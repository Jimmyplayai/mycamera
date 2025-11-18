# Django Settings
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Celery & Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
CELERY_TIMEZONE=Asia/Shanghai

# Camera Recording
CAMERA_BASE_DIR=/workspace/ai_project_data/camera_env/server_sync/ResouceData/CameraRecordingsMAX_RETRY=3
MAX_RETRY=3


CAMERA1_IP=192.168.0.201
CAMERA1_PORT=554
CAMERA1_USER=admin
CAMERA1_PASSWORD=chenhao105501
CAMERA1_PATH=Streaming/Channels/101

CAMERA2_IP=192.168.0.202
CAMERA2_PORT=554
CAMERA2_USER=admin
CAMERA2_PASSWORD=chenhao105501
CAMERA2_PATH=Streaming/Channels/101