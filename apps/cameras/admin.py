from django.contrib import admin
from django.utils.html import format_html
from .models import RecordLog, PersonDetection


@admin.register(RecordLog)
class RecordLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'camera_ip', 'start_time_display', 'duration_display', 'status_display', 'file_size_display', 'detection_count_display', 'video_url_display']
    list_filter = ['status', 'analysis_status', 'camera_ip', 'start_time']
    search_fields = ['camera_ip', 'task_id', 'file_path', 'error_message']
    readonly_fields = ['task_id', 'start_time', 'end_time', 'duration_display', 'video_preview', 'detection_summary']
    date_hierarchy = 'start_time'
    list_per_page = 50
    actions = ['analyze_selected_videos', 'reanalyze_selected_videos']

    fieldsets = (
        ('基本信息', {
            'fields': ('camera_ip', 'camera_user', 'task_id', 'status')
        }),
        ('时间信息', {
            'fields': ('start_time', 'end_time', 'duration_display')
        }),
        ('文件信息', {
            'fields': ('file_path', 'file_size', 'video_preview', 'detection_summary')
        }),
        ('错误信息', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )

    def start_time_display(self, obj):
        """格式化开始时间"""
        return obj.start_time.strftime('%Y-%m-%d %H:%M:%S')
    start_time_display.short_description = '开始时间'

    def duration_display(self, obj):
        """显示时长"""
        duration = obj.duration()
        if duration is not None:
            return f"{duration:.1f}秒"
        return "-"
    duration_display.short_description = '录制时长'

    def status_display(self, obj):
        """彩色状态显示"""
        colors = {
            'success': 'green',
            'failed': 'red',
            'timeout': 'orange',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = '状态'

    def file_size_display(self, obj):
        """格式化文件大小"""
        if obj.file_size:
            size_mb = obj.file_size / (1024 * 1024)
            return f"{size_mb:.2f} MB"
        return "-"
    file_size_display.short_description = '文件大小'

    def video_url_display(self, obj):
        """显示视频链接（可点击查看）"""
        video_url = obj.get_video_url()
        if video_url:
            return format_html(
                '<a href="{}" target="_blank" style="color: #0066cc; text-decoration: underline;">查看视频</a>',
                video_url
            )
        return "-"
    video_url_display.short_description = '视频路径'

    def video_preview(self, obj):
        """在详情页显示视频预览"""
        video_url = obj.get_video_url()
        if video_url:
            return format_html(
                '''
                <div style="margin-top: 10px;">
                    <p><strong>视频URL：</strong><a href="{}" target="_blank">{}</a></p>
                    <video width="640" height="360" controls style="margin-top: 10px;">
                        <source src="{}" type="video/mp4">
                        您的浏览器不支持视频播放。
                    </video>
                </div>
                ''',
                video_url, video_url, video_url
            )
        return "-"
    video_preview.short_description = '视频预览'

    def detection_count_display(self, obj):
        """显示检测到的人物数量和分析状态"""
        count = obj.detections.count()

        # 根据分析状态显示不同内容
        if obj.analysis_status == 'pending':
            return format_html('<span style="color: #999; font-style: italic;">⏳ 待检测</span>')
        elif obj.analysis_status == 'processing':
            return format_html('<span style="color: #0066cc; font-weight: bold;">🔄 检测中...</span>')
        elif obj.analysis_status == 'failed':
            return format_html('<span style="color: #ff4444; font-weight: bold;">❌ 检测失败</span>')
        elif obj.analysis_status == 'completed':
            if count > 0:
                from django.urls import reverse
                url = reverse('admin:cameras_persondetection_changelist') + f'?record_log__id__exact={obj.id}'
                return format_html(
                    '<a href="{}" style="color: #28a745; font-weight: bold;">✓ {} 个人物</a>',
                    url, count
                )
            else:
                return format_html('<span style="color: #999;">✓ 已检测 - 无人物</span>')
        else:
            # 兼容旧数据（没有 analysis_status 字段时）
            if count > 0:
                from django.urls import reverse
                url = reverse('admin:cameras_persondetection_changelist') + f'?record_log__id__exact={obj.id}'
                return format_html(
                    '<a href="{}" style="color: #0066cc; font-weight: bold;">{} 个人物</a>',
                    url, count
                )
            return format_html('<span style="color: #999;">无检测</span>')
    detection_count_display.short_description = '人物检测'

    def detection_summary(self, obj):
        """显示人物检测摘要"""
        detections = obj.detections.all()[:10]  # 只显示前10个
        total_count = obj.detections.count()

        html = '<div style="margin-top: 10px;">'

        # 显示分析状态
        status_colors = {
            'pending': '#999',
            'processing': '#0066cc',
            'completed': '#28a745',
            'failed': '#ff4444'
        }
        status_text = obj.get_analysis_status_display() if hasattr(obj, 'analysis_status') else '未知'
        status_color = status_colors.get(obj.analysis_status, '#999')

        html += f'<p><strong>分析状态：</strong><span style="color: {status_color}; font-weight: bold;">{status_text}</span></p>'

        if obj.analysis_time:
            analysis_time_str = obj.analysis_time.strftime('%Y-%m-%d %H:%M:%S')
            html += f'<p><strong>分析时间：</strong>{analysis_time_str}</p>'

        if total_count == 0:
            if obj.analysis_status == 'completed':
                html += '<p style="color: #999; margin-top: 10px;">✓ 已完成检测，未发现人物</p>'
            elif obj.analysis_status == 'pending':
                html += '<p style="color: #999; margin-top: 10px;">⏳ 等待分析...</p>'
            elif obj.analysis_status == 'processing':
                html += '<p style="color: #0066cc; margin-top: 10px;">🔄 正在分析中...</p>'
            elif obj.analysis_status == 'failed':
                html += '<p style="color: #ff4444; margin-top: 10px;">❌ 分析失败</p>'
            else:
                html += '<p style="color: #999; margin-top: 10px;">暂无人物检测记录</p>'
            html += '</div>'
            return format_html(html)

        from django.urls import reverse
        list_url = reverse('admin:cameras_persondetection_changelist') + f'?record_log__id__exact={obj.id}'

        html += f'<p style="margin-top: 10px;"><strong>检测到 {total_count} 个人物</strong> '
        html += f'<a href="{list_url}" target="_blank" style="color: #0066cc;">查看全部 →</a></p>'
        html += '<div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px;">'

        for detection in detections:
            image_url = detection.get_image_url()
            if image_url:
                detail_url = reverse('admin:cameras_persondetection_change', args=[detection.id])
                timestamp_str = f'{detection.timestamp:.1f}'
                confidence_str = f'{detection.confidence * 100:.0f}'
                html += f'''
                <div style="border: 1px solid #ddd; padding: 5px; border-radius: 4px; text-align: center;">
                    <a href="{detail_url}" target="_blank">
                        <img src="{image_url}" style="width: 120px; height: auto; display: block;"/>
                    </a>
                    <small style="color: #666;">帧{detection.frame_number} | {timestamp_str}s | {confidence_str}%</small>
                </div>
                '''

        html += '</div>'
        if total_count > 10:
            html += f'<p style="margin-top: 10px; color: #666;">还有 {total_count - 10} 个检测结果未显示</p>'
        html += '</div>'

        return format_html(html)
    detection_summary.short_description = '人物检测摘要'

    def analyze_selected_videos(self, request, queryset):
        """批量分析选中的视频（跳过已分析的）"""
        from apps.cameras.tasks import analyze_video_for_person
        import os

        # 只处理成功录制且未分析的视频（状态为 pending 或 failed）
        queryset = queryset.filter(status='success').exclude(analysis_status='completed')

        analyzed_count = 0
        skipped_count = 0

        for record in queryset:
            if not record.file_path or not os.path.exists(record.file_path):
                skipped_count += 1
                continue

            # 跳过正在处理中的
            if record.analysis_status == 'processing':
                skipped_count += 1
                continue

            # 异步执行分析任务
            analyze_video_for_person.delay(record.id)
            analyzed_count += 1

        if analyzed_count > 0:
            self.message_user(
                request,
                f'已提交 {analyzed_count} 个视频到分析队列，跳过 {skipped_count} 个（文件不存在、正在分析或已完成）',
                level='success'
            )
        else:
            self.message_user(
                request,
                f'没有可分析的视频（已跳过 {skipped_count} 个）',
                level='warning'
            )

    analyze_selected_videos.short_description = '分析选中的视频（跳过已分析）'

    def reanalyze_selected_videos(self, request, queryset):
        """批量重新分析选中的视频（删除旧记录）"""
        from apps.cameras.tasks import analyze_video_for_person
        import os

        # 只处理成功录制的视频
        queryset = queryset.filter(status='success')

        analyzed_count = 0
        skipped_count = 0
        deleted_count = 0

        for record in queryset:
            if not record.file_path or not os.path.exists(record.file_path):
                skipped_count += 1
                continue

            # 删除已有的检测记录
            old_detections = record.detections.count()
            if old_detections > 0:
                record.detections.all().delete()
                deleted_count += old_detections

            # 重置分析状态
            record.analysis_status = 'pending'
            record.analysis_time = None
            record.save(update_fields=['analysis_status', 'analysis_time'])

            # 异步执行分析任务
            analyze_video_for_person.delay(record.id)
            analyzed_count += 1

        if analyzed_count > 0:
            self.message_user(
                request,
                f'已提交 {analyzed_count} 个视频到分析队列，删除了 {deleted_count} 条旧记录，跳过 {skipped_count} 个（文件不存在）',
                level='success'
            )
        else:
            self.message_user(
                request,
                f'没有可分析的视频（已跳过 {skipped_count} 个）',
                level='warning'
            )

    reanalyze_selected_videos.short_description = '重新分析选中的视频（覆盖旧记录）'


@admin.register(PersonDetection)
class PersonDetectionAdmin(admin.ModelAdmin):
    list_display = ['id', 'camera_ip_display', 'record_log_link', 'frame_number', 'timestamp_display', 'confidence_display', 'caption_status_display', 'image_preview_thumb', 'created_at_display']
    list_filter = ['caption_status', 'record_log__camera_ip', 'created_at']
    search_fields = ['record_log__camera_ip', 'record_log__file_path', 'image_path', 'caption']
    readonly_fields = ['record_log', 'frame_number', 'timestamp', 'image_path', 'confidence', 'bbox', 'created_at', 'caption_generated_at', 'image_preview_large']
    date_hierarchy = 'created_at'
    list_per_page = 50
    ordering = ['-created_at']
    actions = ['generate_captions_for_selected', 'generate_captions_for_all_pending']

    fieldsets = (
        ('关联信息', {
            'fields': ('record_log',)
        }),
        ('检测信息', {
            'fields': ('frame_number', 'timestamp', 'confidence', 'bbox')
        }),
        ('图片信息', {
            'fields': ('image_path', 'image_preview_large', 'created_at')
        }),
        ('图片描述', {
            'fields': ('caption_status', 'caption', 'caption_zh', 'keywords', 'caption_generated_at'),
            'classes': ('collapse',)
        }),
    )

    def camera_ip_display(self, obj):
        """显示摄像头IP"""
        return obj.record_log.camera_ip
    camera_ip_display.short_description = '摄像头IP'
    camera_ip_display.admin_order_field = 'record_log__camera_ip'

    def record_log_link(self, obj):
        """显示录制日志链接"""
        from django.urls import reverse
        url = reverse('admin:cameras_recordlog_change', args=[obj.record_log.id])
        return format_html(
            '<a href="{}" target="_blank">录制记录 #{}</a>',
            url, obj.record_log.id
        )
    record_log_link.short_description = '关联录制'

    def timestamp_display(self, obj):
        """格式化时间戳"""
        return f"{obj.timestamp:.1f}秒"
    timestamp_display.short_description = '视频时间'
    timestamp_display.admin_order_field = 'timestamp'

    def confidence_display(self, obj):
        """显示置信度（带颜色）"""
        percentage = obj.confidence * 100
        if percentage >= 80:
            color = 'green'
        elif percentage >= 60:
            color = 'orange'
        else:
            color = 'red'
        percentage_str = f'{percentage:.1f}'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}%</span>',
            color, percentage_str
        )
    confidence_display.short_description = '置信度'
    confidence_display.admin_order_field = 'confidence'

    def created_at_display(self, obj):
        """格式化创建时间"""
        return obj.created_at.strftime('%Y-%m-%d %H:%M:%S')
    created_at_display.short_description = '检测时间'
    created_at_display.admin_order_field = 'created_at'

    def image_preview_thumb(self, obj):
        """列表页缩略图"""
        image_url = obj.get_image_url()
        if image_url:
            return format_html(
                '<a href="{}" target="_blank"><img src="{}" style="width: 100px; height: auto; border: 1px solid #ddd; border-radius: 4px;"/></a>',
                image_url, image_url
            )
        return "-"
    image_preview_thumb.short_description = '缩略图'

    def image_preview_large(self, obj):
        """详情页大图预览"""
        from django.utils.safestring import mark_safe

        image_url = obj.get_image_url()
        if image_url:
            bbox_html = ""
            if obj.bbox:
                bbox_html = f"<p><strong>边界框坐标：</strong>{obj.bbox}</p>"

            caption_html = ""
            if obj.caption:
                caption_html = f'''
                <div style="margin-top: 10px; padding: 10px; background: #f0f8ff; border-left: 4px solid #0066cc; border-radius: 4px;">
                    <p style="margin: 0;"><strong>图片描述：</strong>{obj.caption}</p>
                </div>
                '''

            html = f'''
            <div style="margin-top: 10px;">
                <p><strong>图片URL：</strong><a href="{image_url}" target="_blank">{image_url}</a></p>
                {bbox_html}
                {caption_html}
                <img src="{image_url}" style="max-width: 800px; height: auto; border: 2px solid #0066cc; border-radius: 8px; margin-top: 10px;"/>
            </div>
            '''
            return mark_safe(html)
        return "-"
    image_preview_large.short_description = '图片预览'

    def caption_status_display(self, obj):
        """显示描述生成状态（带颜色和图标）"""
        status_info = {
            'pending': {'color': '#999', 'icon': '⏳', 'text': '待生成'},
            'processing': {'color': '#0066cc', 'icon': '🔄', 'text': '生成中'},
            'completed': {'color': '#28a745', 'icon': '✓', 'text': '已完成'},
            'failed': {'color': '#ff4444', 'icon': '❌', 'text': '失败'},
        }
        info = status_info.get(obj.caption_status, {'color': '#999', 'icon': '?', 'text': obj.caption_status})

        # 如果已完成，显示描述
        if obj.caption_status == 'completed' and obj.caption:
            # 尽量显示更多内容，超过100字符才省略
            max_length = 100
            display_text = obj.caption if len(obj.caption) <= max_length else obj.caption[:max_length] + '...'

            # 完整内容用于鼠标悬停显示
            full_caption = obj.caption.replace('"', '&quot;').replace("'", '&#39;')

            return format_html(
                '<span style="color: {}; font-weight: bold;">{} {}</span><br/>'
                '<small style="color: #666; cursor: help; display: block; max-width: 300px; word-wrap: break-word;" title="{}">{}</small>',
                info['color'], info['icon'], info['text'], full_caption, display_text
            )

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            info['color'], info['icon'], info['text']
        )
    caption_status_display.short_description = '描述状态'
    caption_status_display.admin_order_field = 'caption_status'

    def generate_captions_for_selected(self, request, queryset):
        """只为用户选中的记录生成描述"""
        from apps.cameras.tasks import generate_captions_batch

        # 获取选中记录中 pending 状态的
        pending_queryset = queryset.filter(caption_status='pending')
        pending_count = pending_queryset.count()
        selected_count = queryset.count()

        if pending_count == 0:
            self.message_user(
                request,
                f'选中的 {selected_count} 条记录中，没有待处理的图片（caption_status=pending）',
                level='warning'
            )
            return

        # 获取 ID 列表
        pending_ids = list(pending_queryset.values_list('id', flat=True))

        # 传递给任务
        result = generate_captions_batch.delay(detection_ids=pending_ids)

        self.message_user(
            request,
            f'✓ 已提交批量描述生成任务到队列！\n'
            f'- 选中记录数: {selected_count} 条\n'
            f'- 待处理图片数: {pending_count} 张\n'
            f'- 任务ID: {result.id}\n'
            f'- 模型: BLIP2-FLAN-T5-XL\n'
            f'- 说明: 任务将在 video_analysis 队列中依次执行\n'
            f'- 提示: 刷新页面查看进度',
            level='success'
        )

    generate_captions_for_selected.short_description = '🎯 生成选中记录的描述'

    def generate_captions_for_all_pending(self, request, queryset):
        """手动触发 BLIP2 批量生成图片描述（处理所有 pending 状态的图片）"""
        from apps.cameras.tasks import generate_captions_batch

        # 查询所有 pending 状态的图片数量
        pending_count = self.model.objects.filter(caption_status='pending').count()

        if pending_count == 0:
            self.message_user(
                request,
                '当前没有待处理的图片（caption_status=pending）',
                level='warning'
            )
            return

        # 触发批量任务
        result = generate_captions_batch.delay()

        self.message_user(
            request,
            f'✓ 已提交批量描述生成任务到队列！\n'
            f'- 待处理图片数: {pending_count} 张\n'
            f'- 任务ID: {result.id}\n'
            f'- 模型: BLIP2-FLAN-T5-XL\n'
            f'- 说明: 任务将在 video_analysis 队列中依次执行，首次加载模型需要1-2分钟\n'
            f'- 提示: 刷新页面查看进度，或查看 Celery Worker 日志',
            level='success'
        )

    generate_captions_for_all_pending.short_description = '🚀 生成所有待处理图片的描述（忽略选择）'
