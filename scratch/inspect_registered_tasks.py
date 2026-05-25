import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django_celery_beat.models import PeriodicTask

print("=== REGISTERED PERIODIC TASKS IN PUBLIC SCHEMA ===")
connection.set_schema_to_public()

tasks = PeriodicTask.objects.select_related('crontab').all()
for task in tasks:
    print(f"Task Name: {task.name}")
    print(f"  Task: {task.task}")
    print(f"  Enabled: {task.enabled}")
    if task.crontab:
        print(f"  Crontab: minute='{task.crontab.minute}', hour='{task.crontab.hour}', day_of_week='{task.crontab.day_of_week}', day_of_month='{task.crontab.day_of_month}', month_of_year='{task.crontab.month_of_year}', timezone='{task.crontab.timezone}'")
    else:
        print("  Crontab: None")
    print("-" * 50)
