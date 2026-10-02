FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /app/storage/evidence /app/storage/outputs /app/models
CMD ["celery", "-A", "app.celery_app.celery_app", "worker", "--loglevel=info"]
