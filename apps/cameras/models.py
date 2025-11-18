from django.db import models
import os


class RecordLog(models.Model):
    """摄像头录制日志"""
    STATUS_CHOICES = [
        ('success', '成功'),
        ('failed', '失败'),
        ('timeout', '超时'),
    ]

    camera_ip = models.CharField(max_length=50, verbose_name="摄像头IP")
    camera_user = models.CharField(max_length=50, verbose_name="用户名")
    task_id = models.CharField(max_length=200, null=True, blank=True, verbose_name="任务ID")

    start_time = models.DateTimeField(auto_now_add=True, verbose_name="开始时间")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='success',
        verbose_name="状态"
    )

    file_path = models.CharField(max_length=500, null=True, blank=True, verbose_name="录制文件路径")
    file_size = models.BigIntegerField(null=True, blank=True, verbose_name="文件大小(字节)")

    error_message = models.TextField(null=True, blank=True, verbose_name="错误信息")

    class Meta:
        verbose_name = "录制日志"
        verbose_name_plural = "录制日志"
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['-start_time']),
            models.Index(fields=['camera_ip']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.camera_ip} - {self.start_time.strftime('%Y-%m-%d %H:%M:%S')} - {self.get_status_display()}"

    def duration(self):
        """计算录制时长"""
        if self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds()
        return None

    def get_video_url(self):
        """生成视频访问 URL"""
        if not self.file_path:
            return None

        # 从环境变量获取配置
        base_url = os.getenv('RESOURCE_BASE_URL', 'http://resource.haoke.vip')
        base_dir = os.getenv('CAMERA_BASE_DIR', '/workspace/ai_project_data/camera_env/server_sync/ResouceData/CameraRecordings')

        # 将本地路径转换为相对路径
        relative_path = self.file_path.replace(base_dir, '').lstrip('/')

        # 拼接 URL
        return f"{base_url}/CameraRecordings/{relative_path}"
