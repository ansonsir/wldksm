"""
定时任务管理 API
"""
from flask import Blueprint, request, jsonify
from core.database import ScheduledTask
from web.middleware.auth_middleware import require_auth

# 蓝图将在 app.py 中创建并传入 scheduler 实例
scheduler_bp = Blueprint('scheduler', __name__)

# scheduler 实例将在 app.py 中设置
scheduler = None


def init_scheduler_api(scheduler_instance):
    """初始化调度器 API，传入 scheduler 实例"""
    global scheduler
    scheduler = scheduler_instance


@scheduler_bp.route('/api/scheduler/tasks', methods=['GET'])
@require_auth
def get_tasks():
    """获取所有定时任务"""
    try:
        active_only = request.args.get('active_only', 'false').lower() == 'true'
        tasks = scheduler.db.get_scheduled_tasks(active_only=active_only)
        
        task_list = []
        for task in tasks:
            task_list.append({
                'id': task.id,
                'task_name': task.task_name,
                'task_type': task.task_type,
                'schedule_expr': task.schedule_expr,
                'use_default_config': bool(task.use_default_config),
                'ip_ranges': task.ip_ranges or '',
                'ports': task.ports or '',
                'exclude_ips': task.exclude_ips or '',
                'max_workers': task.max_workers or 10,
                'ulimit': task.ulimit or 15000,
                'timeout': task.timeout or 700,
                'is_active': bool(task.is_active),
                'last_run_time': task.last_run_time,
                'last_run_status': task.last_run_status,
                'next_run_time': task.next_run_time,
                'total_runs': task.total_runs,
                'total_success': task.total_success,
                'total_failed': task.total_failed,
                'created_at': task.created_at,
            })
        
        return jsonify({
            'success': True,
            'data': task_list
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@scheduler_bp.route('/api/scheduler/tasks', methods=['POST'])
@require_auth
def create_task():
    """创建定时任务"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('task_name'):
            return jsonify({
                'success': False,
                'message': '任务名称不能为空'
            }), 400
        
        if not data.get('task_type'):
            return jsonify({
                'success': False,
                'message': '任务类型不能为空'
            }), 400
        
        if not data.get('schedule_expr'):
            return jsonify({
                'success': False,
                'message': '调度表达式不能为空'
            }), 400
        
        # 创建任务对象
        task = ScheduledTask(
            task_name=data['task_name'],
            task_type=data['task_type'],
            schedule_expr=data['schedule_expr'],
            use_default_config=data.get('use_default_config', True),
            ip_ranges=data.get('ip_ranges', ''),
            ports=data.get('ports', ''),
            exclude_ips=data.get('exclude_ips', ''),
            max_workers=data.get('max_workers', 10),
            ulimit=data.get('ulimit', 15000),
            timeout=data.get('timeout', 700),
            is_active=data.get('is_active', True)
        )
        
        # 添加到调度器
        try:
            task_id = scheduler.add_task(task)
        except Exception as add_err:
            return jsonify({
                'success': False,
                'message': f'任务已创建但添加到调度器失败: {str(add_err)}。请检查调度表达式是否正确。'
            }), 500
        
        return jsonify({
            'success': True,
            'data': {'id': task_id},
            'message': '定时任务创建成功'
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@scheduler_bp.route('/api/scheduler/tasks/<int:task_id>', methods=['PUT'])
@require_auth
def update_task(task_id):
    """更新定时任务"""
    try:
        data = request.get_json()
        
        # 检查任务是否存在
        task = scheduler.db.get_scheduled_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404
        
        # 更新字段
        update_fields = {}
        allowed_fields = [
            'task_name', 'task_type', 'schedule_expr', 'use_default_config',
            'ip_ranges', 'ports', 'exclude_ips', 'max_workers', 'ulimit',
            'timeout', 'is_active'
        ]
        
        for field in allowed_fields:
            if field in data:
                update_fields[field] = data[field]
        
        if not update_fields:
            return jsonify({
                'success': False,
                'message': '没有要更新的字段'
            }), 400
        
        # 更新任务
        scheduler.update_task(task_id, **update_fields)
        
        return jsonify({
            'success': True,
            'message': '定时任务更新成功'
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@scheduler_bp.route('/api/scheduler/tasks/<int:task_id>', methods=['DELETE'])
@require_auth
def delete_task(task_id):
    """删除定时任务"""
    try:
        # 检查任务是否存在
        task = scheduler.db.get_scheduled_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404
        
        # 删除任务
        success = scheduler.remove_task(task_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '定时任务删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '删除失败'
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@scheduler_bp.route('/api/scheduler/tasks/<int:task_id>/toggle', methods=['POST'])
@require_auth
def toggle_task(task_id):
    """启用/禁用定时任务"""
    try:
        # 检查任务是否存在
        task = scheduler.db.get_scheduled_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404
        
        # 切换状态
        success = scheduler.toggle_task(task_id)
        
        if success:
            new_status = not task.is_active
            return jsonify({
                'success': True,
                'message': f'任务已{"启用" if new_status else "禁用"}'
            })
        else:
            return jsonify({
                'success': False,
                'message': '操作失败'
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@scheduler_bp.route('/api/scheduler/tasks/<int:task_id>/run', methods=['POST'])
@require_auth
def run_now(task_id):
    """立即执行定时任务"""
    try:
        # 检查任务是否存在
        task = scheduler.db.get_scheduled_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404
        
        # 立即执行
        scan_task_id = scheduler.run_task_now(task_id)
        
        if scan_task_id:
            return jsonify({
                'success': True,
                'data': {'scan_task_id': scan_task_id},
                'message': '任务已开始执行'
            })
        else:
            return jsonify({
                'success': False,
                'message': '任务执行失败'
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@scheduler_bp.route('/api/scheduler/tasks/<int:task_id>/stop', methods=['POST'])
@require_auth
def stop_task(task_id):
    """停止正在运行的定时任务"""
    try:
        # 检查任务是否存在
        task = scheduler.db.get_scheduled_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404
        
        # 停止任务
        success = scheduler.stop_task(task_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '任务已停止'
            })
        else:
            return jsonify({
                'success': False,
                'message': '任务未在运行或停止失败'
            }), 400
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
