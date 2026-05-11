"""
认证中间件模块
提供JWT认证装饰器，保护需要登录的API接口
"""
import functools
import logging
from flask import request, jsonify, current_app
from typing import Optional

logger = logging.getLogger("AuthMiddleware")


def require_auth(f):
    """
    JWT认证装饰器 - 保护需要登录的API
    
    使用方法:
        @app.route('/api/protected')
        @require_auth
        def protected_route():
            user_id = request.current_user_id
            # ...
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # 获取token
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({
                'success': False,
                'error': '缺少认证信息'
            }), 401
        
        # 解析Bearer token
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({
                'success': False,
                'error': '认证格式错误'
            }), 401
        
        token = parts[1]
        
        # 验证token
        auth_service = current_app.config['auth_service']
        payload = auth_service.verify_session(token)
        
        if not payload:
            return jsonify({
                'success': False,
                'error': '认证失效，请重新登录'
            }), 401
        
        # 将用户ID注入到request对象
        request.current_user_id = payload['user_id']
        request.current_token = token
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_admin(f):
    """
    管理员权限装饰器
    
    使用方法:
        @app.route('/api/admin/users')
        @require_admin
        def admin_users():
            # ...
    """
    @functools.wraps(f)
    @require_auth
    def decorated_function(*args, **kwargs):
        # 检查用户是否为管理员
        db_manager = current_app.config['db_manager']
        user = db_manager.get_user_by_id(request.current_user_id)
        
        if not user or not user.is_admin:
            return jsonify({
                'success': False,
                'error': '需要管理员权限'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_current_user():
    """
    获取当前登录用户
    
    Returns:
        User对象或None
    """
    if not hasattr(request, 'current_user_id'):
        return None
    
    db_manager = current_app.config['db_manager']
    return db_manager.get_user_by_id(request.current_user_id)
