"""
gunicorn 生产配置文件
启动: gunicorn -c gunicorn.conf.py wsgi:app
"""
import multiprocessing
import os

# 绑定地址
bind = "0.0.0.0:5000"

# 工作进程数（推荐: CPU核心数 * 2 + 1，SQLite场景单worker更安全）
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)

# 工作模式（gevent 适合 IO 密集型）
worker_class = "sync"

# 每个 worker 最大请求数（防止内存泄漏积累）
max_requests = 1000
max_requests_jitter = 100

# 超时设置
timeout = 120
graceful_timeout = 30
keepalive = 5

# 日志
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'

# 进程命名
proc_name = "scanscript"

# 后台运行
daemon = False
pidfile = "logs/gunicorn.pid"

# 预加载应用（共享资源，节省内存）
preload_app = True
