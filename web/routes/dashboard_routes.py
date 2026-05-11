"""
仪表盘和首页路由
/api/stats, /api/system/health, / (首页)
"""
from pathlib import Path
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, send_file, current_app, request

from apscheduler.schedulers.base import STATE_RUNNING
from web.rate_limit import limiter

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    """返回前端页面"""
    project_root = current_app.config['project_root']
    index_path = project_root / 'web' / 'frontend' / 'dist' / 'index.html'
    if index_path.exists():
        return send_file(str(index_path))
    return send_file(str(Path(__file__).parent.parent / 'templates' / 'index.html'))


@dashboard_bp.route('/api/stats', methods=['GET'])
def get_stats():
    """获取丰富的仪表盘统计信息"""
    try:
        db_manager = current_app.config['db_manager']
        
        # 基础统计
        base_stats = db_manager.get_statistics()
        total = base_stats.get('total_scans', 0)
        status_counts = base_stats.get('status_counts', {})
        completed = status_counts.get('completed', 0)
        failed = status_counts.get('failed', 0)
        cancelled = status_counts.get('cancelled', 0)
        running = status_counts.get('running', 0)
        success_rate = round((completed / total * 100), 1) if total > 0 else 0

        # 1. 基础统计
        stats = {
            'total_scans': total,
            'total_hosts': base_stats.get('total_hosts', 0),
            'completed_count': completed,
            'failed_count': failed,
            'cancelled_count': cancelled,
            'running_count': running,
            'success_rate': success_rate,
            'status_counts': status_counts,
            'area_counts': base_stats.get('area_counts', {}),
        }

        # 2. 今日统计
        today = datetime.now().strftime('%Y-%m-%d')
        with db_manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*), SUM(total_hosts), SUM(open_ports_count), AVG(duration_seconds) "
                "FROM scan_records WHERE date(created_at) = ?", (today,)
            )
            row = cursor.fetchone()
            stats['today'] = {
                'scans': row[0] or 0,
                'hosts': row[1] or 0,
                'ports': row[2] or 0,
                'avg_duration': round(row[3]) if row[3] else 0
            }

            # 3. 7天扫描趋势
            trend = []
            for i in range(6, -1, -1):
                day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                day_label = (datetime.now() - timedelta(days=i)).strftime('%m/%d')
                cursor.execute(
                    "SELECT COUNT(*), SUM(total_hosts), SUM(open_ports_count) "
                    "FROM scan_records WHERE date(created_at) = ?", (day,)
                )
                row = cursor.fetchone()
                trend.append({
                    'date': day_label,
                    'scans': row[0] or 0,
                    'hosts': row[1] or 0,
                    'ports': row[2] or 0
                })
            stats['trend'] = trend

            # 4. 端口风险等级分布
            cursor.execute("""
                SELECT p.risk_level, COUNT(*) as cnt
                FROM scan_results sr
                JOIN ports p ON sr.port_num = p.port_num
                GROUP BY p.risk_level
            """)
            risk_rows = cursor.fetchall()
            risk_map = {1: 'low', 2: 'medium', 3: 'high'}
            risk_dist = {'high': 0, 'medium': 0, 'low': 0}
            for row in risk_rows:
                level_name = risk_map.get(row[0], 'low')
                risk_dist[level_name] = row[1]
            stats['risk_distribution'] = risk_dist

            # 5. 漏洞主机 Top 10（按开放端口数排序）
            cursor.execute("""
                SELECT ip_address, COUNT(*) as port_count
                FROM scan_results
                GROUP BY ip_address
                ORDER BY port_count DESC
                LIMIT 10
            """)
            top_hosts = [{'ip': row[0], 'ports': row[1]} for row in cursor.fetchall()]
            stats['top_hosts'] = top_hosts

            # 6. 最近完成扫描的平均耗时
            cursor.execute("""
                SELECT AVG(duration_seconds), MAX(duration_seconds), MIN(duration_seconds)
                FROM scan_records WHERE scan_status = 'completed' AND duration_seconds > 0
            """)
            dur_row = cursor.fetchone()
            stats['avg_duration'] = {
                'avg': round(dur_row[0]) if dur_row[0] else 0,
                'max': dur_row[1] or 0,
                'min': dur_row[2] or 0
            }

            # 7. 定时任务汇总
            cursor.execute("""
                SELECT COUNT(*), SUM(total_runs), SUM(total_success), SUM(total_failed)
                FROM scheduled_tasks WHERE is_active = 1
            """)
            task_row = cursor.fetchone()
            stats['scheduled_tasks'] = {
                'total': task_row[0] or 0,
                'total_runs': task_row[1] or 0,
                'total_success': task_row[2] or 0,
                'total_failed': task_row[3] or 0
            }

            # 8. 最近发现的端口服务 Top 5
            cursor.execute("""
                SELECT sr.port_num, p.service_name, COUNT(*) as cnt
                FROM scan_results sr
                LEFT JOIN ports p ON sr.port_num = p.port_num
                GROUP BY sr.port_num
                ORDER BY cnt DESC
                LIMIT 5
            """)
            top_ports = [{'port': row[0], 'service': row[1] or str(row[0]), 'count': row[2]} for row in cursor.fetchall()]
            stats['top_ports'] = top_ports

        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@dashboard_bp.route('/api/system/health', methods=['GET'])
@limiter.exempt
def health_check():
    """系统健康检查"""
    db_manager = current_app.config['db_manager']
    scheduler = current_app.config['scheduler']
    
    health = {
        'status': 'healthy',
        'checks': {},
        'timestamp': __import__('datetime').datetime.now().isoformat(),
    }
    
    # 检查数据库连接
    try:
        db_manager.get_statistics()
        health['checks']['database'] = 'ok'
    except Exception as e:
        health['checks']['database'] = f'error: {str(e)}'
        health['status'] = 'unhealthy'
    
    # 检查APScheduler状态
    try:
        if scheduler and scheduler.scheduler:
            sched_running = scheduler.scheduler.state == STATE_RUNNING
            jobs_count = len(scheduler.scheduler.get_jobs())
            health['checks']['scheduler'] = {
                'running': sched_running,
                'jobs': jobs_count
            }
            if not sched_running:
                health['checks']['scheduler']['warning'] = 'scheduler_not_running'
        else:
            health['checks']['scheduler'] = 'not_initialized'
    except Exception as e:
        health['checks']['scheduler'] = f'error: {str(e)}'
    
    # 检查活跃任务数
    scan_service = current_app.config.get('scan_service')
    if scan_service:
        running = scan_service.task_manager.running_count
        health['checks']['active_scans'] = running
    
    return jsonify(health)


# ==================== 资产变更追踪 ====================

@dashboard_bp.route('/api/assets/compare', methods=['POST'])
def compare_assets():
    """
    对比两次扫描的资产变更
    
    请求体: { "record_id_old": int, "record_id_new": int }
    响应: { new_hosts, removed_hosts, port_changes, total_old, total_new }
    """
    try:
        db_manager = current_app.config['db_manager']
        data = request.get_json() or {}
        record_id_old = data.get('record_id_old')
        record_id_new = data.get('record_id_new')
        
        if not record_id_old or not record_id_new:
            return jsonify({'success': False, 'message': '请选择两次扫描记录'}), 400
        
        result = db_manager.compare_scan_results(record_id_old, record_id_new)
        
        # 获取记录信息
        old_record = db_manager.get_scan_record_by_id(record_id_old)
        new_record = db_manager.get_scan_record_by_id(record_id_new)
        
        return jsonify({
            'success': True,
            'data': {
                **result,
                'old_record': {
                    'id': old_record.id, 'start_time': old_record.start_time,
                    'end_time': old_record.end_time
                } if old_record else None,
                'new_record': {
                    'id': new_record.id, 'start_time': new_record.start_time,
                    'end_time': new_record.end_time
                } if new_record else None,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@dashboard_bp.route('/api/assets/trend', methods=['GET'])
def get_asset_trend():
    """获取资产变化趋势数据"""
    try:
        db_manager = current_app.config['db_manager']
        days = request.args.get('days', 30, type=int)
        trend = db_manager.get_asset_trend(days=min(days, 90))
        return jsonify({'success': True, 'data': trend})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@dashboard_bp.route('/api/assets/summary', methods=['GET'])
def get_asset_summary():
    """获取资产概览（用于Dashboard）"""
    try:
        db_manager = current_app.config['db_manager']
        
        with db_manager._get_connection() as conn:
            cursor = conn.cursor()
            
            # 最近一次扫描的主机数
            cursor.execute("""
                SELECT total_hosts, open_ports_count, created_at
                FROM scan_records WHERE scan_status = 'completed'
                ORDER BY id DESC LIMIT 1
            """)
            last_scan = cursor.fetchone()
            
            # 历史峰值
            cursor.execute("SELECT MAX(total_hosts), MAX(open_ports_count) FROM scan_records")
            peak = cursor.fetchone()
            
            # 唯一IP总数
            cursor.execute("SELECT COUNT(DISTINCT ip_address) FROM scan_results")
            unique_ips = cursor.fetchone()[0]
            
            # 最近30天新增IP数（简化：与最早记录对比）
            cursor.execute("""
                SELECT COUNT(DISTINCT ip_address) FROM scan_results 
                WHERE created_at >= datetime('now', '-30 days')
            """)
            recent_ips = cursor.fetchone()[0]
            
        return jsonify({
            'success': True,
            'data': {
                'last_scan': {
                    'hosts': last_scan['total_hosts'] if last_scan else 0,
                    'ports': last_scan['open_ports_count'] if last_scan else 0,
                    'time': last_scan['created_at'] if last_scan else None
                },
                'peak': {
                    'hosts': peak[0] or 0,
                    'ports': peak[1] or 0
                },
                'unique_ips': unique_ips or 0,
                'recent_new_ips': recent_ips or 0
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
