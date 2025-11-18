<<<<<<< HEAD
# app/management/commands/record_camera.py
from django.core.management.base import BaseCommand
from apps.cameras.tasks import record_camera_task
from dotenv import load_dotenv
import os
import time

load_dotenv(".env")
print("record_camera.py loaded")

class Command(BaseCommand):
    help = "触发摄像头录制任务"

    def handle(self, *args, **options):
        self.stdout.write("Hello")

        cameras = [
            {
                "ip": os.getenv("CAMERA1_IP"),
                "user": os.getenv("CAMERA1_USER"),
                "password": os.getenv("CAMERA1_PASSWORD"),
                "port": os.getenv("CAMERA1_PORT"),
                "path": os.getenv("CAMERA1_PATH"),
            },
            {
                "ip": os.getenv("CAMERA2_IP"),
                "user": os.getenv("CAMERA2_USER"),
                "password": os.getenv("CAMERA2_PASSWORD"),
                "port": os.getenv("CAMERA2_PORT"),
                "path": os.getenv("CAMERA2_PATH"),
            }
        ]

        print(cameras)
        while True:
            self.stdout.write(self.style.SUCCESS("所有摄像头任务已触发"))

            for cam in cameras:
                record_camera_task.delay(
                    cam["ip"], cam["user"], cam["password"], cam["port"], cam["path"]
                )
                time.sleep(60)  # 每分钟发一次

=======
# app/management/commands/record_camera.py
from django.core.management.base import BaseCommand
from apps.cameras.tasks import record_camera_task
from dotenv import load_dotenv
import os
import time

load_dotenv(".env")
print("record_camera.py loaded")

class Command(BaseCommand):
    help = "触发摄像头录制任务"

    def handle(self, *args, **options):
        self.stdout.write("Hello")

        cameras = [
            {
                "ip": os.getenv("CAMERA1_IP"),
                "user": os.getenv("CAMERA1_USER"),
                "password": os.getenv("CAMERA1_PASSWORD"),
                "port": os.getenv("CAMERA1_PORT"),
                "path": os.getenv("CAMERA1_PATH"),
            },
            {
                "ip": os.getenv("CAMERA2_IP"),
                "user": os.getenv("CAMERA2_USER"),
                "password": os.getenv("CAMERA2_PASSWORD"),
                "port": os.getenv("CAMERA2_PORT"),
                "path": os.getenv("CAMERA2_PATH"),
            }
        ]

        print(cameras)
        while True:
            self.stdout.write(self.style.SUCCESS("所有摄像头任务已触发"))

            for cam in cameras:
                record_camera_task.delay(
                    cam["ip"], cam["user"], cam["password"], cam["port"], cam["path"]
                )
                time.sleep(60)  # 每分钟发一次

>>>>>>> 32e9d818efa98600af0abb2f302c8b09dea5c96a
