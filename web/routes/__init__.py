"""
路由蓝图注册
统一管理所有 API 路由
"""
from flask import Blueprint


def register_routes(app):
    """注册所有路由蓝图到 Flask 应用"""
    from web.routes.config_routes import config_bp
    from web.routes.scan_routes import scan_bp
    from web.routes.report_routes import report_bp
    from web.routes.dashboard_routes import dashboard_bp
    from web.api.auth_api import auth_bp
    from web.api.scheduler_api import scheduler_bp

    app.register_blueprint(config_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(scheduler_bp)
