"""
扫描任务相关路由
/api/scan/start, /api/scan/stop, /api/scan/status, /api/scan/history/*
"""
import logging
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from web.middleware.auth_middleware import require_auth, require_csrf
from web.utils import success_response, error_response
from core.database import ScanResultDetail

logger = logging.getLogger(__name__)

scan_bp = Blueprint('scan', __name__, url_prefix='/api/v1')


def _get_services():
    """获取全局服务实例"""
    return (
        current_app.config['config_manager'],
        current_app.config['db_manager'],
        current_app.config['scan_service'],
    )


def _get_project_root():
    return current_app.config['project_root']


@scan_bp.route('/scan/start', methods=['POST'])
@require_auth
@require_csrf
def start_scan():
    """启动扫描任务"""
    try:
        config_manager, _, scan_service = _get_services()
        data = request.get_json()

        task_id = scan_service.create_task(
            ip_ranges=data.get('ip_ranges', ''),
            ports=data.get('ports', ''),
            exclude_ips=data.get('exclude_ips', ''),
            max_workers=data.get('max_workers', config_manager.get_config().max_workers),
            ulimit=data.get('ulimit', config_manager.get_config().ulimit),
            timeout=data.get('timeout', config_manager.get_config().timeout),
        )

        def progress_callback(completed, total, message, **extra):
            if task_id in scan_service.active_tasks:
                task = scan_service.active_tasks[task_id]
                task['progress'] = completed
                task['total'] = total
                task['message'] = message
                task['current_cidr'] = extra.get('current_cidr', '')
                task['found_hosts'] = extra.get('found_hosts', 0)
                task['open_ports'] = extra.get('open_ports', 0)
                task['elapsed_time'] = extra.get('elapsed_time', 0)
                task['estimated_remaining'] = extra.get('estimated_remaining', 0)

        scan_service.execute_task(task_id, _get_project_root(), progress_callback)

        return success_response(
            data={'task_id': task_id, 'message': '扫描任务已启动'},
            message='扫描任务已启动'
        )
    except ValueError as e:
        return error_response(message=str(e), code=400)
    except Exception as e:
        logger.error("启动扫描任务失败: %s", e, exc_info=True)
        return error_response(message='启动扫描任务失败，请稍后重试', code=500)


@scan_bp.route('/scan/stop/<task_id>', methods=['POST'])
@require_auth
@require_csrf
def stop_scan(task_id):
    """停止扫描任务"""
    _, _, scan_service = _get_services()
    if scan_service.stop_task(task_id):
        return success_response(message='扫描停止请求已发送')
    return error_response(message='任务不存在', code=404)


@scan_bp.route('/scan/status/<task_id>', methods=['GET'])
@require_auth
def get_scan_status(task_id):
    """获取扫描任务状态"""
    _, _, scan_service = _get_services()
    status = scan_service.get_task_status(task_id)
    if status:
        return success_response(data=status)
    return error_response(message='任务不存在', code=404)


@scan_bp.route('/scan/history', methods=['GET'])
@require_auth
def get_scan_history():
    """获取扫描历史"""
    try:
        _, db_manager, scan_service = _get_services()
        project_root = _get_project_root()
        limit = request.args.get('limit', 50, type=int)
        records = db_manager.get_scan_records(limit=limit)

        data = []
        for r in records:
            area = db_manager.get_scan_area_by_id(r.area_id)
            report_file = r.report_file or ''
            if report_file:
                rp = Path(report_file)
                if not rp.is_absolute():
                    rp = project_root / rp
                if rp.exists():
                    report_file = str(rp)
                else:
                    report_file = ''

            task_id = None
            if r.scan_status == 'running':
                for tid, task in scan_service.active_tasks.items():
                    if task.get('record_id') == r.id:
                        task_id = tid
                        break

            data.append({
                'id': r.id,
                'area': area.area_name if area else '-',
                'status': r.scan_status,
                'start_time': r.start_time or '-',
                'end_time': r.end_time or '-',
                'duration': r.duration_seconds,
                'total_hosts': r.total_hosts,
                'open_ports': r.open_ports_count,
                'max_workers': r.max_workers,
                'ulimit': r.ulimit,
                'result_file': r.result_file,
                'report_file': report_file,
                'error_message': r.error_message,
                'task_id': task_id,
            })

        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.error("获取扫描历史失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '获取扫描历史失败，请稍后重试'}), 500


@scan_bp.route('/scan/history/<int:record_id>', methods=['GET'])
@require_auth
def get_scan_detail(record_id):
    """获取扫描详情"""
    try:
        _, db_manager, _ = _get_services()
        project_root = _get_project_root()
        record = db_manager.get_scan_record_by_id(record_id)
        if not record:
            return jsonify({'success': False, 'message': '记录不存在'}), 404

        area = db_manager.get_scan_area_by_id(record.area_id)
        results = db_manager.get_scan_results(record_id)

        if not results and record.result_file:
            try:
                result_path = Path(record.result_file)
                if not result_path.is_absolute():
                    result_path = project_root / result_path
                if result_path.exists():
                    parsed = []
                    with open(result_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith('#'):
                                continue
                            parts = line.split('  ')
                            if len(parts) >= 2:
                                ip = parts[0].strip()
                                ports_str = parts[1].strip().strip('[]')
                                for p in ports_str.split(','):
                                    p = p.strip()
                                    if p:
                                        try:
                                            parsed.append(ScanResultDetail(
                                                record_id=record_id,
                                                ip_address=ip,
                                                port_num=int(p),
                                                service_name=''
                                            ))
                                        except ValueError:
                                            continue
                    results = parsed
            except Exception:
                pass

        return jsonify({
            'success': True,
            'data': {
                'id': record.id,
                'area': area.area_name if area else '未知',
                'status': record.scan_status,
                'start_time': record.start_time,
                'end_time': record.end_time,
                'duration': record.duration_seconds,
                'ip_ranges': record.ip_ranges,
                'total_hosts': record.total_hosts,
                'open_ports_count': record.open_ports_count,
                'max_workers': record.max_workers,
                'ulimit': record.ulimit,
                'result_file': record.result_file,
                'report_file': record.report_file,
                'error_message': record.error_message,
                'details': [
                    {'ip': r.ip_address, 'port': r.port_num, 'service': r.service_name}
                    for r in results
                ]
            }
        })
    except Exception as e:
        logger.error("获取扫描详情失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '获取扫描详情失败，请稍后重试'}), 500


@scan_bp.route('/scan/history/delete', methods=['POST'])
@require_auth
@require_csrf
def delete_scan_history():
    """删除扫描历史记录"""
    try:
        _, db_manager, _ = _get_services()
        project_root = _get_project_root()
        data = request.get_json() or {}
        ids = data.get('ids', [])
        if not ids:
            return jsonify({'success': False, 'message': '未选择要删除的记录'}), 400

        deleted = []
        failed = []
        for record_id in ids:
            record = db_manager.get_scan_record_by_id(record_id)
            if not record:
                failed.append({'id': record_id, 'reason': '记录不存在'})
                continue

            if record.report_file:
                try:
                    report_path = Path(record.report_file)
                    if not report_path.is_absolute():
                        report_path = project_root / report_path
                    if report_path.exists() and report_path.is_file():
                        report_path.unlink()
                except Exception:
                    pass

            try:
                with db_manager._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM scan_records WHERE id = ?", (record_id,))
                    if cursor.rowcount > 0:
                        deleted.append(record_id)
                    else:
                        failed.append({'id': record_id, 'reason': '删除失败'})
            except Exception as e:
                failed.append({'id': record_id, 'reason': str(e)})

        msg = f'成功删除 {len(deleted)} 条记录'
        if failed:
            msg += f'，{len(failed)} 条失败'

        return jsonify({
            'success': len(deleted) > 0,
            'message': msg,
            'deleted': deleted,
            'failed': failed
        })
    except Exception as e:
        logger.error("删除扫描历史失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '删除扫描历史失败，请稍后重试'}), 500
