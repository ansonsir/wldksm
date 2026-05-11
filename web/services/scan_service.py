"""
扫描任务管理服务 (v4.0 精简版)
委托给 TaskManager + ScanExecutor
"""
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Callable

from core.config import ConfigManager
from core.database import DatabaseManager, ScanRecord
from core.utils import setup_logging, load_text_file
from web.services.task_manager import TaskManager
from web.services.scan_executor import ScanExecutor


class ScanService:
    """扫描任务管理服务（统一入口）"""

    def __init__(self, db_manager: DatabaseManager, config_manager: ConfigManager, mailer=None, scheduler=None):
        self.db = db_manager
        self.config_mgr = config_manager
        self.mailer = mailer
        self.scheduler = scheduler
        self.logger = logging.getLogger("ScanService")

        # 子服务
        self.task_manager = TaskManager(db_manager, config_manager)
        self.scan_executor = ScanExecutor(
            db_manager, config_manager, self.task_manager, mailer, scheduler
        )

    # --- 别名属性（保持向后兼容） ---
    @property
    def active_tasks(self):
        return self.task_manager.active_tasks

    @property
    def task_counter(self):
        return self.task_manager.task_counter

    @property
    def task_lock(self):
        return self.task_manager.task_lock

    # --- 任务管理 ---

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
        """创建扫描任务"""
        return self.task_manager.create_task(
            ip_ranges=ip_ranges,
            ports=ports,
            exclude_ips=exclude_ips,
            max_workers=max_workers,
            ulimit=ulimit,
            timeout=timeout,
            scheduled_task_id=scheduled_task_id,
        )

    def execute_task(
        self,
        task_id: str,
        project_root: Path,
        progress_callback: Optional[Callable] = None,
    ):
        """执行扫描任务（后台线程）"""
        return self.scan_executor.execute_task(task_id, project_root, progress_callback)

    def stop_task(self, task_id: str) -> bool:
        """停止扫描任务"""
        return self.scan_executor.stop_task(task_id)

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        return self.task_manager.get_task_status(task_id)

    def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """清理过期任务"""
        self.task_manager.cleanup_completed_tasks(max_age_hours)
