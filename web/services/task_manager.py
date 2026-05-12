"""
任务管理器 - 负责扫描任务的创建、状态管理、生命周期
"""
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Optional

from core.database import DatabaseManager
from core.config import ConfigManager
from core.utils import load_text_file


class TaskManager:
    """扫描任务管理器"""
    
    MAX_CONCURRENT_SCANS = 5  # 最多同时执行的扫描任务数
    
    def __init__(self, db_manager: DatabaseManager, config_manager: ConfigManager):
        self.db = db_manager
        self.config_mgr = config_manager
        self.active_tasks: Dict[str, dict] = {}
        self.task_counter = 0
        self.task_lock = threading.Lock()
        self.logger = logging.getLogger("TaskManager")

    def _generate_task_id(self) -> str:
        """生成唯一任务ID"""
        with self.task_lock:
            self.task_counter += 1
            return f"task_{self.task_counter}_{int(time.time())}"

    @property
    def running_count(self) -> int:
        """当前正在运行的任务数"""
        return sum(1 for t in self.active_tasks.values() 
                   if t.get('status') == 'running')

    def create_task(
        self,
        ip_ranges: str = '',
        ports: str = '',
        exclude_ips: str = '',
        max_workers: int = 10,
        ulimit: int = 15000,
        timeout: int = 700,
        scheduled_task_id: Optional[int] = None,
    ) -> str:
        """
        创建扫描任务
        
        Returns:
            task_id: 唯一任务标识
        """
        task_id = self._generate_task_id()

        # 解析IP范围
        from core.utils import parse_ip_range, parse_ports, load_ip_ranges
        if ip_ranges.strip():
            ip_range_list = parse_ip_range(ip_ranges)
        else:
            config = self.config_mgr.get_config()
            ip_range_list = load_ip_ranges(config.ip_range_file, logging.getLogger())

        if not ip_range_list:
            raise ValueError("IP范围不能为空")

        # 解析端口
        if ports.strip():
            ports_str = parse_ports(ports)
        else:
            config = self.config_mgr.get_config()
            ports_str = load_text_file(config.ports_file, logging.getLogger(), "端口")
            if not ports_str:
                raise ValueError("端口列表为空")

        # 解析排除IP
        if exclude_ips.strip():
            exclude_ips_str = exclude_ips.strip()
        else:
            config = self.config_mgr.get_config()
            exclude_ips_str = load_text_file(config.exclude_ips_file, logging.getLogger(), "排除IP")

        # 创建任务记录
        self.active_tasks[task_id] = {
            'id': task_id,
            'status': 'pending',  # pending → running → completed/failed/cancelled
            'progress': 0,
            'total': len(ip_range_list),
            'message': '等待执行...',
            'current_cidr': '',
            'found_hosts': 0,
            'open_ports': 0,
            'elapsed_time': 0,
            'estimated_remaining': 0,
            'logs': [],
            'results': {},
            'orchestrator': None,
            'record_id': None,
            'start_time': datetime.now().isoformat(),
            'workers': max_workers,
            'ulimit': ulimit,
            'timeout': timeout,
            'ip_ranges': ip_range_list,
            'ports': ports_str,
            'exclude_ips': exclude_ips_str,
            'scheduled_task_id': scheduled_task_id,
        }

        return task_id

    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务"""
        return self.active_tasks.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        task = self.active_tasks.get(task_id)
        if not task:
            return None

        return {
            'id': task['id'],
            'status': task['status'],
            'progress': task['progress'],
            'total': task['total'],
            'message': task['message'],
            'current_cidr': task.get('current_cidr', ''),
            'found_hosts': task.get('found_hosts', 0),
            'open_ports': task.get('open_ports', 0),
            'elapsed_time': task.get('elapsed_time', 0),
            'estimated_remaining': task.get('estimated_remaining', 0),
            'results_count': len(task.get('results', {})),
            'report_file': task.get('report_file', ''),
            'logs': task.get('logs', []),
            'workers': task.get('workers', 0),
            'ulimit': task.get('ulimit', 0),
        }

    def mark_running(self, task_id: str):
        """标记任务为运行中"""
        if task_id in self.active_tasks:
            self.active_tasks[task_id]['status'] = 'running'

    def mark_completed(self, task_id: str):
        """标记任务为已完成"""
        if task_id in self.active_tasks:
            self.active_tasks[task_id]['status'] = 'completed'

    def mark_failed(self, task_id: str, error: str = ''):
        """标记任务为失败"""
        if task_id in self.active_tasks:
            self.active_tasks[task_id]['status'] = 'failed'
            if error:
                self.active_tasks[task_id]['message'] = f"扫描失败: {error}"

    def mark_cancelled(self, task_id: str):
        """标记任务为已取消"""
        if task_id in self.active_tasks:
            self.active_tasks[task_id]['status'] = 'cancelled'

    def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """清理过期任务记录"""
        now = time.time()
        to_remove = []
        for task_id, task in self.active_tasks.items():
            if task['status'] in ('completed', 'failed', 'cancelled'):
                try:
                    task_time = datetime.fromisoformat(task['start_time']).timestamp()
                    if now - task_time > max_age_hours * 3600:
                        to_remove.append(task_id)
                except Exception:
                    pass
        for task_id in to_remove:
            del self.active_tasks[task_id]
