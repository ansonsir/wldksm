"""
WSGI 入口文件 (gunicorn 使用)
启动方式:
    gunicorn -c gunicorn.conf.py wsgi:app
    gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
"""
from web.app import app

if __name__ == "__main__":
    app.run()
