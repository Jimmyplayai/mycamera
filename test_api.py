#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from apps.cameras.views import gpu_metrics_data_api
from django.contrib.auth.models import User

# 创建测试请求
factory = RequestFactory()
request = factory.get('/api/gpu-metrics/?hours=1')

# 创建或获取staff用户
user, created = User.objects.get_or_create(username='admin', defaults={'is_staff': True, 'is_superuser': True})
if not user.is_staff:
    user.is_staff = True
    user.save()

request.user = user

# 调用API
response = gpu_metrics_data_api(request)
print(f'Status Code: {response.status_code}')
print(f'Content Type: {response.get("Content-Type")}')
print(f'\nResponse preview (first 500 chars):')
print(response.content.decode('utf-8')[:500])
