import os
from celery import Celery

celery_app = Celery(
    "video_processor",
    broker=os.environ["RABBITMQ_URL"],
    include=["app.tasks"],
)
celery_app.conf.task_default_queue = "video_processing"
