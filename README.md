# django_test

# supervisor维护这个进程写消息队列
command=/opt/conda/envs/camera_env/bin/python /workspace/blip2_nllb_data/django_test/manage.py record_camera

# celery建议开多个 worker，例如 4 个，用来消费，work进程会跑上面“record_camera“进程delay的代码
nohup celery -A django_test worker -l info --concurrency=4 > logs/celery_worker.log 2>&1 &

# 如果有100个worker需要10台子机子来跑，可以把work进程跑到这10台机子上，用上面的命令就好，需要保证这10台机子的代码是一样的

# 关闭进程
pkill -f "celery -A django_test"
pkill -f ffmpeg

# 检查
ps -ef | grep celery
ps -ef | grep ffmpeg

# 查看视频有没有生成日志
tail -f /var/log/mycamera/celery_worker.err

# 关闭 supervisord
supervisorctl -c /etc/supervisor/supervisord.conf shutdown

# 启动 supervisord 
supervisord -c /etc/supervisor/supervisord.conf

# 如果占用了可以删掉，然后重起
rm -f /var/run/supervisor.sock /var/run/supervisord.pid

