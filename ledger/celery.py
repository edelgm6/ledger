from __future__ import absolute_import, unicode_literals

import os

from celery import Celery

# Set default Django settings module for 'celery'
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledger.settings")

app = Celery("ledger")

# Configure Celery to use settings from Django settings.py with 'CELERY_' prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Automatically discover tasks in installed apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
