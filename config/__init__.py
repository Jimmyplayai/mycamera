import pymysql
import multiprocessing

# 使用 PyMySQL 作为 MySQLdb 的替代
pymysql.install_as_MySQLdb()

# 设置 multiprocessing 启动方式为 spawn，解决 CUDA fork 问题
try:
    multiprocessing.set_start_method('spawn', force=True)
except RuntimeError:
    pass  # 已经设置过了

from config.celery import app as celery_app

__all__ = ('celery_app',)