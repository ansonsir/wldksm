"""
认证服务模块
处理所有认证相关逻辑：密码管理、验证码、TOTP、登录流程、会话管理
"""
import os
import time
import logging
import bcrypt
import jwt
import pyotp
import qrcode
import base64
import secrets
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from pathlib import Path

from web.security_config import (
    JWT_EXPIRATION_MINUTES,
    REFRESH_TOKEN_EXPIRATION_DAYS,
    JWT_ALGORITHM,
    TOTP_DIGITS,
    TOTP_PERIOD,
    TOTP_DISALLOWED_WINDOW,
    TOTP_REPLAY_PROTECTION,
    LOCKOUT_DURATION,
    MAX_LOGIN_ATTEMPTS,
    validate_password_strength,
    validate_username,
)

# 临时存储验证码（生产环境应使用Redis）
_captcha_store: Dict[str, Dict] = {}
_MAX_CAPTCHA_COUNT = 100  # 最大验证码存储数量，防止DoS
# IP级别的验证码请求频率追踪
_captcha_request_tracker: Dict[str, list] = {}  # {ip: [timestamp, ...]}

# 存储已使用的TOTP验证码（防止重放攻击）
_used_totp_tokens: Dict[str, float] = {}  # {token: timestamp}


class AuthService:
    """认证服务"""
    
    def __init__(self, db_manager, jwt_secret_key: Optional[str] = None):
        """
        初始化认证服务
        
        Args:
            db_manager: 数据库管理器实例
            jwt_secret_key: JWT密钥（如果不提供，将自动生成）
        """
        self.db = db_manager
        self.logger = logging.getLogger("AuthService")
        
        # JWT密钥
        if jwt_secret_key:
            self.jwt_secret_key = jwt_secret_key
        else:
            # 从文件或环境变量加载
            jwt_key_file = Path(__file__).parent.parent / "data" / ".jwt_secret"
            if jwt_key_file.exists():
                self.jwt_secret_key = jwt_key_file.read_text().strip()
            else:
                self.jwt_secret_key = os.urandom(32).hex()
                jwt_key_file.parent.mkdir(parents=True, exist_ok=True)
                jwt_key_file.write_text(self.jwt_secret_key)
                self.logger.info("已生成新的JWT密钥")

    # ==================== 密码管理 ====================

    @staticmethod
    def hash_password(password: str) -> str:
        """使用bcrypt加密密码"""
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        return password_hash.decode('utf-8')

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                password_hash.encode('utf-8')
            )
        except Exception as e:
            logging.getLogger("AuthService").error(f"密码验证失败: {e}")
            return False

    def validate_password(self, password: str) -> Tuple[bool, str]:
        """验证密码强度"""
        return validate_password_strength(password)

    # ==================== 验证码管理 ====================

    def generate_captcha(self, client_ip: str = "unknown") -> Tuple[str, str]:
        """
        生成图形验证码
        
        Args:
            client_ip: 客户端IP（用于频率限制）
        
        Returns:
            (captcha_id, captcha_image_base64)
        """
        from captcha.image import ImageCaptcha
        
        # IP级别频率限制：每分钟最多10次
        now = time.time()
        if client_ip != "unknown":
            requests_times = _captcha_request_tracker.get(client_ip, [])
            # 清理60秒前的记录
            requests_times = [t for t in requests_times if now - t < 60]
            if len(requests_times) >= 10:
                self.logger.warning(f"验证码请求频率过高: {client_ip}")
                # 返回错误标识
                return "", ""
            requests_times.append(now)
            _captcha_request_tracker[client_ip] = requests_times
        
        # 限制验证码存储数量，防止内存DoS
        if len(_captcha_store) >= _MAX_CAPTCHA_COUNT:
            self._cleanup_captcha()
            if len(_captcha_store) >= _MAX_CAPTCHA_COUNT:
                self.logger.warning("验证码存储已达上限，拒绝生成新验证码")
                return "", ""
        
        # 生成4位验证码（只使用容易识别的字符）
        # 去除容易混淆的字符：0/O, 1/I/l, 2/Z, 5/S, 8/B
        captcha_code = ''.join(secrets.choice('34679ACDEFGHJKMNPRTUVWXY') for _ in range(4))
        captcha_id = secrets.token_urlsafe(16)
        
        # 生成图片 - 优化清晰度和难度
        image = ImageCaptcha(
            width=160,      # 增加宽度
            height=60,      # 增加高度
            font_sizes=[40, 45, 50]  # 增大字体
        )
        
        # 生成验证码图片
        image_data = image.generate(captcha_code)
        
        # 转换为base64
        image_base64 = base64.b64encode(image_data.read()).decode('utf-8')
        
        # 存储验证码（10分钟有效）
        _captcha_store[captcha_id] = {
            'code': captcha_code.lower(),
            'expires': time.time() + 600
        }
        
        # 清理过期验证码
        self._cleanup_captcha()
        
        return captcha_id, f"data:image/png;base64,{image_base64}"

    def verify_captcha(self, captcha_id: str, user_input: str) -> bool:
        """
        验证验证码（一次性使用）
        
        Args:
            captcha_id: 验证码ID
            user_input: 用户输入
            
        Returns:
            验证是否成功
        """
        if captcha_id not in _captcha_store:
            return False
        
        captcha_data = _captcha_store[captcha_id]
        
        # 检查是否过期
        if time.time() > captcha_data['expires']:
            del _captcha_store[captcha_id]
            return False
        
        # 验证（不区分大小写）
        is_valid = captcha_data['code'] == user_input.lower()
        
        # 一次性使用，无论成功与否都删除
        del _captcha_store[captcha_id]
        
        return is_valid

    def _cleanup_captcha(self):
        """清理过期验证码"""
        now = time.time()
        expired_ids = [cid for cid, data in _captcha_store.items() if now > data['expires']]
        for cid in expired_ids:
            del _captcha_store[cid]

    # ==================== TOTP管理 ====================

    @staticmethod
    def generate_totp_secret() -> str:
        """生成TOTP密钥"""
        return pyotp.random_base32()

    def verify_totp(self, secret: str, token: str) -> Tuple[bool, str]:
        """
        验证TOTP令牌
        
        Args:
            secret: TOTP密钥
            token: 用户输入的6位验证码
            
        Returns:
            (验证是否成功, 错误信息)
        """
        try:
            totp = pyotp.TOTP(secret)
            
            # 验证验证码（允许前后各1个窗口，共90秒容错）
            if not totp.verify(token, valid_window=TOTP_DISALLOWED_WINDOW):
                return False, "验证码错误或已过期"
            
            # 重放保护：检查验证码是否已使用过
            if TOTP_REPLAY_PROTECTION:
                if token in _used_totp_tokens:
                    self.logger.warning(f"TOTP验证码已被使用过（重放攻击）: {token}")
                    return False, "验证码已被使用，请使用新的验证码"
                
                # 记录已使用的验证码
                _used_totp_tokens[token] = time.time()
                
                # 清理过期的记录（保留最近2分钟）
                current_time = time.time()
                expired_tokens = [
                    t for t, ts in _used_totp_tokens.items()
                    if current_time - ts > 120  # 2分钟
                ]
                for t in expired_tokens:
                    del _used_totp_tokens[t]
            
            return True, ""
            
        except Exception as e:
            self.logger.error(f"TOTP验证失败: {e}")
            return False, "验证码验证失败"

    def generate_totp_qr_code(self, username: str, secret: str) -> str:
        """
        生成TOTP二维码（base64）
        
        Args:
            username: 用户名
            secret: TOTP密钥
            
        Returns:
            二维码图片的base64编码
        """
        # 生成TOTP URI
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=username,
            issuer_name="ScanScript"
        )
        
        # 生成二维码
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 转换为base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{img_base64}"

    # ==================== TOTP 临时会话 Token ====================

    def create_totp_session_token(self, user_id: int, ip_address: str, user_agent: str) -> str:
        """
        创建 TOTP 临时会话 Token（替代 Flask session，避免浏览器 cookie 策略问题）
        有效期 5 分钟，仅用于 TOTP 第二步验证
        """
        now = datetime.utcnow()
        expiration = now + timedelta(minutes=5)
        payload = {
            'user_id': user_id,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'type': 'totp_session',
            'iat': now,
            'exp': expiration,
            'jti': secrets.token_urlsafe(16)
        }
        return jwt.encode(payload, self.jwt_secret_key, algorithm=JWT_ALGORITHM)

    def verify_totp_session_token(self, token: str) -> Optional[Dict]:
        """
        验证 TOTP 临时会话 Token
        
        Returns:
            {'user_id': int, 'ip_address': str, 'user_agent': str} 或 None
        """
        try:
            payload = jwt.decode(token, self.jwt_secret_key, algorithms=[JWT_ALGORITHM])
            if payload.get('type') != 'totp_session':
                self.logger.warning("无效的 TOTP 会话 Token 类型")
                return None
            return {
                'user_id': payload['user_id'],
                'ip_address': payload.get('ip_address', 'unknown'),
                'user_agent': payload.get('user_agent', 'unknown')
            }
        except jwt.ExpiredSignatureError:
            self.logger.warning("TOTP 会话 Token 已过期")
            return None
        except jwt.InvalidTokenError as e:
            self.logger.warning(f"无效的 TOTP 会话 Token: {e}")
            return None

    # ==================== 登录流程 ====================

    def authenticate(self, username: str, password: str, 
                    captcha_id: str, captcha_code: str,
                    ip_address: str = "unknown",
                    user_agent: str = "unknown") -> Dict:
        """
        用户登录（第一步：验证用户名密码+验证码）
        
        Args:
            username: 用户名
            password: 密码
            captcha_id: 验证码ID
            captcha_code: 验证码
            ip_address: 客户端真实IP（由API层传入）
            user_agent: 客户端User-Agent
            
        Returns:
            {
                'success': bool,
                'need_totp': bool,  # 是否需要TOTP验证
                'user_id': int,  # 如果需要TOTP
                'token': str,  # 如果登录成功
                'refresh_token': str,
                'user_info': dict,
                'error': str,  # 如果失败
                'remaining_attempts': int  # 剩余尝试次数
            }
        """
        # 1. 验证验证码
        if not self.verify_captcha(captcha_id, captcha_code):
            self.logger.warning(f"验证码验证失败: {username}")
            return {
                'success': False,
                'error': '验证码错误',
                'remaining_attempts': MAX_LOGIN_ATTEMPTS
            }
        
        # 2. 查找用户
        user = self.db.get_user_by_username(username)
        if not user:
            self.logger.warning(f"用户不存在: {username}")
            # 记录登录日志
            self.db.create_login_log(
                user_id=None, username=username, ip_address=ip_address,
                user_agent=user_agent, login_status='failed',
                failure_reason='用户不存在'
            )
            return {
                'success': False,
                'error': '用户名或密码错误',  # 不暴露具体原因
                'remaining_attempts': MAX_LOGIN_ATTEMPTS
            }
        
        # 3. 检查账户是否被锁定
        if user.locked_until:
            locked_until = datetime.strptime(user.locked_until, "%Y-%m-%d %H:%M:%S")
            if datetime.now() < locked_until:
                remaining_minutes = int((locked_until - datetime.now()).total_seconds() / 60)
                self.logger.warning(f"账户已锁定: {username}, 剩余{remaining_minutes}分钟")
                self.db.create_login_log(
                    user_id=user.id, username=username, ip_address=ip_address,
                    user_agent=user_agent, login_status='locked',
                    failure_reason=f'账户锁定，剩余{remaining_minutes}分钟'
                )
                return {
                    'success': False,
                    'error': f'账户已被锁定，请{remaining_minutes}分钟后重试',
                    'remaining_attempts': 0
                }
            else:
                # 锁定已过期，重置
                self.db.update_user_login(user.id, success=True)
        
        # 4. 验证密码
        if not self.verify_password(password, user.password_hash):
            self.logger.warning(f"密码错误: {username}")
            
            # 更新失败次数
            self.db.update_user_login(user.id, success=False)
            
            # 获取更新后的用户信息
            user = self.db.get_user_by_username(username)
            remaining = MAX_LOGIN_ATTEMPTS - user.login_fail_count
            
            # 记录登录日志
            self.db.create_login_log(
                user_id=user.id, username=username, ip_address=ip_address,
                user_agent=user_agent, login_status='failed',
                failure_reason='密码错误'
            )
            
            # 检查是否达到最大失败次数
            if user.login_fail_count >= MAX_LOGIN_ATTEMPTS:
                self.db.lock_user(user.id, LOCKOUT_DURATION)
                self.logger.warning(f"账户已锁定: {username}（失败次数过多）")
                return {
                    'success': False,
                    'error': f'密码错误次数过多，账户已锁定{LOCKOUT_DURATION}分钟',
                    'remaining_attempts': 0
                }
            
            return {
                'success': False,
                'error': f'用户名或密码错误（剩余{remaining}次尝试）',
                'remaining_attempts': remaining
            }
        
        # 5. 检查是否需要TOTP
        if user.totp_enabled:
            # 检查是否需要重新设置TOTP（管理员重置后）
            if user.totp_reset:
                # 需要重新设置TOTP
                self.logger.info(f"用户需要重新设置TOTP: {username}")
                result = self._create_login_session(user, ip_address, user_agent)
                result['need_totp_setup'] = True  # 需要设置TOTP
                result['need_totp'] = False
                result['user_info']['totp_enabled'] = False  # 前端认为未启用
                result['user_info']['totp_setup_required'] = True  # 需要设置
                return result
            
            # 检查是否是预启用（用户还未设置）
            # 如果totp_secret存在但用户从未登录过（last_login为NULL），说明是预启用
            needs_setup = user.totp_secret and not user.last_login
            
            if needs_setup:
                # 预启用的TOTP，需要用户首次登录时设置
                self.logger.info(f"用户预启用TOTP，需要首次设置: {username}")
                result = self._create_login_session(user, ip_address, user_agent)
                result['need_totp_setup'] = True  # 需要设置TOTP
                result['need_totp'] = False
                # 重要：标记为未完成TOTP设置，前端路由守卫会检查这个字段
                result['user_info']['totp_enabled'] = False  # 前端认为未启用
                result['user_info']['totp_setup_required'] = True  # 需要设置
                return result
            else:
                # 用户已完成TOTP设置，需要验证
                self.logger.info(f"需要TOTP验证: {username}")
                return {
                    'success': True,
                    'need_totp': True,
                    'need_totp_setup': False,  # 不需要设置，只需要验证
                    'user_id': user.id
                }
        
        # 6. 登录成功，创建会话（但标记需要设置TOTP）
        result = self._create_login_session(user, ip_address, user_agent)
        result['need_totp_setup'] = True  # 标记需要设置TOTP
        return result

    def verify_totp_login(self, user_id: int, totp_token: str, 
                         ip_address: str = "unknown", user_agent: str = "unknown") -> Dict:
        """
        TOTP验证（第二步）
        
        Args:
            user_id: 用户ID
            totp_token: TOTP验证码
            ip_address: IP地址
            user_agent: User-Agent
            
        Returns:
            登录结果
        """
        user = self.db.get_user_by_id(user_id)
        if not user:
            return {
                'success': False,
                'error': '用户不存在'
            }
        
        # 验证TOTP
        success, error_msg = self.verify_totp(user.totp_secret, totp_token)
        if not success:
            self.logger.warning(f"TOTP验证失败: {user.username}, 原因: {error_msg}")
            self.db.create_login_log(
                user_id=user.id, username=user.username, ip_address=ip_address,
                user_agent=user_agent, login_status='totp_failed',
                failure_reason=error_msg
            )
            return {
                'success': False,
                'error': error_msg
            }
        
        # TOTP验证成功，创建会话
        return self._create_login_session(user, ip_address, user_agent)

    def _create_login_session(self, user, ip_address: str, user_agent: str) -> Dict:
        """
        创建登录会话
        
        Args:
            user: 用户对象
            ip_address: IP地址
            user_agent: User-Agent
            
        Returns:
            登录成功响应
        """
        # 更新登录信息
        self.db.update_user_login(user.id, success=True)
        
        # 记录登录日志
        self.db.create_login_log(
            user_id=user.id, username=user.username, ip_address=ip_address,
            user_agent=user_agent, login_status='success'
        )
        
        # 创建token
        token = self.create_session(user.id)
        refresh_token = self.create_refresh_token(user.id)
        
        self.logger.info(f"用户登录成功: {user.username}")
        
        return {
            'success': True,
            'need_totp': False,
            'token': token,
            'refresh_token': refresh_token,
            'user_info': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_admin': user.is_admin,
                'totp_enabled': user.totp_enabled,
                'first_login': user.first_login,  # 添加首次登录状态
                'last_login': user.last_login
            }
        }

    # ==================== 会话管理 ====================

    def create_csrf_token(self) -> str:
        """
        创建CSRF保护Token（短期JWT）
        用于防止跨站请求伪造攻击
        """
        now = datetime.utcnow()
        expiration = now + timedelta(hours=8)  # CSRF token有效期8小时
        payload = {
            'type': 'csrf',
            'iat': now,
            'exp': expiration,
            'jti': secrets.token_urlsafe(16)
        }
        return jwt.encode(payload, self.jwt_secret_key, algorithm=JWT_ALGORITHM)

    def verify_csrf_token(self, token: str) -> bool:
        """验证CSRF Token"""
        try:
            payload = jwt.decode(token, self.jwt_secret_key, algorithms=[JWT_ALGORITHM])
            return payload.get('type') == 'csrf'
        except jwt.ExpiredSignatureError:
            return False
        except jwt.InvalidTokenError:
            return False

    def create_session(self, user_id: int) -> str:
        """
        创建JWT token
        
        Args:
            user_id: 用户ID
            
        Returns:
            JWT token
        """
        now = datetime.utcnow()
        expiration = now + timedelta(minutes=JWT_EXPIRATION_MINUTES)
        
        payload = {
            'user_id': user_id,
            'type': 'access',
            'iat': now,
            'exp': expiration,
            'jti': secrets.token_urlsafe(16)  # JWT ID
        }
        
        token = jwt.encode(payload, self.jwt_secret_key, algorithm=JWT_ALGORITHM)
        return token

    def create_refresh_token(self, user_id: int) -> str:
        """
        创建刷新token
        
        Args:
            user_id: 用户ID
            
        Returns:
            Refresh token
        """
        now = datetime.utcnow()
        expiration = now + timedelta(days=REFRESH_TOKEN_EXPIRATION_DAYS)
        
        payload = {
            'user_id': user_id,
            'type': 'refresh',
            'iat': now,
            'exp': expiration,
            'jti': secrets.token_urlsafe(16)
        }
        
        token = jwt.encode(payload, self.jwt_secret_key, algorithm=JWT_ALGORITHM)
        return token

    def verify_session(self, token: str) -> Optional[Dict]:
        """
        验证JWT token
        
        Args:
            token: JWT token
            
        Returns:
            token payload（如果有效），否则返回None
        """
        try:
            # 检查是否在黑名单
            if self.db.is_session_blacklisted(token):
                self.logger.warning("Token已在黑名单中")
                return None
            
            payload = jwt.decode(token, self.jwt_secret_key, algorithms=[JWT_ALGORITHM])
            
            # 检查token类型
            if payload.get('type') != 'access':
                self.logger.warning("无效的token类型")
                return None
            
            # 检查用户是否仍然活跃
            user = self.db.get_user_by_id(payload['user_id'])
            if not user or not user.is_active:
                self.logger.warning(f"用户不活跃: {payload['user_id']}")
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            self.logger.warning("Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            self.logger.warning(f"无效的Token: {e}")
            return None

    def refresh_session(self, refresh_token: str) -> Optional[Dict]:
        """
        刷新token
        
        Args:
            refresh_token: 刷新token
            
        Returns:
            {token, refresh_token} 或 None
        """
        try:
            payload = jwt.decode(refresh_token, self.jwt_secret_key, algorithms=[JWT_ALGORITHM])
            
            if payload.get('type') != 'refresh':
                return None
            
            # 检查用户是否仍然活跃
            user = self.db.get_user_by_id(payload['user_id'])
            if not user or not user.is_active:
                return None
            
            # 创建新的token
            new_token = self.create_session(user.id)
            new_refresh_token = self.create_refresh_token(user.id)
            
            return {
                'token': new_token,
                'refresh_token': new_refresh_token
            }
            
        except jwt.ExpiredSignatureError:
            self.logger.warning("Refresh token已过期")
            return None
        except jwt.InvalidTokenError:
            return None

    def revoke_session(self, token: str) -> bool:
        """
        撤销会话（加入黑名单）
        
        Args:
            token: JWT token
            
        Returns:
            是否成功
        """
        return self.db.add_session_to_blacklist(token)
