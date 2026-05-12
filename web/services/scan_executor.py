"""
扫描执行引擎 - 负责实际的扫描执行逻辑
将扫描线程与任务管理分离
"""
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

from core.config import ConfigManager
from core.scanner import ScanOrchestrator
from core.database import DatabaseManager, ScanRecord
from core.utils import setup_logging
from web.services.task_manager import TaskManager


class ScanExecutor:
    """扫描执行引擎"""
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        config_manager: ConfigManager,
        task_manager: TaskManager,
        mailer=None,
        scheduler=None
    ):
        self.db = db_manager
        self.config_mgr = config_manager
        self.task_manager = task_manager
        self.mailer = mailer
        self.scheduler = scheduler
        self.logger = logging.getLogger("ScanExecutor")

    def execute_task(
        self,
        task_id: str,
        project_root: Path,
        progress_callback: Optional[Callable] = None,
    ):
        """
        启动扫描任务（后台线程）
        
        Args:
            task_id: 任务ID
            project_root: 项目根目录
            progress_callback: 进度回调函数 (completed, total, message, **extra)
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        # 检查并发上限
        if self.task_manager.running_count >= TaskManager.MAX_CONCURRENT_SCANS:
            self.logger.warning(
                f"并发扫描已达上限({TaskManager.MAX_CONCURRENT_SCANS})，"
                f"任务 {task_id} 加入队列等待"
            )
            # 不做队列机制，直接启动（由 TaskManager 外的控制决定）

        config = self.config_mgr.get_config()
        self.task_manager.mark_running(task_id)

        def scan_worker():
            try:
                self._do_scan(task, config, project_root, progress_callback)
            except Exception as e:
                task['message'] = f"扫描失败: {str(e)}"
                self.task_manager.mark_failed(task_id, str(e))
                if task.get('record_id'):
                    self.db.update_scan_record(
                        task['record_id'],
                        scan_status="failed",
                        error_message=str(e)
                    )
                self._notify_scheduler(task, success=False)
                self._emit_scan_event(task_id, 'failed', {'message': str(e)})

        thread = threading.Thread(target=scan_worker, daemon=True)
        thread.start()
        task['thread'] = thread

    def _do_scan(self, task, config, project_root, progress_callback):
        """执行实际扫描"""
        config_mgr = self.config_mgr
        orchestrator = ScanOrchestrator(config, setup_logging(config.log_file, console_output=False))
        task['orchestrator'] = orchestrator

        # 创建数据库记录
        area = self.db.get_scan_area_by_name("默认区域")
        if not area:
            area = self.db.get_scan_area_by_id(1)
        area_id = area.id if area else 1

        record = ScanRecord(
            area_id=area_id,
            start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ip_ranges=",".join(task['ip_ranges']),
            scan_status="running",
            result_file=config.save_result_file,
            max_workers=task['workers'],
            ulimit=task['ulimit'],
        )
        record_id = self.db.create_scan_record(record)
        task['record_id'] = record_id

        # 执行扫描
        results = orchestrator.scan_all_ranges(
            task['ip_ranges'],
            task['ports'],
            task['exclude_ips'],
            progress_callback,
        )

        task['results'] = results
        task['progress'] = len(task['ip_ranges'])
        task['message'] = f"扫描完成，发现 {len(results)} 台主机，共 {sum(len(p) for p in results.values())} 个开放端口"
        task['found_hosts'] = len(results)
        task['open_ports'] = sum(len(p) for p in results.values())

        # 保存结果
        from core.utils import save_results
        save_results(
            results,
            orchestrator.statistics.to_dict(),
            task['ports'],
            config.save_result_file,
            logging.getLogger()
        )

        # 保存扫描结果详情到数据库
        scan_details = []
        for ip, ports_list in results.items():
            for port in ports_list:
                scan_details.append((ip, port, ""))
        if scan_details:
            self.db.add_scan_results_batch(record_id, scan_details)

        # 生成报告
        self.logger.info("开始生成报告...")
        self._generate_report(task, config, project_root, area_id, record_id, orchestrator)

        # 自动发送邮件通知
        if task.get('report_file') and self.mailer:
            task['total_hosts'] = len(results)
            task['total_ports'] = sum(len(p) for p in results.values())
            self._send_auto_notification(task, config)

        self.task_manager.mark_completed(task['id'])

        # WebSocket 推送完成事件
        self._emit_scan_event(task['id'], 'completed', {
            'found_hosts': task.get('found_hosts', 0),
            'open_ports': task.get('open_ports', 0),
            'message': task.get('message', ''),
            'report_file': task.get('report_file', ''),
        })

        # 更新数据库记录
        open_ports_count = sum(len(ports_list) for ports_list in results.values())
        self.db.update_scan_record(
            record_id,
            end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            duration_seconds=int(orchestrator.statistics.duration),
            total_hosts=len(results),
            open_ports_count=open_ports_count,
            max_workers=orchestrator.statistics.workers,
            ulimit=task['ulimit'],
            scan_status="completed",
        )

        # Webhook 通知（扫描完成自动推送）
        if task.get('record_id'):
            self._send_webhook_notification(task)

        self._notify_scheduler(task, success=True)

    def _send_webhook_notification(self, task):
        """发送 Webhook 扫描结果通知"""
        try:
            from web.webhook_service import get_webhook_notifier
            notifier = get_webhook_notifier()
            if not notifier.configs:
                return

            # 计算高危设备数（端口数 ≥ 5 视为高危）
            results = task.get('results', {})
            high_risk_count = sum(1 for ports in results.values() if len(ports) >= 5)

            report_url = None
            if task.get('record_id'):
                report_url = f"/api/reports/download/{task['record_id']}"

            scan_info = {
                'total_hosts': task.get('found_hosts', 0),
                'open_ports': task.get('open_ports', 0),
                'high_risk_count': high_risk_count,
                'duration': task.get('message', '未知'),
                'scan_time': task.get('start_time', '未知'),
                'report_url': report_url,
            }
            results_dict = notifier.send_scan_result(scan_info)
            for platform, (success, msg) in results_dict.items():
                if success:
                    self.logger.info(f"[{platform}] Webhook 通知已发送")
                else:
                    self.logger.warning(f"[{platform}] Webhook 通知失败: {msg}")
        except Exception as e:
            self.logger.error(f"Webhook 通知异常: {e}")

    def _generate_report(self, task, config, project_root, area_id, record_id, orchestrator):
        """生成扫描报告"""
        from core.report import generate_report_with_db

        output_file = f"{time.strftime('%Y.%m.%d')}{config.report_suffix}.docx"
        output_path = Path(config.report_dir) / output_file
        if not output_path.is_absolute():
            output_path = project_root / output_path

        counter = 1
        while output_path.exists():
            output_file = f"{time.strftime('%Y.%m.%d')}_{counter}{config.report_suffix}.docx"
            output_path = Path(config.report_dir) / output_file
            if not output_path.is_absolute():
                output_path = project_root / output_path
            counter += 1

        scan_data = {
            "scan_start_time": orchestrator.statistics.to_dict()['start_time'],
            "scan_end_time": orchestrator.statistics.to_dict()['end_time'],
            "scan_duration": orchestrator.statistics.to_dict()['duration'],
            "ip_range": "\n".join(task['ip_ranges'][:8]) + (
                f"\n... (共{len(task['ip_ranges'])}个网段)" if len(task['ip_ranges']) > 8 else ""),
            "ports": task['ports'],
        }

        report_success = generate_report_with_db(
            scan_data=scan_data,
            result_file=config.save_result_file,
            output_file=str(output_path),
            area_name="默认区域",
            template_dir=config.template_dir,
            db_manager=self.db,
            record_id=record_id,
        )

        if report_success and output_path.exists():
            task['report_file'] = str(output_path)
            self.db.update_scan_record(record_id, report_file=str(output_path))

            # 生成多格式导出文件 (CSV/JSON/HTML)
            self._generate_alternate_formats(scan_data, config, output_path)

    def _generate_alternate_formats(self, scan_data, config, output_path):
        """生成 CSV/JSON/HTML 格式报告"""
        try:
            from core.report import (
                generate_csv_report, generate_json_report, generate_html_report,
                ReportDataAnalyzer
            )
            analyzer = ReportDataAnalyzer()
            result_file = config.save_result_file
            if not Path(result_file).is_absolute():
                result_file = str(Path(config.data_dir) / result_file)
            if not analyzer.load_scan_results(result_file):
                return
            analysis = analyzer.analyze(enable_redarea=False)

            for fn, name in [(generate_csv_report, 'CSV'), (generate_json_report, 'JSON'), (generate_html_report, 'HTML')]:
                try:
                    fn(scan_data, analysis, str(output_path))
                    self.logger.info(f"{name} 格式报告已生成")
                except Exception as e:
                    self.logger.warning(f"{name} 格式报告生成失败: {e}")
        except Exception as e:
            self.logger.warning(f"多格式报告生成失败: {e}")

    def _send_auto_notification(self, task, config):
        """自动发送邮件通知"""
        try:
            recipients_str = config.default_recipients
            if not recipients_str or not recipients_str.strip():
                self.logger.info("未配置默认收件人，跳过自动邮件通知")
                return

            recipients = []
            for line in recipients_str.replace(',', '\n').split('\n'):
                email = line.strip()
                if email:
                    recipients.append(email)

            if not recipients:
                return

            report_path = task.get('report_file')
            report_name = Path(report_path).name if report_path else '未知'

            subject = f"【自动通知】网络端口扫描完成 - {time.strftime('%Y.%m.%d')}"
            body = f"网络端口扫描任务已完成，请查收附件中的扫描报告。\n\n"
            body += f"报告文件: {report_name}\n"
            body += f"发现主机: {task.get('total_hosts', 0)} 台\n"
            body += f"开放端口: {task.get('total_ports', 0)} 个\n"
            body += f"\n此邮件为系统自动发送，请勿回复。"

            success, message = self.mailer.send_report(
                report_path=report_path,
                recipients=recipients,
                subject=subject,
                body=body,
            )

            if success:
                self.logger.info(f"自动邮件通知发送成功: {', '.join(recipients)}")
            else:
                self.logger.error(f"自动邮件通知发送失败: {message}")
        except Exception as e:
            self.logger.error(f"自动邮件通知异常: {e}")

    def _notify_scheduler(self, task, success: bool):
        """通知调度器任务完成"""
        scheduled_task_id = task.get('scheduled_task_id')
        if scheduled_task_id and self.scheduler:
            task_id = task.get('id', '')
            self.scheduler.on_scan_task_completed(scheduled_task_id, task_id, success=success)

    def _emit_scan_event(self, task_id: str, status: str, extra: dict = None):
        """通过 WebSocket 推送扫描事件"""
        try:
            from flask import current_app
            socketio = current_app.config.get('socketio') if current_app else None
            if socketio:
                payload = {'task_id': task_id, 'status': status}
                if extra:
                    payload.update(extra)
                socketio.emit('scan_status', payload, room=f'scan_{task_id}')
        except Exception:
            pass  # WebSocket 推送失败不影响主流程

    def stop_task(self, task_id: str) -> bool:
        """停止扫描任务"""
        task = self.task_manager.get_task(task_id)
        if not task:
            self.logger.warning(f"扫描任务 {task_id} 不存在")
            return False

        orchestrator = task.get('orchestrator')
        if not orchestrator:
            # 等待orchestrator被创建（最多等待3秒）
            for _ in range(30):
                time.sleep(0.1)
                orchestrator = task.get('orchestrator')
                if orchestrator:
                    break

            if not orchestrator:
                self.task_manager.mark_cancelled(task_id)
                task['message'] = '扫描已停止（orchestrator未创建）'
                if task.get('record_id'):
                    self.db.update_scan_record(task['record_id'], scan_status='cancelled')
                return True

        orchestrator.stop()
        self.task_manager.mark_cancelled(task_id)
        task['message'] = '扫描已停止'

        if task.get('record_id'):
            self.db.update_scan_record(
                task['record_id'],
                scan_status='cancelled',
                total_hosts=task.get('found_hosts', 0),
                open_ports_count=task.get('open_ports', 0),
            )

        return True
