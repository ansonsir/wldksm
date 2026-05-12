"""
Flask Web 后端主应用 (v4.0 Blueprint 架构)
提供 RESTful API 供前端调用
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask
from flask_cors import CORS
from flask_talisman import Talisman
from flask_socketio import SocketIO

from web.rate_limit import limiter

from core.config import ConfigManager
from core.database import DatabaseManager
from web.mail_service import ReportMailer
from web.services.scan_service import ScanService
from web.services.auth_service import AuthService
from web.scheduler import TaskScheduler
from web.webhook_service import get_webhook_notifier, WebhookConfig
from web.api import scheduler_api
from web.routes import register_routes


def create_app():
    """应用工厂函数"""
    FRONTEND_DIST = PROJECT_ROOT / 'web' / 'frontend' / 'dist'
    app = Flask(__name__, static_folder=str(FRONTEND_DIST / 'assets'), template_folder='templates')
    CORS(app, resources={
        r"/api/v1/*": {
            "origins": ["http://localhost:5000", "http://127.0.0.1:5000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["Content-Disposition"],
            "max_age": 3600,
        }
    })
    # 持久化 Flask session secret key（避免重启后 session 失效导致 TOTP 登录中断）
    _secret_file = PROJECT_ROOT / 'web' / 'data' / '.flask_secret'
    if _secret_file.exists():
        app.secret_key = _secret_file.read_text().strip()
    else:
        app.secret_key = os.urandom(32).hex()
        _secret_file.parent.mkdir(parents=True, exist_ok=True)
        _secret_file.write_text(app.secret_key)

    # --- 创建服务实例 ---
    db_manager = DatabaseManager()
    config_manager = ConfigManager(db_manager=db_manager)
    mailer = ReportMailer(db_manager=db_manager)

    # 定时任务调度器（先创建，再注入 scan_service）
    scheduler = TaskScheduler(db_manager=db_manager, scan_service=None, config_manager=config_manager)
    scan_service = ScanService(db_manager=db_manager, config_manager=config_manager, mailer=mailer, scheduler=scheduler)
    scheduler.scan_service = scan_service

    auth_service = AuthService(db_manager=db_manager)

    # --- 初始化 SocketIO ---
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    app.config['socketio'] = socketio

    # Socket.IO 事件处理
    @socketio.on('join')
    def handle_join(data):
        from flask_socketio import join_room
        room = data.get('room', '')
        if room:
            join_room(room)

    @socketio.on('leave')
    def handle_leave(data):
        from flask_socketio import leave_room
        room = data.get('room', '')
        if room:
            leave_room(room)

    # --- 将服务实例存入 app.config，供 Blueprint 路由通过 current_app.config 访问 ---
    app.config['project_root'] = PROJECT_ROOT
    app.config['config_manager'] = config_manager
    app.config['db_manager'] = db_manager
    app.config['mailer'] = mailer
    app.config['scan_service'] = scan_service
    app.config['scheduler'] = scheduler
    app.config['auth_service'] = auth_service

    # --- 初始化默认管理员 ---
    _init_default_admin(db_manager, auth_service)

    # --- 初始化调度器 API ---
    scheduler_api.init_scheduler_api(scheduler)

    # --- 加载 Webhook 配置到运行时 ---
    _load_webhook_configs(db_manager)

    # --- 注册所有路由蓝图 ---
    register_routes(app)

    return app


def _init_default_admin(db_manager, auth_service):
    """创建默认管理员账户（如果不存在）"""
    admin = db_manager.get_user_by_username('admin')
    if not admin:
        import secrets
        import logging
        logger = logging.getLogger(__name__)
        password = ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*') for _ in range(12))
        password_hash = auth_service.hash_password(password)
        db_manager.create_user(
            username='admin',
            password_hash=password_hash,
            email='admin@localhost',
            is_admin=True
        )
        # 安全：将初始凭据写入受保护文件（而非打印到控制台/日志）
        credential_file = Path(__file__).parent.parent / 'data' / '.admin_initial_credentials'
        credential_file.parent.mkdir(parents=True, exist_ok=True)
        credential_file.write_text(
            f"Username: admin\nPassword: {password}\n"
            f"IMPORTANT: Login and change password immediately, then delete this file.\n"
        )
        if os.name == 'posix':
            credential_file.chmod(0o600)
        logger.warning(
            "="*70 + "\n"
            "【首次启动】默认管理员账户已创建\n"
            "用户名: admin\n"
            f"初始凭据文件: {credential_file}\n"
            "请立即登录并修改密码，随后删除该凭据文件！\n"
            "="*70
        )
    else:
        print("管理员账户已存在")


def _load_webhook_configs(db_manager):
    """从数据库加载 Webhook 配置到运行时通知器"""
    try:
        notifier = get_webhook_notifier()
        configs = db_manager.get_webhook_configs()
        for cfg in configs:
            platform = cfg.get('platform', '')
            if not platform:
                continue
            wc = WebhookConfig(
                platform=platform,
                webhook_url=cfg.get('webhook_url', ''),
                secret=cfg.get('secret', ''),
                is_active=bool(cfg.get('is_active', False)),
                notify_on_complete=bool(cfg.get('notify_on_complete', True)),
                notify_on_high_risk=bool(cfg.get('notify_on_high_risk', True)),
            )
            if wc.is_active and wc.webhook_url:
                notifier.add_config(platform, wc)
        print(f"[Webhook] 已加载 {len(notifier.configs)} 个通知渠道")
    except Exception as e:
        print(f"[Webhook] 加载配置失败: {e}")


app = create_app()


if __name__ == '__main__':
    import logging
    import sys
    from core.utils import setup_logging

    config_manager = app.config['config_manager']
    db_manager = app.config['db_manager']
    scheduler = app.config['scheduler']

    # 配置日志系统
    config = config_manager.get_config()
    setup_logging(
        log_file=config.log_file,
        console_output=True,
        file_mode='a'
    )

    # 初始化数据库
    db_manager.init_default_data()

    # 安全中间件
    Talisman(app, content_security_policy={
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline'",
        'style-src': "'self' 'unsafe-inline'",
        'img-src': "'self' data:",
        'report-uri': '/api/v1/csp-report',
    }, force_https=False)

    limiter.init_app(app)

    # 启动定时任务调度器
    print("[调度器] 正在启动定时任务调度器...")
    sys.stdout.flush()
    try:
        scheduler.start()
        print(f"[调度器] 启动成功! 运行状态: {scheduler.scheduler.running}")
        jobs = scheduler.scheduler.get_jobs()
        print(f"[调度器] 已加载 {len(jobs)} 个定时任务")
        for job in jobs:
            next_run = getattr(job, 'next_run_time', None)
            print(f"[调度器]   - {job.id}: next_run_time={next_run}")
        sys.stdout.flush()
    except Exception as e:
        print(f"[调度器] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()

    print("""
╔═══════════════════════════════════════════════════════════╗
║              网络端口扫描工具 Web 服务 v4.0               ║
║                                                           ║
║  访问地址: http://0.0.0.0:5000                           ║
╚═══════════════════════════════════════════════════════════╝
    """)
    sys.stdout.flush()

    try:
        socketio = app.config['socketio']
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    finally:
        scheduler.stop()
