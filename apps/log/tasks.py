from django_test import shared_task
from .models import LogEntry
import datetime

@shared_task
def count_today_entries():
    today = datetime.date.today()
    entries = LogEntry.objects.filter(created_at__date=today)
    print(f"Today entries: {len(entries)}")
    return len(entries)