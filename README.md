# Helmet Traffic Violation Detection System

This project detects confirmed `no_helmet` observations in uploaded traffic videos. It uses one Ultralytics YOLO model, OpenCV, Celery/RabbitMQ, PostgreSQL with raw `psycopg` SQL, and a React dashboard.

```text
React → FastAPI API Gateway → RabbitMQ → Celery worker → YOLO/OpenCV
                                                    ↓
                                           PostgreSQL + evidence + annotated MP4
```

## Model setup

Place one legitimate Ultralytics detection weight file at:

```text
models/helmet_model.pt
```

Set this environment variable (already shown in `.env.example`):

```env
HELMET_MODEL_PATH=/app/models/helmet_model.pt
```

The model must expose exactly the relevant class names `helmet` and `no_helmet`. Only `no_helmet` observations are confirmed and saved. The project does not download, train, or include a model file.

## Run

```bash
cp .env.example .env
# Replace every CHANGE_ME value in .env.
docker compose up --build
```

Open http://localhost:5173. Upload a traffic video, start analysis, then view confirmed no-helmet evidence and download the CSV report.

The worker requires repeated nearby-frame `no_helmet` observations according to `VIOLATION_CONFIRMATION_FRAMES` before it saves one violation. It generates an annotated MP4, frame evidence, and a CSV report.

## Reset the database

```bash
docker compose down -v
docker compose up --build
```
