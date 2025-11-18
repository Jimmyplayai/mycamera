from apps.log.tasks import count_today_entries

if __name__ == "__main__":
    count_today_entries.delay()
