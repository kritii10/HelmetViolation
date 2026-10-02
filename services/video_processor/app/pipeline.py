from dataclasses import dataclass
from typing import Any

import cv2
from ultralytics import YOLO

from .config import Settings


@dataclass
class Detection:
    box: tuple[int, int, int, int]
    label: str
    confidence: float


@dataclass
class ViolationState:
    first_frame: int
    last_frame: int
    supporting_frames: int = 1
    reported: bool = False
    best_confidence: float = 0.0
    best_frame: Any = None


class VideoPipeline:
    def __init__(self, settings: Settings):
        missing = settings.missing_model()
        if missing:
            raise FileNotFoundError(f"Required YOLO weight is missing: {missing}")
        self.settings = settings
        self.model = YOLO(str(settings.helmet_model_path))
        self.state: ViolationState | None = None

    def process_frame(self, frame: Any, frame_number: int) -> tuple[Any, list[dict[str, Any]]]:
        result = self.model(frame, conf=self.settings.confidence, verbose=False)[0]
        detections = [Detection(tuple(map(int, box.xyxy[0].tolist())), str(result.names[int(box.cls[0])]).lower(), float(box.conf[0])) for box in result.boxes]
        no_helmet = [item for item in detections if item.label == "no_helmet"]
        event: list[dict[str, Any]] = []
        if no_helmet:
            best = max(no_helmet, key=lambda item: item.confidence)
            if self.state is None or frame_number - self.state.last_frame > self.settings.max_frame_gap + 1:
                self.state = ViolationState(frame_number, frame_number, best_confidence=best.confidence, best_frame=frame.copy())
            else:
                self.state.supporting_frames += 1; self.state.last_frame = frame_number
                if best.confidence >= self.state.best_confidence:
                    self.state.best_confidence, self.state.best_frame = best.confidence, frame.copy()
            if not self.state.reported and self.state.supporting_frames >= self.settings.confirmation_frames:
                self.state.reported = True
                event.append({"confidence": self.state.best_confidence, "first_frame": self.state.first_frame, "confirmation_frame": frame_number, "supporting_frames": self.state.supporting_frames, "frame": self.state.best_frame})
        for item in detections:
            x1, y1, x2, y2 = item.box
            confirmed = item.label == "no_helmet" and self.state is not None and self.state.reported
            colour = (0, 0, 255) if confirmed else (0, 200, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)
            cv2.putText(frame, f"{item.label} {item.confidence:.2f}", (x1, max(18, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, .55, colour, 2)
        return frame, event
