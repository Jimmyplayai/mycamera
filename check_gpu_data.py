#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.cameras.models import GPUMetrics
from django.utils import timezone
from datetime import timedelta

print(f'Total GPUMetrics records: {GPUMetrics.objects.count()}')
print(f'\nRecent 5 records:')
for m in GPUMetrics.objects.all().order_by('-timestamp')[:5]:
    print(f'  {m.timestamp} - GPU: {m.gpu_utilization:.1f}% - Memory: {m.memory_percent:.1f}% - Task: {m.task_type}')

one_hour_ago = timezone.now() - timedelta(hours=1)
recent_count = GPUMetrics.objects.filter(timestamp__gte=one_hour_ago).count()
print(f'\nRecords in last 1 hour: {recent_count}')

if GPUMetrics.objects.exists():
    latest = GPUMetrics.objects.latest('timestamp')
    print(f'\nLatest record:')
    print(f'  Timestamp: {latest.timestamp}')
    print(f'  GPU Utilization: {latest.gpu_utilization:.1f}%')
    print(f'  Memory: {latest.memory_used} / {latest.memory_total} MB ({latest.memory_percent:.1f}%)')
    print(f'  Temperature: {latest.temperature}°C' if latest.temperature else '  Temperature: N/A')
    print(f'  Task Type: {latest.get_task_type_display()}')
