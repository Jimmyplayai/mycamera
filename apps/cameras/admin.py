from django.contrib import admin
from django.utils.html import format_html
from .models import RecordLog


@admin.register(RecordLog)
class RecordLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'camera_ip', 'start_time_display', 'duration_display', 'status_display', 'file_size_display', 'video_url_display']
    list_filter = ['status', 'camera_ip', 'start_time']
    search_fields = ['camera_ip', 'task_id', 'file_path', 'error_message']
    readonly_fields = ['task_id', 'start_time', 'end_time', 'duration_display', 'video_preview']
    date_hierarchy = 'start_time'
    list_per_page = 50

    fieldsets = (
        ('基本信息', {
            'fields': ('camera_ip', 'camera_user', 'task_id', 'status')
        }),
        ('时间信息', {
            'fields': ('start_time', 'end_time', 'duration_display')
        }),
        ('文件信息', {
            'fields': ('file_path', 'file_size', 'video_preview')
        }),
        ('错误信息', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )

    def start_time_display(self, obj):
        """格式化开始时间"""
        return obj.start_time.strftime('%Y-%m-%d %H:%M:%S')
    start_time_display.short_description = '开始时间'

    def duration_display(self, obj):
        """显示时长"""
        duration = obj.duration()
        if duration is not None:
            return f"{duration:.1f}秒"
        return "-"
    duration_display.short_description = '录制时长'

    def status_display(self, obj):
        """彩色状态显示"""
        colors = {
            'success': 'green',
            'failed': 'red',
            'timeout': 'orange',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = '状态'

    def file_size_display(self, obj):
        """格式化文件大小"""
        if obj.file_size:
            size_mb = obj.file_size / (1024 * 1024)
            return f"{size_mb:.2f} MB"
        return "-"
    file_size_display.short_description = '文件大小'

    def video_url_display(self, obj):
        """显示视频链接（可点击查看）"""
        video_url = obj.get_video_url()
        if video_url:
            return format_html(
                '<a href="{}" target="_blank" style="color: #0066cc; text-decoration: underline;">查看视频</a>',
                video_url
            )
        return "-"
    video_url_display.short_description = '视频路径'

    def video_preview(self, obj):
        """在详情页显示视频预览"""
        video_url = obj.get_video_url()
        if video_url:
            return format_html(
                '''
                <div style="margin-top: 10px;">
                    <p><strong>视频URL：</strong><a href="{}" target="_blank">{}</a></p>
                    <video width="640" height="360" controls style="margin-top: 10px;">
                        <source src="{}" type="video/mp4">
                        您的浏览器不支持视频播放。
                    </video>
                </div>
                ''',
                video_url, video_url, video_url
            )
        return "-"
    video_preview.short_description = '视频预览'
