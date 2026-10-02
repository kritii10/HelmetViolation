import os
from pathlib import Path
from uuid import uuid4

import cv2
import httpx
import pandas as pd

from .celery_app import celery_app
from .config import Settings
from .pipeline import VideoPipeline

VIOLATION_SERVICE_URL = os.getenv("VIOLATION_SERVICE_URL", "http://violation-service:8002")


def update_job(job_id: str, payload: dict) -> None:
    httpx.patch(f"{VIOLATION_SERVICE_URL}/jobs/{job_id}", json=payload, timeout=20).raise_for_status()


def public_path(path: Path) -> str:
    return "/storage/" + str(path.relative_to("/app/storage"))


def save_event(job_id: str, event: dict, fps: float, output_path: Path) -> dict:
    folder = Path("/app/storage/evidence") / job_id; folder.mkdir(parents=True, exist_ok=True)
    frame_path = folder / f"{uuid4().hex}_no_helmet.jpg"; cv2.imwrite(str(frame_path), event["frame"])
    first, confirmed = event["first_frame"] / fps, event["confirmation_frame"] / fps
    payload = {"job_id": job_id, "confidence": event["confidence"], "timestamp": confirmed, "duration": confirmed - first, "supporting_frames": event["supporting_frames"], "evidence": [{"evidence_type": "frame", "filepath": public_path(frame_path), "confidence": event["confidence"]}, {"evidence_type": "annotated_video", "filepath": public_path(output_path), "confidence": event["confidence"]}]}
    response = httpx.post(f"{VIOLATION_SERVICE_URL}/violations", json=payload, timeout=30); response.raise_for_status()
    return {"violation_id": response.json()["violation_id"], "confidence": event["confidence"], "timestamp": confirmed, "duration": confirmed - first, "supporting_frames": event["supporting_frames"], "evidence_path": public_path(frame_path)}


@celery_app.task(name="video_processor.process_video", bind=True)
def process_video(self, job_id: str, video_path: str, video_id: str) -> dict:
    """Process a video with one helmet/no-helmet YOLO model."""
    capture = writer = None
    try:
        update_job(job_id, {"status": "processing", "progress": 0})
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened(): raise ValueError("OpenCV could not open the uploaded video")
        fps, width, height = float(capture.get(cv2.CAP_PROP_FPS)), int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0 or not width or not height: raise ValueError("Video has invalid FPS or resolution")
        pipeline = VideoPipeline(Settings())
        output_path = Path("/app/storage/outputs") / f"{job_id}_annotated.mp4"; output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened(): raise ValueError("OpenCV could not create annotated output video")
        rows, frame_number = [], 0
        while True:
            ok, frame = capture.read()
            if not ok: break
            annotated, events = pipeline.process_frame(frame, frame_number); writer.write(annotated)
            rows.extend(save_event(job_id, event, fps, output_path) for event in events)
            frame_number += 1
            if frame_number % 100 == 0: update_job(job_id, {"status": "processing", "progress": min(99, round(frame_number / max(total, 1) * 100))})
        report_path = Path("/app/storage/outputs") / f"{job_id}_violations.csv"
        pd.DataFrame(rows, columns=["violation_id", "confidence", "timestamp", "duration", "supporting_frames", "evidence_path"]).to_csv(report_path, index=False)
        httpx.patch(f"{VIOLATION_SERVICE_URL}/videos/{video_id}/duration", params={"value": frame_number / fps}, timeout=30).raise_for_status()
        update_job(job_id, {"status": "completed", "progress": 100})
        return {"job_id": job_id, "annotated_video_path": public_path(output_path), "report_path": public_path(report_path)}
    except Exception as exc:
        update_job(job_id, {"status": "failed", "progress": 0, "error_message": str(exc)})
        raise
    finally:
        if capture: capture.release()
        if writer: writer.release()
