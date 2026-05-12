"""
共享的 Flask-Limiter 实例
独立模块避免循环导入
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "200 per hour"]
)
