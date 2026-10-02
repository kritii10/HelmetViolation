import os
from celery import Celery

celery_client = Celery("api_gateway", broker=os.environ["RABBITMQ_URL"])
celery_client.conf.task_default_queue = "video_processing"
