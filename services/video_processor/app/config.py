import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    helmet_model_path: Path = Path(os.getenv("HELMET_MODEL_PATH", "/app/models/helmet_model.pt"))
    confidence: float = float(os.getenv("YOLO_CONFIDENCE", "0.40"))
    confirmation_frames: int = int(os.getenv("VIOLATION_CONFIRMATION_FRAMES", "4"))
    max_frame_gap: int = int(os.getenv("VIOLATION_MAX_FRAME_GAP", "1"))

    def missing_model(self) -> str | None:
        return None if self.helmet_model_path.is_file() else f"HELMET_MODEL_PATH ({self.helmet_model_path})"
