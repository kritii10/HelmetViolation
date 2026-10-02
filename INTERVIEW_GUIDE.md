# Helmet-only system notes

The system uses a single Ultralytics YOLO detection model for `helmet` and `no_helmet`. OpenCV reads and annotates video frames. Celery performs the long-running work asynchronously after RabbitMQ receives a task. FastAPI validates HTTP requests and the violation service writes parameterized raw SQL through psycopg. PostgreSQL stores videos, jobs, no-helmet violations, and evidence.

IoU vehicle tracking, seatbelt detection, license plate detection, OCR, and multiple violation types are not part of this helmet-only version.
