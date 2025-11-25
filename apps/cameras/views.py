from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from datetime import timedelta
from .models import GPUMetrics
from django.db.models import Avg, Max, Min, Count, Q


@staff_member_required
def gpu_chart_view(request):
    """GPU监控图表页面"""
    # 获取最近1小时的数据用于初始化显示
    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent_data = GPUMetrics.objects.filter(
        timestamp__gte=one_hour_ago
    ).order_by('timestamp')

    # 统计信息
    stats = {
        'total_records': GPUMetrics.objects.count(),
        'warning_count': GPUMetrics.objects.filter(alert_level='warning').count(),
        'critical_count': GPUMetrics.objects.filter(alert_level='critical').count(),
    }

    if recent_data.exists():
        stats.update({
            'avg_gpu_util': recent_data.aggregate(Avg('gpu_utilization'))['gpu_utilization__avg'],
            'max_gpu_util': recent_data.aggregate(Max('gpu_utilization'))['gpu_utilization__max'],
            'avg_memory_percent': recent_data.aggregate(Avg('memory_percent'))['memory_percent__avg'],
            'max_temperature': recent_data.aggregate(Max('temperature'))['temperature__max'],
        })

    context = {
        'stats': stats,
        'site_header': 'GPU监控图表',
    }

    return render(request, 'admin/cameras/gpu_metrics_chart.html', context)


@staff_member_required
def gpu_metrics_data_api(request):
    """
    GPU监控数据API

    参数:
        hours: 查询最近N小时的数据 (默认1)
        task_type: 任务类型筛选 (可选)
    """
    try:
        # 获取参数
        hours = int(request.GET.get('hours', 1))
        task_type = request.GET.get('task_type', None)

        # 限制查询范围（最多30天）
        hours = min(hours, 24 * 30)

        # 计算时间范围
        time_threshold = timezone.now() - timedelta(hours=hours)

        # 构建查询
        queryset = GPUMetrics.objects.filter(timestamp__gte=time_threshold)

        if task_type:
            queryset = queryset.filter(task_type=task_type)

        queryset = queryset.order_by('timestamp')

        # 如果数据点太多（>1000），进行采样
        total_count = queryset.count()
        if total_count > 1000:
            # 每N条取一条
            step = total_count // 1000
            queryset = queryset[::step]

        # 序列化数据
        data = {
            'timestamps': [],
            'gpu_utilization': [],
            'memory_used': [],
            'memory_percent': [],
            'temperature': [],
            'task_types': [],
            'alert_levels': [],
        }

        for metric in queryset:
            data['timestamps'].append(metric.timestamp.strftime('%Y-%m-%d %H:%M:%S'))
            data['gpu_utilization'].append(round(metric.gpu_utilization, 2))
            data['memory_used'].append(metric.memory_used)
            data['memory_percent'].append(round(metric.memory_percent, 2))
            data['temperature'].append(round(metric.temperature, 2) if metric.temperature else None)
            data['task_types'].append(metric.get_task_type_display())
            data['alert_levels'].append(metric.alert_level)

        # 任务类型统计
        task_stats = list(
            queryset.values('task_type').annotate(
                count=Count('id')
            ).order_by('-count')
        )

        # 转换任务类型显示名称
        for stat in task_stats:
            task_type_value = stat['task_type']
            # 获取display值
            stat['task_type_display'] = dict(GPUMetrics.TASK_TYPE_CHOICES).get(task_type_value, task_type_value)

        # 告警统计
        alert_stats = list(
            queryset.values('alert_level').annotate(
                count=Count('id')
            )
        )

        return JsonResponse({
            'success': True,
            'data': data,
            'task_stats': task_stats,
            'alert_stats': alert_stats,
            'total_count': total_count,
            'query_hours': hours,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

