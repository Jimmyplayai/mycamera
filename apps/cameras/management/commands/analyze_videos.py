"""
批量分析历史视频中的人物
"""
from django.core.management.base import BaseCommand
from apps.cameras.models import RecordLog, PersonDetection
from apps.cameras.tasks import analyze_video_for_person
import os


class Command(BaseCommand):
    help = '批量分析历史视频中的人物'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='分析所有视频（包括已分析过的）',
        )
        parser.add_argument(
            '--camera-ip',
            type=str,
            help='只分析指定摄像头的视频',
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='开始日期（格式：2025-11-18）',
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='结束日期（格式：2025-11-18）',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='限制分析数量',
        )
        parser.add_argument(
            '--async',
            action='store_true',
            dest='async_mode',
            help='使用 Celery 异步执行（推荐用于大量视频）',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='强制重新分析（删除已有的检测记录）',
        )

    def handle(self, *args, **options):
        # 构建查询条件
        queryset = RecordLog.objects.filter(status='success')

        # 按摄像头IP过滤
        if options['camera_ip']:
            queryset = queryset.filter(camera_ip=options['camera_ip'])
            self.stdout.write(f"筛选摄像头: {options['camera_ip']}")

        # 按日期范围过滤
        if options['start_date']:
            queryset = queryset.filter(start_time__gte=options['start_date'])
            self.stdout.write(f"开始日期: {options['start_date']}")

        if options['end_date']:
            queryset = queryset.filter(start_time__lte=options['end_date'])
            self.stdout.write(f"结束日期: {options['end_date']}")

        # 如果不是分析所有，则只分析未检测的
        if not options['all'] and not options['force']:
            queryset = queryset.filter(detections__isnull=True)
            self.stdout.write("只分析未检测过的视频")

        # 限制数量
        if options['limit']:
            queryset = queryset[:options['limit']]
            self.stdout.write(f"限制数量: {options['limit']}")

        total_count = queryset.count()

        if total_count == 0:
            self.stdout.write(self.style.WARNING('没有找到符合条件的视频'))
            return

        self.stdout.write(self.style.SUCCESS(f'找到 {total_count} 个视频需要分析'))

        # 确认
        if not options['async_mode']:
            confirm = input(f'准备同步分析 {total_count} 个视频，这可能需要较长时间。继续？ (yes/no): ')
            if confirm.lower() not in ['yes', 'y']:
                self.stdout.write(self.style.WARNING('已取消'))
                return

        # 开始分析
        success_count = 0
        skip_count = 0
        error_count = 0

        for idx, record in enumerate(queryset, 1):
            # 检查视频文件是否存在
            if not record.file_path or not os.path.exists(record.file_path):
                self.stdout.write(
                    self.style.WARNING(f'[{idx}/{total_count}] 跳过: 视频文件不存在 - {record.file_path}')
                )
                skip_count += 1
                continue

            # 如果强制重新分析，删除已有的检测记录
            if options['force'] and record.detections.exists():
                deleted_count = record.detections.count()
                record.detections.all().delete()
                self.stdout.write(f'  删除了 {deleted_count} 条旧的检测记录')

            try:
                if options['async_mode']:
                    # 异步执行
                    task = analyze_video_for_person.delay(record.id)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[{idx}/{total_count}] 已提交异步任务: {record.camera_ip} - {record.file_path} (Task ID: {task.id})'
                        )
                    )
                else:
                    # 同步执行
                    self.stdout.write(f'[{idx}/{total_count}] 分析中: {record.camera_ip} - {record.file_path}')
                    result = analyze_video_for_person(record.id)
                    self.stdout.write(self.style.SUCCESS(f'  {result}'))

                success_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'[{idx}/{total_count}] 分析失败: {record.camera_ip} - {str(e)}')
                )
                error_count += 1

        # 总结
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'分析完成！'))
        self.stdout.write(f'  成功: {success_count}')
        self.stdout.write(f'  跳过: {skip_count}')
        self.stdout.write(f'  失败: {error_count}')
        self.stdout.write('='*60)

        if options['async_mode']:
            self.stdout.write('\n提示: 任务已提交到 Celery 队列，请查看 Celery 日志了解执行进度')
