"""
定时任务调度器
基于 APScheduler 实现
"""
import re
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
import pytz

from core.database import DatabaseManager, ScheduledTask
from core.config import ConfigManager
from web.services.scan_service import ScanService


class TaskScheduler:
    """定时任务调度器"""
    
    def __init__(self, db_manager: DatabaseManager, 
                 scan_service: ScanService,
                 config_manager: ConfigManager):
        self.db = db_manager
        self.scan_service = scan_service
        self.config_mgr = config_manager
        self.logger = logging.getLogger("TaskScheduler")
        
        # 使用本地时区
        timezone = pytz.timezone('Asia/Shanghai')
        self.scheduler = BackgroundScheduler(timezone=timezone)
        self.running_tasks = {}  # 记录正在执行的任务 {task_id: scan_task_id}
        
        # 注册事件监听
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    
    def start(self):
        """启动调度器"""
        try:
            # 先启动调度器
            self.scheduler.start()
            self.logger.info(f"定时任务调度器已启动，运行状态: {self.scheduler.running}")
            
            # 加载所有活跃的定时任务
            tasks = self.db.get_scheduled_tasks(active_only=True)
            self.logger.info(f"加载到 {len(tasks)} 个活跃定时任务")
            
            for task in tasks:
                self.logger.info(f"添加定时任务: {task.task_name} (ID: {task.id}, 类型: {task.task_type}, 表达式: {task.schedule_expr})")
                self._add_job(task)
            
            # 打印所有已调度的任务
            jobs = self.scheduler.get_jobs()
            self.logger.info(f"当前调度器中有 {len(jobs)} 个任务")
            for job in jobs:
                next_run = getattr(job, 'next_run_time', None)
                if next_run:
                    self.logger.info(f"  - {job.id}: next_run_time={next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    self.logger.info(f"  - {job.id}: next_run_time=N/A")
                
            # 注册定期清理黑名单的任务（每天执行一次）
            self.scheduler.add_job(
                func=self._cleanup_blacklist,
                trigger=IntervalTrigger(hours=24),
                id='cleanup_blacklist',
                replace_existing=True,
            )
            self.logger.info("已注册黑名单定期清理任务（每24小时）")
                
        except Exception as e:
            self.logger.error(f"启动定时任务调度器失败: {e}", exc_info=True)
            raise
    
    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.logger.info("定时任务调度器已停止")
    
    def _cleanup_blacklist(self):
        """定期清理过期的 JWT 黑名单记录"""
        try:
            deleted = self.db.cleanup_expired_blacklist()
            if deleted > 0:
                self.logger.info(f"黑名单清理完成: 删除 {deleted} 条过期记录")
        except Exception as e:
            self.logger.warning(f"黑名单清理异常: {e}")
    
    def add_task(self, task: ScheduledTask) -> int:
        """添加定时任务，返回任务ID"""
        self.logger.info(f"开始添加定时任务: {task.task_name}, is_active={task.is_active}")
        
        # 保存到数据库
        task_id = self.db.add_scheduled_task(task)
        task.id = task_id
        self.logger.info(f"任务 {task.task_name} 已保存到数据库, ID={task_id}")
        
        # 添加到调度器
        if task.is_active:
            self.logger.info(f"任务 {task.task_name} 是活跃状态，开始添加到调度器")
            try:
                self._add_job(task)
                self.logger.info(f"✅ 任务 {task.task_name} 已成功添加到APScheduler调度器")
            except Exception as e:
                self.logger.error(f"❌ 添加任务 {task.task_name} (ID={task_id}) 到调度器失败: {e}", exc_info=True)
                # 任务已保存到数据库但未加入调度器，标记为非活跃状态
                try:
                    self.db.update_scheduled_task(task_id, is_active=False)
                    self.logger.warning(f"已将任务 {task.task_name} (ID={task_id}) 标记为非活跃")
                except Exception as db_err:
                    self.logger.error(f"更新任务状态失败: {db_err}")
                raise  # 重新抛出异常，让API层知道失败
        else:
            self.logger.info(f"任务 {task.task_name} 不是活跃状态，跳过添加到调度器")
        
        self.logger.info(f"添加定时任务完成: {task.task_name} (ID: {task_id})")
        return task_id
    
    def remove_task(self, task_id: int) -> bool:
        """移除定时任务"""
        # 从调度器移除
        job_id = f"task_{task_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        # 从数据库删除
        success = self.db.delete_scheduled_task(task_id)
        
        if success:
            self.logger.info(f"删除定时任务: ID {task_id}")
        
        return success
    
    def update_task(self, task_id: int, **kwargs) -> bool:
        """更新定时任务"""
        self.logger.info(f"开始更新定时任务: ID {task_id}, 更新字段: {list(kwargs.keys())}")
        
        # 如果调度表达式被修改，清空 next_run_time（让 _add_job 重新计算）
        if 'schedule_expr' in kwargs or 'task_type' in kwargs:
            self.db.update_scheduled_task(task_id, next_run_time=None)
            self.logger.info(f"任务 {task_id} 调度表达式变化，已清空 next_run_time")
        
        # 更新数据库
        self.db.update_scheduled_task(task_id, **kwargs)
        self.logger.info(f"任务 {task_id} 数据库更新完成")
        
        # 重新加载任务到调度器
        task = self.db.get_scheduled_task(task_id)
        if task:
            self.logger.info(f"重新加载任务: {task.task_name}, schedule_expr={task.schedule_expr}, is_active={task.is_active}")
            
            job_id = f"task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.logger.info(f"移除旧的任务: {job_id}")
                self.scheduler.remove_job(job_id)
            
            if task.is_active:
                self.logger.info(f"任务 {task.task_name} 是活跃状态，重新添加到调度器")
                self._add_job(task)
            else:
                self.logger.info(f"任务 {task.task_name} 不是活跃状态，不添加到调度器")
            
            self.logger.info(f"更新定时任务完成: ID {task_id}")
        
        return True
    
    def toggle_task(self, task_id: int) -> bool:
        """启用/禁用定时任务"""
        task = self.db.get_scheduled_task(task_id)
        if not task:
            return False
        
        new_status = not task.is_active
        self.db.update_scheduled_task(task_id, is_active=new_status)
        
        job_id = f"task_{task_id}"
        if new_status:
            # 启用：先清除旧的 next_run_time，再添加到调度器（会重新计算）
            self.db.update_scheduled_task(task_id, next_run_time=None)
            # 重新加载 task 对象以获取最新状态
            task = self.db.get_scheduled_task(task_id)
            self._add_job(task)
            self.logger.info(f"启用定时任务: ID {task_id}")
        else:
            # 禁用：从调度器移除
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            self.logger.info(f"禁用定时任务: ID {task_id}")
        
        return True
    
    def run_task_now(self, task_id: int) -> Optional[str]:
        """立即执行定时任务，返回扫描任务ID"""
        task = self.db.get_scheduled_task(task_id)
        if not task:
            return None
        
        # 执行任务
        return self._execute_task(task_id, manual=True)
    
    def _add_job(self, task: ScheduledTask):
        """添加任务到调度器"""
        job_id = f"task_{task.id}"
        
        try:
            # 解析调度表达式
            trigger = self._parse_trigger(task.task_type, task.schedule_expr)
            self.logger.info(f"任务 {task.task_name} 触发器创建成功: {task.task_type} - {task.schedule_expr}")
            
            # 添加任务（含 misfire_grace_time，避免错过执行）
            self.scheduler.add_job(
                func=self._execute_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                replace_existing=True,
                misfire_grace_time=86400  # 允许24小时内的错过执行
            )
            
            # 🔧 检测 APScheduler 状态异常：如果调度器状态变为 STOPPED，
            # 说明后台线程已意外退出，需要重新启动调度器
            from apscheduler.schedulers.base import STATE_STOPPED
            if self.scheduler.state == STATE_STOPPED:
                self.logger.warning(
                    f"⚠️ APScheduler 状态异常(STOPPED)，任务 {task.task_name} 被暂存。"
                    f"正在尝试重启调度器..."
                )
                try:
                    self.scheduler.start()
                    self.logger.info(
                        f"✅ 调度器已重新启动，状态: {self.scheduler.state}，"
                        f"暂存任务已激活: {task.task_name}"
                    )
                except Exception as restart_err:
                    self.logger.error(f"❌ 重启调度器失败: {restart_err}", exc_info=True)
                    raise RuntimeError(
                        f"APScheduler 调度器已停止且无法重启: {restart_err}"
                    ) from restart_err
            
            self.logger.info(f"任务 {task.task_name} 已添加到APScheduler (misfire_grace_time=86400s)")
            
            # 检查并更新下次执行时间
            timezone = pytz.timezone('Asia/Shanghai')
            now = datetime.now(timezone)
            
            # 如果 next_run_time 为空或者是过去的时间，重新计算
            need_recalculate = False
            if not task.next_run_time:
                need_recalculate = True
            else:
                try:
                    next_run_dt = datetime.strptime(task.next_run_time, "%Y-%m-%d %H:%M:%S")
                    next_run_dt = timezone.localize(next_run_dt)
                    if next_run_dt <= now:
                        need_recalculate = True
                        self.logger.info(f"任务 {task.task_name} 的 next_run_time ({task.next_run_time}) 已过期，重新计算")
                except Exception as e:
                    self.logger.warning(f"任务 {task.task_name} 解析 next_run_time 失败: {e}")
                    need_recalculate = True
            
            if need_recalculate:
                self._calculate_and_update_next_run(task)
            else:
                self.logger.info(f"任务 {task.task_name} 的 next_run_time ({task.next_run_time}) 有效，跳过重新计算")
            
            self.logger.info(f"任务已添加到调度器: {task.task_name} (ID: {task.id})")
            
        except Exception as e:
            self.logger.error(f"❌ 添加任务到调度器失败: {task.task_name}, 错误: {e}", exc_info=True)
            raise  # 重新抛出异常，让调用者知道
    
    def _calculate_and_update_next_run(self, task: ScheduledTask):
        """计算并更新下次执行时间"""
        try:
            if task.task_type == "cron":
                # 使用 APScheduler 的 trigger 来计算下次执行时间
                trigger = self._parse_trigger(task.task_type, task.schedule_expr)
                
                # 获取当前时间（使用时区）
                timezone = pytz.timezone('Asia/Shanghai')
                now = datetime.now(timezone)
                
                # 计算下次执行时间
                next_time = trigger.get_next_fire_time(None, now)
                
                if next_time:
                    # 转换为字符串
                    next_run = next_time.strftime("%Y-%m-%d %H:%M:%S")
                    self.logger.info(f"任务 {task.task_name} 计算的下次执行时间: {next_run}")
                    
                    # 更新数据库
                    success = self.db.update_scheduled_task(task.id, next_run_time=next_run)
                    if success:
                        self.logger.info(f"✅ 任务 {task.task_name} 的 next_run_time 已更新到数据库: {next_run}")
                    else:
                        self.logger.error(f"❌ 任务 {task.task_name} 的 next_run_time 更新数据库失败")
                else:
                    self.logger.warning(f"⚠️ 任务 {task.task_name} 无法计算下次执行时间")
            else:
                # interval 和 once 类型也需要更新
                self.logger.debug(f"任务 {task.task_name} 类型为 {task.task_type}，跳过 next_run_time 计算")
        except Exception as e:
            self.logger.error(f"计算下次执行时间失败: {e}", exc_info=True)
    
    def _parse_trigger(self, task_type: str, schedule_expr: str):
        """解析调度表达式"""
        timezone = pytz.timezone('Asia/Shanghai')
        
        if task_type == "cron":
            # cron 表达式：分钟 小时 日 月 周
            parts = schedule_expr.split()
            if len(parts) != 5:
                raise ValueError(f"无效的 cron 表达式: {schedule_expr}，应为 5 个字段")
            
            return CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                timezone=timezone  # 显式指定时区，确保与调度器一致
            )
        
        elif task_type == "interval":
            # interval 表达式：如 "24h", "30m", "7d"
            match = re.match(r'(\d+)([hmd])', schedule_expr)
            if match:
                value = int(match.group(1))
                unit = match.group(2)
                kwargs = {}
                if unit == 'h':
                    kwargs['hours'] = value
                elif unit == 'm':
                    kwargs['minutes'] = value
                elif unit == 'd':
                    kwargs['days'] = value
                return IntervalTrigger(**kwargs)
            else:
                raise ValueError(f"无效的 interval 表达式: {schedule_expr}，格式如: 24h, 30m, 7d")
        
        elif task_type == "once":
            # 一次性任务：如 "2024-01-15 09:00:00"
            try:
                run_time = datetime.strptime(schedule_expr, "%Y-%m-%d %H:%M:%S")
                return DateTrigger(run_date=run_time)
            except ValueError:
                raise ValueError(f"无效的日期格式: {schedule_expr}，应为: YYYY-MM-DD HH:MM:SS")
        
        else:
            raise ValueError(f"不支持的任务类型: {task_type}")
    
    def _execute_task(self, task_id: int, manual: bool = False) -> Optional[str]:
        """执行定时任务"""
        try:
            # 检查是否有任务正在执行
            if task_id in self.running_tasks:
                self.logger.warning(f"任务 {task_id} 上次执行未完成，跳过本次执行")
                self.db.update_task_execution_record(task_id, "skipped")
                return None
            
            # 获取任务配置
            task = self.db.get_scheduled_task(task_id)
            if not task:
                self.logger.error(f"未找到定时任务: ID {task_id}")
                return None
            
            if not task.is_active and not manual:
                self.logger.warning(f"定时任务已禁用: {task.task_name} (ID: {task_id})")
                return None
            
            self.logger.info(f"开始执行定时任务: {task.task_name} (ID: {task_id}, manual={manual})")
            
            # 准备扫描参数
            if task.use_default_config:
                # 使用默认配置 — 先重新加载YAML配置（避免使用启动时的旧缓存）
                self.config_mgr.reload_from_yaml()
                config = self.config_mgr.get_config()
                self.logger.info(
                    f"任务 {task.task_name} 使用默认配置: "
                    f"ip_range_file={config.ip_range_file}, "
                    f"ports_file={config.ports_file}, "
                    f"exclude_ips_file={config.exclude_ips_file}"
                )
                from core.utils import load_ip_ranges, load_text_file
                
                try:
                    ip_ranges_list = load_ip_ranges(config.ip_range_file, self.logger)
                    ip_ranges_str = '\n'.join(ip_ranges_list)
                except Exception as e:
                    self.logger.error(f"加载默认IP范围失败: {e}")
                    ip_ranges_str = ""
                
                try:
                    ports_str = load_text_file(config.ports_file, self.logger, "端口")
                except Exception as e:
                    self.logger.error(f"加载默认端口失败: {e}")
                    ports_str = ""
                
                try:
                    exclude_ips_str = load_text_file(config.exclude_ips_file, self.logger, "排除IP")
                except Exception as e:
                    self.logger.error(f"加载默认排除IP失败: {e}")
                    exclude_ips_str = ""
                
                max_workers = config.max_workers
                ulimit = config.ulimit
                timeout = config.timeout
            else:
                # 使用自定义配置
                ip_ranges_str = task.ip_ranges
                ports_str = task.ports
                exclude_ips_str = task.exclude_ips
                max_workers = task.max_workers
                ulimit = task.ulimit
                timeout = task.timeout
            
            # 创建扫描任务
            scan_task_id = self.scan_service.create_task(
                ip_ranges=ip_ranges_str,
                ports=ports_str,
                exclude_ips=exclude_ips_str,
                max_workers=max_workers,
                ulimit=ulimit,
                timeout=timeout,
                scheduled_task_id=task_id
            )
            
            if not scan_task_id:
                self.logger.error(f"创建扫描任务失败: {task.task_name}")
                self.db.update_task_execution_record(task_id, "failed")
                return None
            
            # 执行扫描任务（启动后台线程）
            from pathlib import Path
            project_root = Path(__file__).parent.parent
            self.scan_service.execute_task(scan_task_id, project_root)
            
            # 记录正在执行的任务
            self.running_tasks[task_id] = scan_task_id
            
            # 更新执行记录 - 设置为 running
            self.db.update_task_execution_record(task_id, "running")
            
            # CRON 类型任务：执行后立即计算并更新下次执行时间
            if task.task_type == "cron":
                try:
                    self._calculate_and_update_next_run(task)
                except Exception as e:
                    self.logger.warning(f"更新下次执行时间失败（不影响扫描）: {e}")
            
            self.logger.info(f"定时任务扫描已启动: {task.task_name}, 扫描任务ID: {scan_task_id}")
            return scan_task_id
            
        except Exception as e:
            self.logger.error(f"执行定时任务失败: {e}", exc_info=True)
            self.db.update_task_execution_record(task_id, "failed")
            return None
    
    def _job_listener(self, event):
        """任务执行事件监听器"""
        job_id = event.job_id
        
        # 提取 task_id
        if job_id and job_id.startswith("task_"):
            try:
                task_id = int(job_id.split("_")[1])
                
                if event.exception:
                    # 任务执行出错
                    self.logger.error(f"定时任务执行异常: {job_id}, 错误: {event.exception}")
                    if task_id in self.running_tasks:
                        del self.running_tasks[task_id]
                    self.db.update_task_execution_record(task_id, "failed")
                else:
                    # 任务执行完成（注意：这里只是调度器触发了任务，扫描任务可能还在运行）
                    self.logger.info(f"调度器任务执行完成: {job_id}")
                    # 不更新状态，等待扫描任务完成后再更新
                    
            except (ValueError, IndexError) as e:
                self.logger.error(f"解析任务ID失败: {job_id}, 错误: {e}")
    
    def on_scan_task_completed(self, task_id: int, scan_task_id: str, success: bool):
        """扫描任务完成回调"""
        if task_id in self.running_tasks:
            if self.running_tasks[task_id] == scan_task_id:
                del self.running_tasks[task_id]
                
                status = "success" if success else "failed"
                self.db.update_task_execution_record(task_id, status)
                
                self.logger.info(f"定时任务扫描完成: ID {task_id}, 状态: {status}")
    
    def stop_task(self, task_id: int) -> bool:
        """
        停止正在运行的定时任务
        
        Args:
            task_id: 定时任务ID
            
        Returns:
            是否成功停止
        """
        self.logger.info(f"收到停止定时任务请求: {task_id}")
        self.logger.info(f"当前 running_tasks: {list(self.running_tasks.keys())}")
        
        # 先尝试从 running_tasks 中获取
        if task_id in self.running_tasks:
            scan_task_id = self.running_tasks[task_id]
            self.logger.info(f"从 running_tasks 中找到任务 {task_id}, 扫描任务ID: {scan_task_id}")
        else:
            # running_tasks 中没有，检查数据库状态
            task = self.db.get_scheduled_task(task_id)
            if not task:
                self.logger.warning(f"任务 {task_id} 不存在")
                return False
            
            if task.last_run_status != 'running':
                self.logger.warning(f"任务 {task_id} 数据库状态不是 running: {task.last_run_status}")
                return False
            
            # 数据库状态是 running，但 running_tasks 中没有记录
            # 这可能是服务重启导致的，需要从 scan_records 中查找最新的 running 记录
            self.logger.warning(f"任务 {task_id} 不在 running_tasks 中，但数据库状态是 running")
            self.logger.info(f"尝试从 scan_records 中查找对应的扫描任务")
            
            # 查询该定时任务最新的 running 状态的扫描记录
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM scan_records 
                    WHERE scheduled_task_id = ? AND scan_status = 'running'
                    ORDER BY id DESC LIMIT 1
                """, (task_id,))
                row = cursor.fetchone()
            
            if not row:
                self.logger.warning(f"未找到任务 {task_id} 的 running 状态的扫描记录")
                # 清理数据库状态
                self.db.update_task_execution_record(task_id, "failed")
                return False
            
            record_id = row[0]
            # 扫描任务ID不在数据库中，需要从active_tasks中查找
            # 查找格式为 task_{counter}_{timestamp} 且包含 scheduled_task_id 的任务
            self.logger.info(f"找到扫描记录ID: {record_id}，尝试在 active_tasks 中查找")
            
            scan_task_id = None
            for active_task_id in self.scan_service.active_tasks.keys():
                # 检查这个active_task是否属于这个scheduled_task
                active_task = self.scan_service.active_tasks[active_task_id]
                if active_task.get('scheduled_task_id') == task_id:
                    scan_task_id = active_task_id
                    break
            
            if not scan_task_id:
                self.logger.warning(f"未找到任务 {task_id} 对应的扫描任务")
                # 清理数据库状态
                self.db.update_task_execution_record(task_id, "failed")
                return False
            
            self.logger.info(f"从 active_tasks 找到扫描任务ID: {scan_task_id}")
            # 添加到 running_tasks 中
            self.running_tasks[task_id] = scan_task_id
        
        # 停止扫描任务
        success = self.scan_service.stop_task(scan_task_id)
        
        if success:
            # 从running_tasks中移除
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            
            # 更新数据库状态
            self.db.update_task_execution_record(task_id, "cancelled")
            
            self.logger.info(f"✅ 定时任务已停止: ID {task_id}, 扫描任务ID: {scan_task_id}")
            return True
        else:
            self.logger.error(f"❌ 停止定时任务失败: ID {task_id}, scan_task_id: {scan_task_id}")
            self.logger.info(f"scan_service.active_tasks keys: {list(self.scan_service.active_tasks.keys())}")
            return False
