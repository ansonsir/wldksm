"""
ScanScript 核心异常类
"""


class ScanError(Exception):
    """扫描异常基类"""
    pass


class ScanTimeoutError(ScanError):
    """扫描超时"""
    pass


class ConfigError(ScanError):
    """配置错误"""
    pass


class DatabaseError(ScanError):
    """数据库错误"""
    pass


class TaskNotFoundError(ScanError):
    """任务不存在"""
    pass
