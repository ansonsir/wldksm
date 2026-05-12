"""
认证API接口
提供登录、注册、验证码、TOTP等认证相关接口
"""
import logging
from flask import Blueprint, request, jsonify, current_app

from web.utils import success_response, error_response
from web.middleware.auth_middleware import require_auth, require_admin, require_csrf
from web.security_config import validate_username, validate_password_strength
from web.rate_limit import limiter

logger = logging.getLogger("AuthAPI")


def _auth_service():
    return current_app.config['auth_service']

def _db_manager():
    return current_app.config['db_manager']

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')


@auth_bp.route('/captcha', methods=['POST'])
@limiter.limit("10 per minute")
def get_captcha():
    """获取图形验证码"""
    try:
        # 获取客户端真实IP
        client_ip = (request.headers.get('X-Forwarded-For', '') or '').split(',')[0].strip()
        if not client_ip:
            client_ip = request.remote_addr or "unknown"
        
        captcha_id, captcha_image = _auth_service().generate_captcha(client_ip)
        
        if not captcha_id:
            return error_response("验证码请求过于频繁，请稍后再试", 429)
        
        return success_response({
            'captcha_id': captcha_id,
            'captcha_image': captcha_image
        })
    except Exception as e:
        logger.error(f"生成验证码失败: {e}")
        return error_response("生成验证码失败", 500)


@auth_bp.route('/csrf-token', methods=['GET'])
@require_auth
def get_csrf_token():
    """
    获取CSRF保护Token
    前端在登录后调用此接口获取CSRF Token，
    后续所有状态变更请求（POST/PUT/DELETE）需在X-CSRF-Token头中携带
    """
    try:
        csrf_token = _auth_service().create_csrf_token()
        return success_response({'csrf_token': csrf_token})
    except Exception as e:
        logger.error(f"生成CSRF Token失败: {e}")
        return error_response("生成CSRF Token失败", 500)


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    """
    用户登录（第一步：验证用户名密码+验证码）
    
    请求体:
    {
        "username": "admin",
        "password": "password123",
        "captcha_id": "...",
        "captcha_code": "ABCD"
    }
    """
    try:
        auth_service = _auth_service()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        captcha_id = data.get('captcha_id', '')
        captcha_code = data.get('captcha_code', '').strip()
        
        # 参数验证
        if not username or not password:
            return error_response("用户名和密码不能为空", 400)
        
        if not captcha_id or not captcha_code:
            return error_response("请输入验证码", 400)
        
        # 获取IP和User-Agent（正确获取客户端真实IP）
        ip_address = (request.headers.get('X-Forwarded-For', '') or '').split(',')[0].strip()
        if not ip_address:
            ip_address = request.remote_addr or "unknown"
        user_agent = request.headers.get('User-Agent', 'unknown')
        
        # 执行认证（传入真实 IP 用于安全审计和暴力破解防护）
        result = auth_service.authenticate(username, password, captcha_id, captcha_code,
                                           ip_address=ip_address, user_agent=user_agent)
        
        if result['success']:
            if result.get('need_change_password'):
                # 首次登录：必须修改密码，不签发完整 Token
                return success_response({
                    'need_change_password': True,
                    'user_id': result['user_id'],
                    'change_password_token': result['change_password_token'],
                    'user_info': result['user_info']
                }, message="首次登录，请先修改密码")
            elif result.get('need_totp'):
                # 生成 TOTP 临时会话 Token（替代 Flask session，避免浏览器 cookie 策略问题）
                totp_session_token = auth_service.create_totp_session_token(
                    result['user_id'], ip_address, user_agent
                )
                return success_response({
                    'need_totp': True,
                    'user_id': result['user_id'],
                    'totp_session_token': totp_session_token
                }, message="需要进行TOTP验证")
            elif result.get('need_totp_setup'):
                # 需要设置TOTP（包括首次登录和管理员重置后）
                return success_response({
                    'token': result['token'],
                    'refresh_token': result['refresh_token'],
                    'user_info': result['user_info'],
                    'need_totp_setup': True  # 添加这个字段
                }, message="登录成功")
            else:
                return success_response({
                    'token': result['token'],
                    'refresh_token': result['refresh_token'],
                    'user_info': result['user_info']
                }, message="登录成功")
        else:
            return error_response(
                result.get('error', '登录失败'), 
                401,
                extra={'remaining_attempts': result.get('remaining_attempts', 0)}
            )
            
    except Exception as e:
        logger.error(f"登录失败: {e}", exc_info=True)
        return error_response("登录失败，请稍后重试", 500)


@auth_bp.route('/login/totp', methods=['POST'])
@limiter.limit("5 per minute")
def login_totp():
    """
    TOTP验证（第二步）
    
    请求体:
    {
        "totp_token": "123456",
        "totp_session_token": "eyJ..."
    }
    """
    try:
        auth_service = _auth_service()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        totp_code = data.get('totp_token', '').strip()
        totp_session_token = data.get('totp_session_token', '').strip()
        
        if not totp_code:
            return error_response("请输入动态验证码", 400)
        
        if not totp_session_token:
            return error_response("会话已过期，请重新登录", 400)
        
        # 验证 TOTP 会话 Token（替代 Flask session）
        session_data = auth_service.verify_totp_session_token(totp_session_token)
        if not session_data:
            return error_response("会话已过期，请重新登录", 400)
        
        user_id = session_data['user_id']
        ip_address = session_data['ip_address']
        user_agent = session_data['user_agent']
        
        # 执行TOTP验证
        result = auth_service.verify_totp_login(user_id, totp_code, ip_address, user_agent)
        
        if result['success']:
            return success_response({
                'token': result['token'],
                'refresh_token': result['refresh_token'],
                'user_info': result['user_info']
            }, message="登录成功")
        else:
            return error_response(result.get('error', 'TOTP验证失败'), 401)
            
    except Exception as e:
        logger.error(f"TOTP登录失败: {e}", exc_info=True)
        return error_response("登录失败，请稍后重试", 500)


@auth_bp.route('/logout', methods=['POST'])
@require_auth
@require_csrf
def logout():
    """用户登出"""
    try:
        auth_service = _auth_service()
        
        # 撤销token
        auth_service.revoke_session(request.current_token)
        
        return success_response(message="已退出登录")
        
    except Exception as e:
        logger.error(f"登出失败: {e}")
        return error_response("登出失败", 500)


@auth_bp.route('/refresh', methods=['POST'])
def refresh_token():
    """刷新token"""
    try:
        auth_service = _auth_service()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        refresh_token = data.get('refresh_token', '')
        
        if not refresh_token:
            return error_response("缺少refresh_token", 400)
        
        result = auth_service.refresh_session(refresh_token)
        
        if result:
            return success_response(result, message="Token刷新成功")
        else:
            return error_response("Refresh token无效或已过期", 401)
            
    except Exception as e:
        logger.error(f"刷新Token失败: {e}")
        return error_response("刷新Token失败", 500)


@auth_bp.route('/profile', methods=['GET'])
@require_auth
def get_profile():
    """获取当前用户信息"""
    try:
        db_manager = _db_manager()
        
        user = db_manager.get_user_by_id(request.current_user_id)
        
        if not user:
            return error_response("用户不存在", 404)
        
        return success_response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin,
            'totp_enabled': user.totp_enabled,
            'last_login': user.last_login,
            'created_at': user.created_at
        })
        
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        return error_response("获取用户信息失败", 500)


@auth_bp.route('/profile', methods=['PUT'])
@require_auth
def update_profile():
    """更新用户信息"""
    try:
        db_manager = _db_manager()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        # 只允许更新邮箱
        email = data.get('email', '').strip()
        
        if email:
            if len(email) > 100:
                return error_response("邮箱地址过长", 400)
            
            # TODO: 更新邮箱
            # db_manager.update_user_email(request.current_user_id, email)
        
        return success_response(message="更新成功")
        
    except Exception as e:
        logger.error(f"更新用户信息失败: {e}")
        return error_response("更新失败", 500)


@auth_bp.route('/change-password', methods=['POST'])
@require_auth
@require_csrf
def change_password():
    """修改密码"""
    try:
        auth_service = _auth_service(); db_manager = _db_manager()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        first_login = data.get('first_login', False)  # 是否首次登录
        
        if not new_password:
            return error_response("新密码不能为空", 400)
        
        # 验证新密码强度
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            return error_response(error_msg, 400)
        
        # 获取当前用户
        user = db_manager.get_user_by_id(request.current_user_id)
        
        # 如果不是首次登录，验证旧密码
        if not first_login:
            if not old_password:
                return error_response("旧密码不能为空", 400)
            if not auth_service.verify_password(old_password, user.password_hash):
                return error_response("旧密码错误", 400)
        
        # 更新密码
        new_password_hash = auth_service.hash_password(new_password)
        db_manager.reset_user_password(user.id, new_password_hash)
        
        logger.info(f"用户修改密码成功: {user.username} (首次登录: {first_login})")
        
        # 首次登录改密后：撤销当前会话，强制用户重新登录
        if first_login:
            auth_service.revoke_session(request.current_token)
            return success_response({
                'need_relogin': True
            }, message="密码修改成功，请重新登录")
        
        return success_response(message="密码修改成功")
        
    except Exception as e:
        logger.error(f"修改密码失败: {e}")
        return error_response("修改密码失败", 500)


@auth_bp.route('/setup-totp', methods=['POST'])
@require_auth
def setup_totp():
    """启用TOTP（返回二维码和密钥）"""
    try:
        auth_service = _auth_service(); db_manager = _db_manager()
        
        user = db_manager.get_user_by_id(request.current_user_id)
        
        # 生成TOTP密钥
        totp_secret = auth_service.generate_totp_secret()
        
        # 生成二维码
        qr_code = auth_service.generate_totp_qr_code(user.username, totp_secret)
        
        # 临时存储到数据库（等待验证）
        db_manager.update_user_totp(user.id, totp_secret, False)  # 先不启用
        
        return success_response({
            'secret': totp_secret,
            'qr_code': qr_code
        }, message="请扫描二维码或手动输入密钥")
        
    except Exception as e:
        logger.error(f"设置TOTP失败: {e}")
        return error_response("设置TOTP失败", 500)


@auth_bp.route('/verify-totp-setup', methods=['POST'])
@require_auth
def verify_totp_setup():
    """验证TOTP设置"""
    try:
        auth_service = _auth_service(); db_manager = _db_manager()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        totp_token = data.get('totp_token', '').strip()
        
        if not totp_token:
            return error_response("请输入动态验证码", 400)
        
        # 从数据库获取当前用户的TOTP密钥
        user = db_manager.get_user_by_id(request.current_user_id)
        if not user.totp_secret:
            return error_response("请先设置TOTP", 400)
        
        # 验证TOTP
        success, error_msg = auth_service.verify_totp(user.totp_secret, totp_token)
        if not success:
            return error_response(error_msg, 400)
        
        # 启用TOTP，并清除totp_reset标志
        with db_manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET totp_enabled = 1, totp_reset = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (user.id,)
            )
        
        logger.info(f"用户启用TOTP成功: {user.username}")
        
        return success_response(message="TOTP启用成功")
        
    except Exception as e:
        logger.error(f"验证TOTP设置失败: {e}")
        return error_response("验证失败", 500)


@auth_bp.route('/disable-totp', methods=['POST'])
@require_auth
@require_csrf
def disable_totp():
    """禁用TOTP（仅管理员）"""
    try:
        db_manager = _db_manager()
        
        # 验证是否为管理员
        user = db_manager.get_user_by_id(request.current_user_id)
        if not user.is_admin:
            return error_response("只有管理员可以禁用双因素认证", 403)
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        totp_token = data.get('totp_token', '').strip()
        
        if not totp_token:
            return error_response("请输入动态验证码", 400)
        
        # 验证当前TOTP
        if not user.totp_secret:
            return error_response("TOTP未启用", 400)
        
        auth_service = _auth_service()
        success, error_msg = auth_service.verify_totp(user.totp_secret, totp_token)
        if not success:
            return error_response(error_msg, 400)
        
        # 禁用TOTP
        db_manager.update_user_totp(user.id, None, False)
        
        logger.info(f"管理员禁用TOTP: {user.username}")
        
        return success_response(message="TOTP已禁用")
        
    except Exception as e:
        logger.error(f"禁用TOTP失败: {e}")
        return error_response("禁用失败", 500)


@auth_bp.route('/login-logs', methods=['GET'])
@require_admin
def get_login_logs():
    """获取登录日志（管理员）"""
    try:
        db_manager = _db_manager()
        
        limit = request.args.get('limit', 100, type=int)
        user_id = request.args.get('user_id', type=int)
        
        logs = db_manager.get_login_logs(limit=limit, user_id=user_id)
        
        log_list = []
        for log in logs:
            log_list.append({
                'id': log.id,
                'user_id': log.user_id,
                'username': log.username,
                'ip_address': log.ip_address,
                'user_agent': log.user_agent,
                'login_status': log.login_status,
                'failure_reason': log.failure_reason,
                'created_at': log.created_at
            })
        
        return success_response(log_list)
        
    except Exception as e:
        logger.error(f"获取登录日志失败: {e}")
        return error_response("获取登录日志失败", 500)


# ==================== 用户管理 API（管理员） ====================

@auth_bp.route('/users', methods=['GET'])
@require_admin
def get_users():
    """获取用户列表（管理员）"""
    try:
        db_manager = _db_manager()
        from core.database import User
        
        # 查询所有用户
        with db_manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY id ASC")
            rows = cursor.fetchall()
            
            users = []
            for row in rows:
                users.append({
                    'id': row['id'],
                    'username': row['username'],
                    'email': row['email'],
                    'totp_enabled': bool(row['totp_enabled']),
                    'is_active': bool(row['is_active']),
                    'is_admin': bool(row['is_admin']),
                    'last_login': row['last_login'],
                    'login_fail_count': row['login_fail_count'],
                    'locked_until': row['locked_until'],
                    'created_at': row['created_at']
                })
        
        return success_response(users)
        
    except Exception as e:
        logger.error(f"获取用户列表失败: {e}")
        return error_response("获取用户列表失败", 500)


@auth_bp.route('/users', methods=['POST'])
@require_admin
@require_csrf
def create_user():
    """创建用户（管理员）"""
    try:
        auth_service = _auth_service(); db_manager = _db_manager()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()
        is_admin = data.get('is_admin', False)
        enable_totp = data.get('enable_totp', False)  # 新增：是否启用TOTP
        
        # 验证
        if not username or not password:
            return error_response("用户名和密码不能为空", 400)
        
        is_valid, error_msg = validate_username(username)
        if not is_valid:
            return error_response(error_msg, 400)
        
        is_valid, error_msg = validate_password_strength(password)
        if not is_valid:
            return error_response(error_msg, 400)
        
        # 检查用户名是否已存在
        if db_manager.get_user_by_username(username):
            return error_response("用户名已存在", 400)
        
        # 创建用户
        password_hash = auth_service.hash_password(password)
        user_id = db_manager.create_user(username, password_hash, email, is_admin)
        
        # 如果需要启用TOTP，生成密钥
        if enable_totp:
            totp_secret = auth_service.generate_totp_secret()
            db_manager.update_user_totp(user_id, totp_secret, True)
            logger.info(f"为用户 {username} 预启用TOTP")
        
        logger.info(f"管理员创建用户: {username}")
        
        return success_response({'id': user_id}, message="用户创建成功")
        
    except Exception as e:
        logger.error(f"创建用户失败: {e}")
        return error_response("创建用户失败", 500)


@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@require_admin
@require_csrf
def update_user(user_id):
    """更新用户信息（管理员）"""
    try:
        db_manager = _db_manager()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        # 检查用户是否存在
        user = db_manager.get_user_by_id(user_id)
        if not user:
            return error_response("用户不存在", 404)
        
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        is_admin = data.get('is_admin', False)
        is_active = data.get('is_active', True)
        
        # 验证
        if not username:
            return error_response("用户名不能为空", 400)
        
        is_valid, error_msg = validate_username(username)
        if not is_valid:
            return error_response(error_msg, 400)
        
        # 检查用户名是否已被其他用户使用
        existing_user = db_manager.get_user_by_username(username)
        if existing_user and existing_user.id != user_id:
            return error_response("用户名已存在", 400)
        
        # 更新用户信息
        success = db_manager.update_user_info(user_id, username, email, is_admin, is_active)
        
        if success:
            logger.info(f"管理员更新用户信息: {user.username} -> {username}")
            return success_response(message="用户信息更新成功")
        else:
            return error_response("更新失败", 500)
        
    except Exception as e:
        logger.error(f"更新用户信息失败: {e}")
        return error_response("更新用户信息失败", 500)


@auth_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@require_admin
@require_csrf
def reset_user_password(user_id):
    """重置用户密码（管理员）"""
    try:
        auth_service = _auth_service(); db_manager = _db_manager()
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空", 400)
        
        new_password = data.get('password', '')
        
        if not new_password:
            return error_response("密码不能为空", 400)
        
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            return error_response(error_msg, 400)
        
        # 检查用户是否存在
        user = db_manager.get_user_by_id(user_id)
        if not user:
            return error_response("用户不存在", 404)
        
        # 重置密码
        password_hash = auth_service.hash_password(new_password)
        db_manager.reset_user_password(user_id, password_hash)
        
        logger.info(f"管理员重置用户密码: {user.username}")
        
        return success_response(message="密码重置成功")
        
    except Exception as e:
        logger.error(f"重置密码失败: {e}")
        return error_response("重置密码失败", 500)


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@require_admin
@require_csrf
def delete_user(user_id):
    """删除用户（管理员）"""
    try:
        db_manager = _db_manager()
        
        # 检查用户是否存在
        user = db_manager.get_user_by_id(user_id)
        if not user:
            return error_response("用户不存在", 404)
        
        # 不能删除自己
        if user_id == request.current_user_id:
            return error_response("不能删除自己的账户", 400)
        
        # 删除用户
        with db_manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        logger.info(f"管理员删除用户: {user.username}")
        
        return success_response(message="用户已删除")
        
    except Exception as e:
        logger.error(f"删除用户失败: {e}")
        return error_response("删除用户失败", 500)


@auth_bp.route('/users/<int:user_id>/enable-totp', methods=['POST'])
@require_admin
@require_csrf
def enable_user_totp(user_id):
    """启用用户TOTP（管理员）"""
    try:
        auth_service = _auth_service(); db_manager = _db_manager()
        
        # 检查用户是否存在
        user = db_manager.get_user_by_id(user_id)
        if not user:
            return error_response("用户不存在", 404)
        
        # 如果已经启用，直接返回
        if user.totp_enabled:
            return success_response(message="TOTP已启用")
        
        # 生成新的TOTP密钥
        totp_secret = auth_service.generate_totp_secret()
        
        # 更新用户TOTP设置
        db_manager.update_user_totp(user_id, totp_secret, True)
        
        logger.info(f"管理员启用用户TOTP: {user.username}")
        
        return success_response(message="TOTP已启用")
        
    except Exception as e:
        logger.error(f"启用TOTP失败: {e}")
        return error_response("启用TOTP失败", 500)


@auth_bp.route('/users/<int:user_id>/disable-totp', methods=['POST'])
@require_admin
@require_csrf
def disable_user_totp(user_id):
    """禁用用户TOTP（管理员）"""
    try:
        db_manager = _db_manager()
        
        # 检查用户是否存在
        user = db_manager.get_user_by_id(user_id)
        if not user:
            return error_response("用户不存在", 404)
        
        # 如果未启用，直接返回
        if not user.totp_enabled:
            return success_response(message="TOTP未启用")
        
        # 禁用TOTP
        db_manager.update_user_totp(user_id, None, False)
        
        logger.info(f"管理员禁用用户TOTP: {user.username}")
        
        return success_response(message="TOTP已禁用")
        
    except Exception as e:
        logger.error(f"禁用TOTP失败: {e}")
        return error_response("禁用TOTP失败", 500)


@auth_bp.route('/users/<int:user_id>/reset-totp', methods=['POST'])
@require_admin
@require_csrf
def reset_user_totp(user_id):
    """重置用户TOTP（管理员）"""
    try:
        auth_service = _auth_service(); db_manager = _db_manager()
        
        # 检查用户是否存在
        user = db_manager.get_user_by_id(user_id)
        if not user:
            return error_response("用户不存在", 404)
        
        # 如果未启用，返回错误
        if not user.totp_enabled:
            return error_response("用户TOTP未启用", 400)
        
        # 生成新的TOTP密钥
        new_totp_secret = auth_service.generate_totp_secret()
        
        # 更新用户TOTP设置，并标记需要重新设置
        with db_manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET totp_secret = ?, totp_enabled = 1, totp_reset = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_totp_secret, user_id)
            )
        
        logger.info(f"管理员重置用户TOTP: {user.username}")
        
        return success_response(message="TOTP已重置")
        
    except Exception as e:
        logger.error(f"重置TOTP失败: {e}")
        return error_response("重置TOTP失败", 500)
