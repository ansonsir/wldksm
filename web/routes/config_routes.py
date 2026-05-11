"""
配置相关路由
/api/config, /api/scan/defaults, /api/scan/areas, /api/mail/*
"""
import logging
from flask import Blueprint, request, jsonify, current_app
from web.middleware.auth_middleware import require_auth
from web.mail_service import MailConfig


config_bp = Blueprint('config', __name__)


def _get_services():
    """获取全局服务实例"""
    return (
        current_app.config['config_manager'],
        current_app.config['db_manager'],
        current_app.config['mailer'],
    )


@config_bp.route('/api/config', methods=['GET'])
@require_auth
def get_config():
    """获取当前配置"""
    try:
        config_manager, _, _ = _get_services()
        config = config_manager.get_config()
        return jsonify({
            'success': True,
            'data': {
                'ip_range_file': config.ip_range_file,
                'ports_file': config.ports_file,
                'exclude_ips_file': config.exclude_ips_file,
                'template_file': config.template_file,
                'max_workers': config.max_workers,
                'ulimit': config.ulimit,
                'timeout': config.timeout,
                'batch_size': config.batch_size,
                'smtp_server': config.smtp_server,
                'smtp_port': config.smtp_port,
                'smtp_user': config.smtp_user,
                'smtp_ssl': config.smtp_ssl,
                'default_sender': config.default_sender,
                'default_recipients': config.default_recipients,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/config', methods=['POST'])
@require_auth
def update_config():
    """更新配置"""
    try:
        config_manager, _, mailer = _get_services()
        data = request.get_json()
        config = config_manager.get_config()

        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)

        config_manager.save_to_yaml()

        if any(k in data for k in ['smtp_server', 'smtp_port', 'smtp_user', 'smtp_password']):
            mail_config = MailConfig(
                smtp_server=config.smtp_server,
                smtp_port=config.smtp_port,
                smtp_user=config.smtp_user,
                smtp_password=config.smtp_password,
                smtp_ssl=config.smtp_ssl,
                default_sender=config.default_sender,
                default_recipients=config.default_recipients,
            )
            mailer.save_to_db(mail_config)
            mailer.config = mail_config

        return jsonify({'success': True, 'message': '配置已更新'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/scan/defaults', methods=['GET'])
@require_auth
def get_scan_defaults():
    """获取扫描默认参数（从系统配置文件读取）"""
    try:
        config_manager, _, _ = _get_services()
        config = config_manager.get_config()
        logger = logging.getLogger('API')

        from core.utils import load_ip_ranges, load_text_file

        ip_ranges_str = ''
        try:
            ip_ranges_list = load_ip_ranges(config.ip_range_file, logger)
            ip_ranges_str = '\n'.join(ip_ranges_list)
        except Exception as e:
            logger.warning(f"加载IP范围文件失败: {e}")

        ports_str = ''
        try:
            ports_str = load_text_file(config.ports_file, logger, "端口")
        except Exception as e:
            logger.warning(f"加载端口文件失败: {e}")

        exclude_ips_str = ''
        try:
            exclude_ips_str = load_text_file(config.exclude_ips_file, logger, "排除IP")
        except Exception as e:
            logger.warning(f"加载排除IP文件失败: {e}")

        return jsonify({
            'success': True,
            'data': {
                'ip_ranges': ip_ranges_str,
                'ports': ports_str,
                'exclude_ips': exclude_ips_str,
                'max_workers': config.max_workers,
                'ulimit': config.ulimit,
                'timeout': config.timeout,
                'batch_size': config.batch_size,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/scan/areas', methods=['GET'])
@require_auth
def get_scan_areas():
    """获取扫描区域列表"""
    try:
        _, db_manager, _ = _get_services()
        areas = db_manager.get_scan_areas()
        return jsonify({
            'success': True,
            'data': [
                {
                    'id': a.id,
                    'name': a.area_name,
                    'description': a.description,
                    'scan_ports': a.scan_ports,
                    'is_full_scan': a.is_full_scan
                }
                for a in areas
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/mail/config', methods=['GET'])
@require_auth
def get_mail_config():
    """获取邮件配置"""
    try:
        _, db_manager, _ = _get_services()
        settings = db_manager.get_email_settings()
        if settings:
            return jsonify({
                'success': True,
                'data': {
                    'smtp_server': settings.smtp_server,
                    'smtp_port': settings.smtp_port,
                    'smtp_user': settings.smtp_user,
                    'smtp_password': settings.smtp_password,
                    'smtp_ssl': bool(settings.smtp_ssl),
                    'skip_login': bool(settings.skip_login),
                    'default_sender': settings.default_sender,
                    'default_recipients': settings.default_recipients,
                }
            })
        return jsonify({'success': True, 'data': {}})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/mail/config', methods=['POST'])
@require_auth
def save_mail_config():
    """保存邮件配置"""
    try:
        _, _, mailer = _get_services()
        data = request.get_json()
        config = MailConfig(
            smtp_server=data.get('smtp_server', ''),
            smtp_port=data.get('smtp_port', 587),
            smtp_user=data.get('smtp_user', ''),
            smtp_password=data.get('smtp_password', ''),
            smtp_ssl=data.get('smtp_ssl', True),
            skip_login=data.get('skip_login', False),
            default_sender=data.get('default_sender', ''),
            default_recipients=data.get('default_recipients', ''),
        )
        success = mailer.save_to_db(config)
        if success:
            mailer.config = config
            return jsonify({'success': True, 'message': '邮件配置已保存'})
        return jsonify({'success': False, 'message': '保存失败'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/mail/test', methods=['POST'])
@require_auth
def test_mail():
    """测试邮件配置"""
    try:
        _, _, mailer = _get_services()
        data = request.get_json()
        config = MailConfig(
            smtp_server=data.get('smtp_server', ''),
            smtp_port=data.get('smtp_port', 587),
            smtp_user=data.get('smtp_user', ''),
            smtp_password=data.get('smtp_password', ''),
            smtp_ssl=data.get('smtp_ssl', True),
            skip_login=data.get('skip_login', False),
        )
        success, message = mailer.test_connection(config)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== Webhook 配置 ====================

@config_bp.route('/api/webhook/configs', methods=['GET'])
@require_auth
def get_webhook_configs():
    """获取所有 Webhook 配置"""
    try:
        _, db_manager, _ = _get_services()
        configs = db_manager.get_webhook_configs()
        return jsonify({'success': True, 'data': configs})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/webhook/configs', methods=['POST'])
@require_auth
def save_webhook_config():
    """保存 Webhook 配置"""
    try:
        _, db_manager, _ = _get_services()
        data = request.get_json() or {}
        platform = data.get('platform', '')
        if platform not in ('dingtalk', 'wecom', 'feishu'):
            return jsonify({'success': False, 'message': '不支持的平台类型'}), 400
        
        success = db_manager.save_webhook_config(platform, data)
        if success:
            from web.webhook_service import get_webhook_notifier, WebhookConfig
            notifier = get_webhook_notifier()
            config = WebhookConfig(
                platform=platform,
                webhook_url=data.get('webhook_url', ''),
                secret=data.get('secret', ''),
                is_active=data.get('is_active', False),
                notify_on_complete=data.get('notify_on_complete', True),
                notify_on_high_risk=data.get('notify_on_high_risk', True),
            )
            notifier.add_config(platform, config)
            return jsonify({'success': True, 'message': 'Webhook 配置已保存'})
        return jsonify({'success': False, 'message': '保存失败'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/webhook/configs/<platform>', methods=['DELETE'])
@require_auth
def delete_webhook_config(platform):
    """删除 Webhook 配置"""
    try:
        _, db_manager, _ = _get_services()
        db_manager.delete_webhook_config(platform)
        from web.webhook_service import get_webhook_notifier
        get_webhook_notifier().remove_config(platform)
        return jsonify({'success': True, 'message': 'Webhook 配置已删除'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@config_bp.route('/api/webhook/test', methods=['POST'])
@require_auth
def test_webhook():
    """测试 Webhook 通知"""
    try:
        data = request.get_json() or {}
        platform = data.get('platform', '')
        webhook_url = data.get('webhook_url', '')
        secret = data.get('secret', '')
        
        if not platform or not webhook_url:
            return jsonify({'success': False, 'message': '缺少必要参数'}), 400
        
        from web.webhook_service import WebhookNotifier, WebhookConfig
        notifier = WebhookNotifier()
        config = WebhookConfig(
            platform=platform,
            webhook_url=webhook_url,
            secret=secret,
            is_active=True,
        )
        notifier.add_config(platform, config)
        
        test_info = {
            'total_hosts': 5,
            'open_ports': 12,
            'high_risk_count': 2,
            'duration': '3分钟20秒',
            'scan_time': '测试消息 - 请忽略',
        }
        results = notifier.send_scan_result(test_info)
        
        all_success = all(success for success, _ in results.values())
        return jsonify({
            'success': all_success,
            'data': {
                platform: {'success': s, 'message': m} 
                for platform, (s, m) in results.items()
            },
            'message': '测试消息已发送' if all_success else '部分平台发送失败'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== 扫描策略模板 ====================

# 预定义的扫描策略模板
SCAN_POLICIES = {
    'quick': {
        'id': 'quick',
        'name': '快速扫描',
        'description': '扫描最常用的高危端口（22,80,443,3389,3306等30个端口），速度快，适合日常巡检',
        'icon': 'Lightning',
        'ports': '21,22,23,25,53,80,110,135,139,143,443,445,873,993,995,1433,1521,2181,2375,3306,3389,5432,5900,6379,8080,8443,8888,9090,11211,27017',
        'max_workers': 32,
        'ulimit': 15000,
        'batch_size': 10000,
        'timeout': 300,
        'color': '#409eff'
    },
    'deep': {
        'id': 'deep',
        'name': '深度扫描',
        'description': '全端口扫描（1-65535），使用更多线程和资源，适合安全审计和全面资产发现',
        'icon': 'Search',
        'ports': '1-65535',
        'max_workers': 48,
        'ulimit': 32768,
        'batch_size': 15000,
        'timeout': 700,
        'color': '#e6a23c'
    },
    'compliance': {
        'id': 'compliance',
        'name': '合规扫描',
        'description': '扫描等保合规要求的标准端口（常见Web、数据库、远程管理端口），控制资源占用',
        'icon': 'Checked',
        'ports': '21,22,23,25,53,80,110,135,139,143,443,445,993,995,1433,1521,3306,3389,5432,5900,6379,8080,8443,27017',
        'max_workers': 24,
        'ulimit': 10000,
        'batch_size': 8000,
        'timeout': 500,
        'color': '#67c23a'
    }
}


@config_bp.route('/api/scan/policies', methods=['GET'])
@require_auth
def get_scan_policies():
    """获取扫描策略模板列表"""
    try:
        return jsonify({
            'success': True,
            'data': list(SCAN_POLICIES.values())
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
