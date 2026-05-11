"""
安全配置模块
定义密码策略、会话安全、暴力破解防护等安全参数
"""

# ==================== 密码策略 ====================
PASSWORD_MIN_LENGTH = 8
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True
PASSWORD_REQUIRE_DIGIT = True
PASSWORD_REQUIRE_SPECIAL = True
SPECIAL_CHARACTERS = "!@#$%^&*()_+-=[]{}|;:,.<>?"

# ==================== 暴力破解防护 ====================
MAX_LOGIN_ATTEMPTS = 5  # 最大失败次数
LOCKOUT_DURATION = 30  # 锁定时间（分钟）
CAPTCHA_REQUIRED_ALWAYS = True  # 始终要求验证码

# ==================== 会话安全 ====================
SESSION_TIMEOUT_MINUTES = 15  # 会话超时时间（分钟）
JWT_EXPIRATION_MINUTES = 15  # JWT token有效期（分钟）
REFRESH_TOKEN_EXPIRATION_DAYS = 7  # 刷新token有效期（天）
JWT_ALGORITHM = "HS256"

# ==================== TOTP配置 ====================
TOTP_DIGITS = 6  # TOTP验证码位数
TOTP_PERIOD = 30  # TOTP时间窗口（秒）
TOTP_DISALLOWED_WINDOW = 1  # 允许的前后时间窗口数（1=前后各30秒，总共90秒容错）
TOTP_REPLAY_PROTECTION = True  # 启用验证码重放保护（防止重复使用）

# ==================== HTTP安全头 ====================
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

# ==================== 日志审计 ====================
LOG_LOGIN_ATTEMPTS = True  # 记录登录尝试
LOG_FAILED_PASSWORDS = False  # 不记录失败密码（安全考虑）

# ==================== 输入验证 ====================
MAX_USERNAME_LENGTH = 50
MAX_EMAIL_LENGTH = 100
ALLOWED_USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    验证密码强度
    
    Returns:
        (is_valid, error_message)
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"密码长度至少为{PASSWORD_MIN_LENGTH}位"
    
    if PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
        return False, "密码必须包含大写字母"
    
    if PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in password):
        return False, "密码必须包含小写字母"
    
    if PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in password):
        return False, "密码必须包含数字"
    
    if PASSWORD_REQUIRE_SPECIAL:
        if not any(c in SPECIAL_CHARACTERS for c in password):
            return False, f"密码必须包含特殊字符（{SPECIAL_CHARACTERS}）"
    
    return True, ""


def validate_username(username: str) -> tuple[bool, str]:
    """
    验证用户名合法性
    
    Returns:
        (is_valid, error_message)
    """
    if not username or len(username) > MAX_USERNAME_LENGTH:
        return False, f"用户名长度必须在1-{MAX_USERNAME_LENGTH}之间"
    
    if not all(c in ALLOWED_USERNAME_CHARS for c in username):
        return False, "用户名只能包含字母、数字、下划线、连字符和点"
    
    return True, ""
