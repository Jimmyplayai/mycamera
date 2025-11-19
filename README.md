# MyCamera - 智能摄像头监控系统

基于 Django + Celery 的智能摄像头监控系统，支持 RTSP 视频流录制、YOLOv8 人物检测和 BLIP2 图片描述生成。

## 功能特性

- **视频录制**：自动从 RTSP 摄像头录制视频（每分钟 60 秒）
- **人物检测**：使用 YOLOv8 检测视频中的人物并截图
- **图片描述**：使用 BLIP2 模型生成图片描述（支持 8-bit 量化）
- **任务调度**：基于 Celery Beat 的定时任务管理
- **后台管理**：Django Admin 界面查看录制日志和检测结果

## 技术栈

- **框架**：Django 5.2
- **任务队列**：Celery + RabbitMQ
- **数据库**：MySQL 8.0
- **AI 模型**：
  - YOLOv8 (人物检测)
  - BLIP2-FLAN-T5-XL (图片描述)
- **进程管理**：Supervisor
- **视频处理**：FFmpeg

## 项目结构

```
mycamera/
├── apps/
│   ├── cameras/              # 摄像头应用
│   │   ├── models.py         # 数据模型
│   │   ├── tasks.py          # Celery 任务
│   │   ├── admin.py          # Admin 配置
│   │   └── management/
│   │       └── commands/
│   │           └── analyze_videos.py  # 批量分析命令
│   └── log/                  # 日志应用
├── config/
│   ├── settings.py           # Django 配置
│   ├── celery.py             # Celery 配置
│   └── urls.py               # URL 配置
├── .env.example              # 环境变量示例
├── .env.dev                  # 开发环境配置
├── .env.prod                 # 生产环境配置
└── manage.py
```

## 环境要求

- Python 3.10+
- MySQL 8.0+
- RabbitMQ 3.x
- Redis 6.x
- FFmpeg
- CUDA 11.x+ (GPU 支持)

## 快速开始

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd mycamera
```

### 2. 创建虚拟环境

```bash
conda create -n camera_env python=3.10
conda activate camera_env
```

### 3. 安装依赖

```bash
pip install django celery mysql-connector-python python-dotenv
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install ultralytics transformers bitsandbytes accelerate
pip install pytz opencv-python pillow
```

### 4. 配置环境变量

复制并编辑环境变量文件：

```bash
cp .env.example .env.dev
vim .env.dev
```

主要配置项：

```bash
# 数据库
DB_NAME=mycamera_db
DB_USER=root
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306

# Celery
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# 摄像头配置
CAMERA1_IP=192.168.0.201
CAMERA1_PORT=554
CAMERA1_USER=admin
CAMERA1_PASSWORD=your_password
CAMERA1_PATH=Streaming/Channels/101

CAMERA2_IP=192.168.0.202
CAMERA2_PORT=554
CAMERA2_USER=admin
CAMERA2_PASSWORD=your_password
CAMERA2_PATH=Streaming/Channels/101

# 存储路径
CAMERA_BASE_DIR=/path/to/CameraRecordings
PICS_BASE_DIR=/path/to/CameraWarningPics
```

### 5. 初始化数据库

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. 启动服务

#### 开发模式

```bash
# 启动 Django
python manage.py runserver

# 启动 Celery Worker（录制任务）
celery -A config worker -l info --concurrency=2 -Q celery -n record@%h

# 启动 Celery Worker（分析任务）
celery -A config worker -l info --concurrency=1 -Q video_analysis -n analysis@%h

# 启动 Celery Beat（定时任务）
celery -A config beat -l info
```

#### 生产模式（Supervisor）

配置文件位置：`/etc/supervisor/conf.d/`

```bash
# 启动所有服务
supervisord -c /etc/supervisor/supervisord.conf

# 查看状态
supervisorctl status

# 重启服务
supervisorctl restart celery_worker_record
supervisorctl restart celery_worker_analysis
supervisorctl restart celery_beat
```

## 数据模型

### RecordLog（录制日志）

| 字段 | 类型 | 说明 |
|------|------|------|
| camera_ip | CharField | 摄像头 IP |
| start_time | DateTimeField | 开始时间 |
| end_time | DateTimeField | 结束时间 |
| status | CharField | 状态 (success/failed/timeout) |
| file_path | CharField | 视频文件路径 |
| file_size | BigIntegerField | 文件大小 |
| analysis_status | CharField | 检测状态 |

### PersonDetection（人物检测）

| 字段 | 类型 | 说明 |
|------|------|------|
| record_log | ForeignKey | 关联录制日志 |
| frame_number | IntegerField | 帧序号 |
| timestamp | FloatField | 视频时间戳 |
| image_path | CharField | 截图路径 |
| confidence | FloatField | 检测置信度 |
| caption | TextField | 图片描述（英文） |
| caption_zh | TextField | 图片描述（中文） |

## 定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| record_camera_task | 每分钟 | 录制摄像头视频 |
| generate_captions_batch | 每 10 分钟 | 批量生成图片描述 |

## 管理命令

### 批量分析历史视频

```bash
# 分析所有未检测的视频
python manage.py analyze_videos

# 分析指定摄像头的视频
python manage.py analyze_videos --camera-ip 192.168.0.201

# 限制分析数量
python manage.py analyze_videos --limit 100

# 异步执行
python manage.py analyze_videos --async

# 强制重新分析
python manage.py analyze_videos --force
```

## 日志管理

日志文件位置：`/var/log/mycamera/`

- `celery_worker_record.log` - 录制任务日志
- `celery_worker_analysis.log` - 分析任务日志
- `celery_beat.log` - 定时任务日志

### 日志轮转配置

配置文件：`/etc/logrotate.d/mycamera`

```bash
/var/log/mycamera/*.log /var/log/mycamera/*.err {
    daily
    rotate 30
    missingok
    notifempty
    compress
    delaycompress
    dateext
    dateformat -%Y%m%d
    copytruncate
    sharedscripts
}
```

## 性能优化

### GPU 显存优化

BLIP2 模型使用 8-bit 量化，显存占用减少约 50%：

```python
model = Blip2ForConditionalGeneration.from_pretrained(
    model_path,
    load_in_8bit=True,
    device_map='auto',
    torch_dtype=torch.float16
)
```

### 数据库优化

当前表索引配置：

```python
indexes = [
    models.Index(fields=['-start_time']),
    models.Index(fields=['camera_ip']),
    models.Index(fields=['status']),
]
```

建议在数据量达到 100-300 万条时考虑分表。

## 常用命令

```bash
# 查看服务状态
supervisorctl status

# 重启所有 Celery Worker
supervisorctl restart celery_worker_record celery_worker_analysis

# 查看实时日志
tail -f /var/log/mycamera/celery_worker_analysis.log

# 检查数据库连接
python manage.py dbshell

# 进入 Django Shell
python manage.py shell

# 关闭进程
pkill -f "celery -A config"
pkill -f ffmpeg

# 检查进程
ps -ef | grep celery
ps -ef | grep ffmpeg
```

## 故障排查

### Celery Worker 无法连接 RabbitMQ

```bash
# 检查 RabbitMQ 状态
systemctl status rabbitmq-server

# 查看队列
rabbitmqctl list_queues
```

### GPU 显存不足

```bash
# 查看 GPU 状态
nvidia-smi

# 清理 GPU 缓存
python -c "import torch; torch.cuda.empty_cache()"
```

### 视频录制失败

```bash
# 测试 RTSP 连接
ffmpeg -i "rtsp://user:pass@ip:port/path" -t 5 test.mp4

# 检查 FFmpeg 版本
ffmpeg -version
```

### Supervisor 问题

```bash
# 关闭 supervisord
supervisorctl -c /etc/supervisor/supervisord.conf shutdown

# 启动 supervisord
supervisord -c /etc/supervisor/supervisord.conf

# 如果端口被占用，删除 socket 文件后重启
rm -f /var/run/supervisor.sock /var/run/supervisord.pid
supervisord -c /etc/supervisor/supervisord.conf
```

## 注意事项

1. **存储空间**：每个摄像头每天约产生 1440 个视频文件，注意磁盘空间
2. **GPU 资源**：YOLOv8 和 BLIP2 任务会占用 GPU，建议错峰执行
3. **网络带宽**：多摄像头录制时注意网络带宽限制
4. **数据备份**：定期备份 MySQL 数据库

## License

MIT License
