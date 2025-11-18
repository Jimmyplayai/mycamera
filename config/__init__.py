import pymysql

# 使用 PyMySQL 作为 MySQLdb 的替代
pymysql.install_as_MySQLdb()

from config.celery import app as celery_app

__all__ = ('celery_app',)