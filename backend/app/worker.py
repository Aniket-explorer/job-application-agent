from celery import Celery
from app.config import settings

celery_app = Celery("job_agent", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    timezone="UTC", enable_utc=True,
    beat_schedule={
        # Dispatches a placeholder scan task every hour. Provider connectors are unconfigured by default.
        "hourly-source-scan": {"task": "app.tasks.hourly_scan", "schedule": 3600.0},
    },
)
celery_app.autodiscover_tasks(["app"])
