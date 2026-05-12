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
    
    特殊处理：
        - 首次登录（first_login=True）的用户只能访问 /change-password 和 /csrf-token
        - 改密 Token（type='change_password'）只能用于 /change-password
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
        
        # 也接受改密 Token（仅用于 /change-password）
        token_type = None
        if not payload:
            payload = auth_service.verify_change_password_token(token)
            if payload:
                token_type = 'change_password'
        
        if not payload:
            return jsonify({
                'success': False,
                'error': '认证失效，请重新登录'
            }), 401
        
        # 将用户ID注入到request对象
        request.current_user_id = payload['user_id']
        request.current_token = token
        
        # 检查是否首次登录（必须强制修改密码）
        db_manager = current_app.config['db_manager']
        user = db_manager.get_user_by_id(payload['user_id'])
        if user and user.first_login:
            # 只允许访问 change-password 和 csrf-token
            if not request.path.endswith('/change-password') and not request.path.endswith('/csrf-token'):
                return jsonify({
                    'success': False,
                    'error': '首次登录必须修改密码后才能继续操作'
                }), 403
        
        # 改密 Token 只能用于 /change-password
        if token_type == 'change_password' and not request.path.endswith('/change-password'):
            return jsonify({
                'success': False,
                'error': '请先修改密码'
            }), 403
        
        # 标记 Token 类型，供 require_csrf 判断是否跳过 CSRF
        request._token_type = token_type
        
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


def require_csrf(f):
    """
    CSRF保护装饰器 - 用于状态变更请求（POST/PUT/DELETE）
    
    需要客户端在 X-CSRF-Token 头中提供有效的CSRF Token。
    与 @require_auth 配合使用（先认证再验证CSRF）。
    
    使用方法:
        @app.route('/api/protected', methods=['POST'])
        @require_auth
        @require_csrf
        def protected_route():
            ...
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # GET/HEAD/OPTIONS 请求不需要CSRF保护
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return f(*args, **kwargs)
        
        # 改密 Token 跳过 CSRF 检查（临时 Token 已限制用途，无需额外 CSRF）
        if getattr(request, '_token_type', None) == 'change_password':
            return f(*args, **kwargs)
        
        csrf_token = request.headers.get('X-CSRF-Token', '')
        if not csrf_token:
            return jsonify({
                'success': False,
                'error': '缺少CSRF保护Token'
            }), 403
        
        auth_service = current_app.config['auth_service']
        if not auth_service.verify_csrf_token(csrf_token):
            return jsonify({
                'success': False,
                'error': 'CSRF Token无效或已过期'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function
