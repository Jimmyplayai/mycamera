# app/tasks.py
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
import subprocess
from datetime import datetime
import os
import pytz
import logging
from django.utils import timezone
import cv2
import torch
from ultralytics import YOLO
from pathlib import Path

logger = logging.getLogger(__name__)


def get_gpu_stats():
    """获取 GPU 利用率和显存使用情况"""
    if not torch.cuda.is_available():
        return None

    try:
        # 使用 nvidia-smi 获取详细信息
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            values = result.stdout.strip().split(', ')
            if len(values) >= 4:
                mem_used = float(values[1])
                mem_total = float(values[2])
                mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0
                return {
                    'gpu_util': f"{values[0]}%",
                    'mem_used': f"{int(mem_used)}MB",
                    'mem_total': f"{int(mem_total)}MB",
                    'mem_percent': f"{mem_percent:.1f}%",
                    'temperature': f"{values[3]}°C"
                }
    except Exception as e:
        logger.debug(f"nvidia-smi 获取失败: {e}")

    # 备用方案：使用 PyTorch
    try:
        device = torch.cuda.current_device()
        mem_allocated = torch.cuda.memory_allocated(device) / 1024**2
        mem_total = torch.cuda.get_device_properties(device).total_memory / 1024**2
        mem_percent = (mem_allocated / mem_total * 100) if mem_total > 0 else 0
        return {
            'gpu_util': 'N/A',
            'mem_used': f"{mem_allocated:.0f}MB",
            'mem_total': f"{mem_total:.0f}MB",
            'mem_percent': f"{mem_percent:.1f}%",
            'temperature': 'N/A'
        }
    except Exception as e:
        logger.debug(f"PyTorch GPU 信息获取失败: {e}")
        return None


def log_gpu_stats(prefix=""):
    """打印 GPU 状态日志"""
    stats = get_gpu_stats()
    if stats:
        logger.info(f"{prefix}GPU状态: 利用率={stats['gpu_util']}, 显存={stats['mem_used']}/{stats['mem_total']} ({stats['mem_percent']}), 温度={stats['temperature']}")
    return stats


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
        # 添加超时保护：ffmpeg录制60秒，但给它75秒的超时时间
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

        # 触发视频分析任务（异步执行）
        analyze_video_for_person.delay(log.id)

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


@shared_task(
    bind=True,
    max_retries=3,
    time_limit=300,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def analyze_video_for_person(self, record_log_id):
    """
    分析视频中的人物并保存截图

    Args:
        record_log_id: RecordLog 的 ID
    """
    from apps.cameras.models import RecordLog, PersonDetection
    import gc

    model = None
    cap = None

    try:
        # 获取录制日志
        log = RecordLog.objects.get(id=record_log_id)

        # 标记为检测中
        log.analysis_status = 'processing'
        log.save(update_fields=['analysis_status'])

        if not log.file_path or not os.path.exists(log.file_path):
            logger.error(f"视频文件不存在: {log.file_path}")
            log.analysis_status = 'failed'
            log.save(update_fields=['analysis_status'])
            return f"视频文件不存在"

        # 获取配置
        pics_base_dir = os.getenv('PICS_BASE_DIR', '/workspace/ai_project_data/camera_env/server_sync/ResouceData/CameraWarningPics')
        model_path = os.getenv('YOLO_MODEL_PATH', 'yolov8n.pt')
        sample_interval = int(os.getenv('DETECTION_SAMPLE_INTERVAL', '1'))
        confidence_threshold = float(os.getenv('DETECTION_CONFIDENCE_THRESHOLD', '0.5'))
        dedup_window = int(os.getenv('DETECTION_DEDUP_WINDOW', '10'))
        batch_size = int(os.getenv('DETECTION_BATCH_SIZE', '8'))  # 减小批处理大小
        use_gpu = os.getenv('USE_GPU', 'True').lower() in ('true', '1', 't')

        logger.info(f"开始分析视频: {log.file_path}")
        logger.info(f"配置: 采样间隔={sample_interval}s, 置信度={confidence_threshold}, GPU={use_gpu}")

        # 打印初始 GPU 状态
        log_gpu_stats("【任务开始】")

        # 清理 GPU 缓存
        if use_gpu and torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

        # 加载 YOLO 模型
        device = 'cuda' if use_gpu and torch.cuda.is_available() else 'cpu'

        # 使用上下文管理器确保资源释放
        model = YOLO(model_path)

        if device == 'cuda':
            # 设置 CUDA 环境变量避免多进程冲突
            os.environ['CUDA_LAUNCH_BLOCKING'] = '1'
            model.to(device)
        else:
            model.to(device)

        logger.info(f"YOLO 模型加载完成，使用设备: {device}")
        log_gpu_stats("【模型加载后】")

        # 打开视频
        cap = cv2.VideoCapture(log.file_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        logger.info(f"视频信息: FPS={fps}, 总帧数={total_frames}, 时长={duration:.1f}秒")

        # 创建输出目录
        video_filename = os.path.basename(log.file_path).replace('.mp4', '')
        # 从视频路径提取日期信息
        video_dir = os.path.dirname(log.file_path)
        # 例如: /path/to/192.168.0.201/2025/11/18/20/02.mp4
        path_parts = video_dir.split(os.sep)
        camera_ip = log.camera_ip

        # 查找年月日时的位置
        year, month, day, hour = None, None, None, None
        for i, part in enumerate(path_parts):
            if part == camera_ip and i + 4 < len(path_parts):
                year = path_parts[i + 1]
                month = path_parts[i + 2]
                day = path_parts[i + 3]
                hour = path_parts[i + 4]
                break

        if year and month and day and hour:
            output_dir = os.path.join(pics_base_dir, camera_ip, year, month, day, hour)
        else:
            # 备用方案：使用当前时间
            now = datetime.now()
            output_dir = os.path.join(pics_base_dir, camera_ip, now.strftime("%Y/%m/%d/%H"))

        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"输出目录: {output_dir}")

        # 采样帧并批量检测
        frames_to_process = []
        frame_info = []  # 存储 (frame_number, timestamp)

        frame_interval = int(fps * sample_interval) if fps > 0 else 30
        current_frame = 0
        detection_count = 0
        last_detection_time = -dedup_window  # 上次检测到人物的时间

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 按间隔采样
            if current_frame % frame_interval == 0:
                timestamp = current_frame / fps if fps > 0 else 0
                frames_to_process.append(frame)
                frame_info.append((current_frame, timestamp))

                # 批量处理
                if len(frames_to_process) >= batch_size:
                    result = process_batch(
                        model, frames_to_process, frame_info, log, output_dir,
                        video_filename, confidence_threshold, dedup_window,
                        last_detection_time
                    )
                    detection_count += result['count']
                    if result['last_time'] is not None:
                        last_detection_time = result['last_time']
                    frames_to_process = []
                    frame_info = []

            current_frame += 1

        # 处理剩余的帧
        if frames_to_process:
            result = process_batch(
                model, frames_to_process, frame_info, log, output_dir,
                video_filename, confidence_threshold, dedup_window,
                last_detection_time
            )
            detection_count += result['count']

        cap.release()

        # 标记为检测完成
        log.analysis_status = 'completed'
        log.analysis_time = timezone.now()
        log.save(update_fields=['analysis_status', 'analysis_time'])

        # 打印最终 GPU 状态
        log_gpu_stats("【分析完成】")

        logger.info(f"视频分析完成: {log.file_path}, 检测到 {detection_count} 个人物")
        return f"分析完成，检测到 {detection_count} 个人物"

    except RecordLog.DoesNotExist:
        logger.error(f"RecordLog {record_log_id} 不存在")
        return "录制日志不存在"

    except Exception as e:
        logger.error(f"视频分析失败: {str(e)}", exc_info=True)
        # 标记为检测失败
        try:
            log = RecordLog.objects.get(id=record_log_id)
            log.analysis_status = 'failed'
            log.save(update_fields=['analysis_status'])
        except:
            pass
        raise

    finally:
        # 清理资源
        if cap is not None:
            try:
                cap.release()
            except:
                pass

        if model is not None:
            try:
                del model
            except:
                pass

        # 清理 GPU 缓存
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        gc.collect()
        logger.info(f"资源已清理")


def process_batch(model, frames, frame_info, log, output_dir, video_filename,
                  confidence_threshold, dedup_window, last_detection_time):
    """
    批量处理帧并保存检测结果

    Returns:
        dict: {'count': 检测数量, 'last_time': 最后检测时间}
    """
    from apps.cameras.models import PersonDetection

    detection_count = 0
    last_time = last_detection_time

    # 批量推理
    results = model(frames, verbose=False)

    for i, (result, (frame_number, timestamp)) in enumerate(zip(results, frame_info)):
        # 检查是否检测到人物 (class 0 = person in COCO dataset)
        person_detections = []

        for box in result.boxes:
            if int(box.cls[0]) == 0:  # person class
                confidence = float(box.conf[0])
                if confidence >= confidence_threshold:
                    person_detections.append({
                        'confidence': confidence,
                        'bbox': box.xyxy[0].cpu().numpy().tolist()
                    })

        # 如果检测到人物
        if person_detections:
            # 去重：检查时间窗口
            if timestamp - last_time >= dedup_window:
                # 保存最高置信度的检测
                best_detection = max(person_detections, key=lambda x: x['confidence'])

                # 保存图片
                image_filename = f"{video_filename}_frame_{frame_number:05d}_person.jpg"
                image_path = os.path.join(output_dir, image_filename)
                cv2.imwrite(image_path, frames[i])

                # 保存到数据库
                PersonDetection.objects.create(
                    record_log=log,
                    frame_number=frame_number,
                    timestamp=timestamp,
                    image_path=image_path,
                    confidence=best_detection['confidence'],
                    bbox=best_detection['bbox']
                )

                detection_count += 1
                last_time = timestamp

                logger.debug(f"保存人物检测: 帧{frame_number}, 时间{timestamp:.1f}s, 置信度{best_detection['confidence']:.2f}")

    return {'count': detection_count, 'last_time': last_time if detection_count > 0 else None}
