import os
from celery import Celery

# 设置 Django 配置模块
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

# 从 Django settings 读取 celery 配置（CELERY_ 开头）
app.config_from_object("django.conf:settings", namespace="CELERY")

# 自动发现 apps 下的 tasks.py
app.autodiscover_tasks()