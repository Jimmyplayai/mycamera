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


@shared_task(
    bind=True,
    max_retries=3,
    time_limit=600,
    soft_time_limit=540,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def generate_captions_batch(self, detection_ids=None):
    """
    批量生成图片描述（使用 BLIP2 模型）

    由 Celery Beat 定时触发，每10分钟执行一次
    查询所有 caption_status='pending' 的图片，批量生成英文描述

    Args:
        detection_ids: 可选，要处理的 PersonDetection ID 列表。
                      如果为 None，则处理所有 pending 状态的图片
    """
    from apps.cameras.models import PersonDetection
    from transformers import Blip2Processor, Blip2ForConditionalGeneration
    from PIL import Image
    from django.utils import timezone
    import gc

    model = None
    processor = None

    try:
        # 配置参数
        model_path = os.getenv('BLIP2_MODEL_PATH', '/workspace/ai_project_data/camera_env/model/blip2-flan-t5-xl')
        batch_size = int(os.getenv('BLIP2_BATCH_SIZE', '8'))  # 每批处理8张图片
        max_images = int(os.getenv('BLIP2_MAX_IMAGES', '100'))  # 一次最多处理100张
        use_gpu = os.getenv('USE_GPU', 'True').lower() in ('true', '1', 't')

        logger.info("=" * 60)
        logger.info("开始批量生成图片描述任务")
        logger.info(f"配置: 模型=blip2-flan-t5-xl, 批量大小={batch_size}, 最大数量={max_images}, GPU={use_gpu}")

        # 打印初始 GPU 状态
        log_gpu_stats("【BLIP2任务开始】")

        # 查询待处理的图片
        if detection_ids:
            # 只处理指定的 ID 列表
            pending_detections = PersonDetection.objects.filter(
                id__in=detection_ids,
                caption_status='pending'
            ).select_related('record_log').order_by('created_at')
            logger.info(f"指定处理 {len(detection_ids)} 个 ID")
        else:
            # 处理所有 pending 的记录
            pending_detections = PersonDetection.objects.filter(
                caption_status='pending'
            ).select_related('record_log').order_by('created_at')[:max_images]

        count = pending_detections.count()
        if count == 0:
            logger.info("没有待处理的图片，任务结束")
            return "没有待处理的图片"

        logger.info(f"找到 {count} 张待处理图片，开始批量处理...")

        # 清理 GPU 缓存
        if use_gpu and torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

        # 加载 BLIP2 模型
        device = 'cuda' if use_gpu and torch.cuda.is_available() else 'cpu'
        logger.info(f"开始加载 BLIP2 模型: {model_path} (使用8-bit量化)")

        processor = Blip2Processor.from_pretrained(model_path)

        if device == 'cuda':
            # 使用 8-bit 量化以减少显存占用和加快加载速度
            model = Blip2ForConditionalGeneration.from_pretrained(
                model_path,
                load_in_8bit=True,
                device_map='auto',
                torch_dtype=torch.float16
            )
            logger.info(f"BLIP2 模型加载完成 (8-bit量化)，使用设备: {device}")
        else:
            # CPU 模式不使用量化
            model = Blip2ForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=torch.float32
            )
            model.to(device)
            logger.info(f"BLIP2 模型加载完成，使用设备: {device}")
        log_gpu_stats("【BLIP2模型加载后】")

        # 批量处理图片
        processed_count = 0
        failed_count = 0
        total_batches = (count + batch_size - 1) // batch_size

        for batch_idx in range(0, count, batch_size):
            batch_num = batch_idx // batch_size + 1
            batch = list(pending_detections[batch_idx:batch_idx + batch_size])

            logger.info(f"处理第 {batch_num}/{total_batches} 批，共 {len(batch)} 张图片")

            # 加载图片
            images = []
            valid_detections = []

            for detection in batch:
                try:
                    if not os.path.exists(detection.image_path):
                        logger.warning(f"图片不存在: {detection.image_path}")
                        detection.caption_status = 'failed'
                        detection.save(update_fields=['caption_status'])
                        failed_count += 1
                        continue

                    img = Image.open(detection.image_path).convert('RGB')
                    images.append(img)
                    valid_detections.append(detection)

                except Exception as e:
                    logger.error(f"图片加载失败 {detection.image_path}: {e}")
                    detection.caption_status = 'failed'
                    detection.save(update_fields=['caption_status'])
                    failed_count += 1

            if not images:
                logger.warning(f"第 {batch_num} 批没有有效图片，跳过")
                continue

            # 批量推理
            try:
                logger.debug(f"开始推理 {len(images)} 张图片...")

                # 标记为处理中
                for detection in valid_detections:
                    detection.caption_status = 'processing'
                    detection.save(update_fields=['caption_status'])

                # BLIP2 推理
                inputs = processor(images=images, return_tensors="pt").to(device)

                with torch.no_grad():
                    generated_ids = model.generate(
                        **inputs,
                        max_length=50,
                        num_beams=5,  # 使用 beam search 提高质量
                        early_stopping=True
                    )

                captions = processor.batch_decode(generated_ids, skip_special_tokens=True)

                # 保存结果到数据库
                for detection, caption in zip(valid_detections, captions):
                    detection.caption = caption.strip()
                    detection.caption_status = 'completed'
                    detection.caption_generated_at = timezone.now()
                    detection.save(update_fields=['caption', 'caption_status', 'caption_generated_at'])
                    processed_count += 1

                    logger.debug(f"✓ {os.path.basename(detection.image_path)}: {caption}")

                logger.info(f"第 {batch_num} 批处理完成，成功 {len(valid_detections)} 张")

            except Exception as e:
                logger.error(f"第 {batch_num} 批推理失败: {e}", exc_info=True)
                # 将这批图片标记为失败
                for detection in valid_detections:
                    detection.caption_status = 'failed'
                    detection.save(update_fields=['caption_status'])
                failed_count += len(valid_detections)

        # 打印最终结果
        logger.info("=" * 60)
        logger.info(f"批量处理完成: 成功 {processed_count} 张, 失败 {failed_count} 张")
        log_gpu_stats("【BLIP2任务完成】")

        return f"批量生成图片描述完成: 成功 {processed_count} 张, 失败 {failed_count} 张"

    except Exception as e:
        logger.error(f"批量生成图片描述任务失败: {str(e)}", exc_info=True)
        raise

    finally:
        # 清理资源
        if model is not None:
            try:
                del model
            except:
                pass

        if processor is not None:
            try:
                del processor
            except:
                pass

        # 清理 GPU 缓存
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        gc.collect()
        logger.info("BLIP2 模型资源已释放")
