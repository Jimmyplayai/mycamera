from django.db import models
import os


class RecordLog(models.Model):
    """摄像头录制日志"""
    STATUS_CHOICES = [
        ('success', '成功'),
        ('failed', '失败'),
        ('timeout', '超时'),
    ]

    ANALYSIS_STATUS_CHOICES = [
        ('pending', '待检测'),
        ('processing', '检测中'),
        ('completed', '已完成'),
        ('failed', '检测失败'),
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

    # 人物检测状态
    analysis_status = models.CharField(
        max_length=20,
        choices=ANALYSIS_STATUS_CHOICES,
        default='pending',
        verbose_name="检测状态"
    )
    analysis_time = models.DateTimeField(null=True, blank=True, verbose_name="检测完成时间")

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


class PersonDetection(models.Model):
    """人物检测记录"""
    CAPTION_STATUS_CHOICES = [
        ('pending', '待生成'),
        ('processing', '生成中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    ]

    record_log = models.ForeignKey(
        RecordLog,
        on_delete=models.CASCADE,
        related_name='detections',
        verbose_name="录制日志"
    )
    frame_number = models.IntegerField(verbose_name="帧序号")
    timestamp = models.FloatField(verbose_name="视频时间戳(秒)")
    image_path = models.CharField(max_length=500, verbose_name="截图路径")
    confidence = models.FloatField(verbose_name="检测置信度")
    bbox = models.JSONField(null=True, blank=True, verbose_name="边界框坐标")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    # 图片描述相关字段
    caption = models.TextField(null=True, blank=True, verbose_name="图片描述(英文)")
    caption_zh = models.TextField(null=True, blank=True, verbose_name="图片描述(中文)")
    keywords = models.JSONField(null=True, blank=True, verbose_name="关键词列表")
    caption_status = models.CharField(
        max_length=20,
        choices=CAPTION_STATUS_CHOICES,
        default='pending',
        verbose_name="描述生成状态"
    )
    caption_generated_at = models.DateTimeField(null=True, blank=True, verbose_name="描述生成时间")

    class Meta:
        verbose_name = "人物检测记录"
        verbose_name_plural = "人物检测记录"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['record_log', 'timestamp']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['caption_status']),
        ]

    def __str__(self):
        return f"{self.record_log.camera_ip} - Frame {self.frame_number} - {self.confidence:.2f}"

    def get_image_url(self):
        """生成图片访问 URL"""
        if not self.image_path:
            return None

        base_url = os.getenv('RESOURCE_BASE_URL', 'http://resource.haoke.vip')
        pics_base_dir = os.getenv('PICS_BASE_DIR', '/workspace/ai_project_data/camera_env/server_sync/ResouceData/CameraWarningPics')

        # 将本地路径转换为相对路径
        relative_path = self.image_path.replace(pics_base_dir, '').lstrip('/')

        # 拼接 URL
        return f"{base_url}/CameraWarningPics/{relative_path}"
