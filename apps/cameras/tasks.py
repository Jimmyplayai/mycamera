# app/tasks.py
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
import subprocess
from datetime import datetime
import os
import pytz
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, time_limit=120, soft_time_limit=90)
def record_camera_task(self, ip, user, password, port, path, base_dir=None):
    # 导入模型（避免循环导入）
    from apps.cameras.models import RecordLog

    if base_dir is None:
        base_dir = os.getenv("CAMERA_BASE_DIR", "/workspace/ai_project_data/camera_env/server_sync/ResouceData/CameraRecordings")
    print(f"录制摄像头流: {ip}")
    tz = pytz.timezone("Asia/Shanghai")  # 设置时区
    now = datetime.now(tz)
    minute = now.strftime("%M")  # 当前分钟

    output_dir = os.path.join(base_dir, ip, now.strftime("%Y/%m/%d/%H"))
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{minute}.mp4")

    rtsp_url = f"rtsp://{user}:{password}@{ip}:{port}/{path}"

    # 创建日志记录
    log = RecordLog.objects.create(
        camera_ip=ip,
        camera_user=user,
        task_id=self.request.id,
        file_path=output_file,
    )

    try:
        # 添加���时保护：ffmpeg录制60秒，但给它75秒的超时时间
        subprocess.run([
            "ffmpeg",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c:v", "copy",
            "-an",
            "-t", "60",
            "-y", output_file
        ], check=True, timeout=75)

        # 录制成功，更新日志
        log.status = 'success'
        log.end_time = timezone.now()
        if os.path.exists(output_file):
            log.file_size = os.path.getsize(output_file)
        log.save()

        return f"{ip} 录制成功: {output_file}"

    except subprocess.TimeoutExpired as e:
        logger.error(f"{ip} ffmpeg进程超时(75秒)，可能摄像头网络异常")
        log.status = 'timeout'
        log.end_time = timezone.now()
        log.error_message = f"ffmpeg进程超时(75秒): {str(e)}"
        log.save()
        return f"{ip} 录制超时: ffmpeg进程被终止"

    except subprocess.CalledProcessError as e:
        logger.error(f"{ip} ffmpeg执行失败: {e}")
        log.status = 'failed'
        log.end_time = timezone.now()
        log.error_message = f"ffmpeg执行失败: {str(e)}"
        log.save()
        # 自动重试
        raise self.retry(exc=e, countdown=5)

    except SoftTimeLimitExceeded:
        logger.warning(f"{ip} Celery任务软超时(90秒)，任务即将被终止")
        log.status = 'timeout'
        log.end_time = timezone.now()
        log.error_message = "Celery任务软超时(90秒)"
        log.save()
        return f"{ip} 录制任务超时"

    except Exception as e:
        logger.error(f"{ip} 未知错误: {e}")
        log.status = 'failed'
        log.end_time = timezone.now()
        log.error_message = f"未知错误: {str(e)}"
        log.save()
        return f"{ip} 录制失败: {str(e)}"
