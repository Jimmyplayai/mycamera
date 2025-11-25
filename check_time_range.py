#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.cameras.models import GPUMetrics
from django.utils import timezone
from datetime import timedelta

now = timezone.now()
print(f'Current time: {now}')
print(f'Timezone: {timezone.get_current_timezone()}')

if GPUMetrics.objects.exists():
    latest = GPUMetrics.objects.latest('timestamp')
    oldest = GPUMetrics.objects.earliest('timestamp')

    print(f'\nData range:')
    print(f'  Oldest: {oldest.timestamp}')
    print(f'  Latest: {latest.timestamp}')
    print(f'  Time since latest: {(now - latest.timestamp).total_seconds() / 60:.1f} minutes ago')

    # 检查不同时间范围的数据量
    for hours in [1, 6, 24, 168]:
        time_ago = now - timedelta(hours=hours)
        count = GPUMetrics.objects.filter(timestamp__gte=time_ago).count()
        print(f'\nLast {hours} hour(s): {count} records')
        if count > 0:
            print(f'  Time threshold: {time_ago}')
else:
    print('No data in database')
