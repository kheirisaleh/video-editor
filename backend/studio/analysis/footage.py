"""Classic computer vision analysis of footage.

Works on the low resolution proxies and needs no AI model. It finds shot boundaries,
scores every moment for sharpness, exposure and camera shake, locates the subject for
smart 9:16 cropping, and proposes the best candidate segments of each clip.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SAMPLE_FPS = 10.0
ANALYSIS_WIDTH = 320
CUT_THRESHOLD = 0.55
SEGMENT_SECONDS = 2.4
WINDOW_STEP = 0.4
EDGE_MARGIN = 0.25

_face_detector: cv2.CascadeClassifier | None = None


def _faces() -> cv2.CascadeClassifier:
    global _face_detector
    if _face_detector is None:
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        _face_detector = cv2.CascadeClassifier(str(path))
    return _face_detector


@dataclass
class Sample:
    t: float
    sharpness: float
    brightness: float
    motion: float
    subject_x: float
    face: bool


@dataclass
class Segment:
    clip_id: str
    start: float
    end: float
    score: float
    sharpness: float
    brightness: float
    motion: float
    face_ratio: float
    subject_x: float
    shot: int

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class ClipAnalysis:
    clip_id: str
    duration: float
    width: int
    height: int
    shots: list[tuple[float, float]] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    mean_brightness: float = 0.0
    mean_sharpness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sample_clip(
    path: Path, on_progress: Callable[[float], None] | None = None
) -> tuple[list[Sample], list[float], float, int, int]:
    """Read the proxy at SAMPLE_FPS and measure every sampled frame.

    Returns samples, cut times, duration and the frame size.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {path.name}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(int(round(fps / SAMPLE_FPS)), 1)

    samples: list[Sample] = []
    cuts: list[float] = []
    prev_gray: np.ndarray | None = None
    prev_hist: np.ndarray | None = None
    face_every = max(int(SAMPLE_FPS / 2), 1)
    last_subject = 0.5
    last_face = False
    index = 0
    sampled = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if index % step:
            index += 1
            continue
        ok, frame = cap.retrieve()
        if not ok:
            break
        t = index / fps
        scale = ANALYSIS_WIDTH / frame.shape[1]
        small = cv2.resize(
            frame, (ANALYSIS_WIDTH, int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA
        )
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(gray.mean())
        motion = float(cv2.absdiff(gray, prev_gray).mean()) if prev_gray is not None else 0.0

        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        if prev_hist is not None:
            similarity = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            if similarity < CUT_THRESHOLD and t > 0.3:
                cuts.append(round(t, 3))

        if sampled % face_every == 0:
            last_subject, last_face = _subject_position(gray)

        samples.append(
            Sample(
                t=round(t, 3),
                sharpness=sharpness,
                brightness=brightness,
                motion=motion,
                subject_x=last_subject,
                face=last_face,
            )
        )
        prev_gray, prev_hist = gray, hist
        sampled += 1
        index += 1
        if on_progress and total and sampled % 20 == 0:
            on_progress(min(index / total, 1.0))
    cap.release()
    duration = (index / fps) if index else 0.0
    return samples, cuts, duration, width, height


def _subject_position(gray: np.ndarray) -> tuple[float, bool]:
    """Horizontal centre of interest in 0..1: the largest face, else the edge energy."""
    faces = _faces().detectMultiScale(
        gray, scaleFactor=1.15, minNeighbors=5, minSize=(gray.shape[0] // 10, gray.shape[0] // 10)
    )
    if len(faces):
        x, _, w, _ = max(faces, key=lambda f: f[2] * f[3])
        return float((x + w / 2) / gray.shape[1]), True
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    energy = cv2.magnitude(gx, gy).sum(axis=0)
    if energy.sum() <= 0:
        return 0.5, False
    cols = np.arange(energy.size, dtype=np.float32)
    centre = float((energy * cols).sum() / energy.sum() / energy.size)
    # Edge energy is a weak signal, so pull it towards the middle.
    return 0.5 + (centre - 0.5) * 0.6, False


def analyze_clip(
    clip_id: str, proxy: Path, on_progress: Callable[[float], None] | None = None
) -> ClipAnalysis:
    samples, cuts, duration, width, height = sample_clip(proxy, on_progress)
    result = ClipAnalysis(clip_id=clip_id, duration=round(duration, 3), width=width, height=height)
    if not samples:
        return result

    bounds = [0.0, *cuts, duration]
    result.shots = [
        (round(a, 3), round(b, 3)) for a, b in zip(bounds, bounds[1:], strict=False) if b - a > 0.2
    ]
    sharp = np.array([s.sharpness for s in samples])
    result.mean_sharpness = float(sharp.mean())
    result.mean_brightness = float(np.mean([s.brightness for s in samples]))
    reference = float(np.percentile(sharp, 90)) or 1.0

    for shot_index, (a, b) in enumerate(result.shots):
        result.segments.extend(_best_windows(clip_id, shot_index, a, b, samples, reference))
    return result


def _window_stats(window: list[Sample], reference: float) -> dict[str, float]:
    sharp = np.mean([s.sharpness for s in window]) / reference
    bright = np.mean([s.brightness for s in window])
    motion = np.mean([s.motion for s in window[1:]]) if len(window) > 1 else 0.0
    faces = np.mean([1.0 if s.face else 0.0 for s in window])
    subject = float(np.median([s.subject_x for s in window]))
    return {
        "sharp": float(min(sharp, 1.5)),
        "bright": float(bright),
        "motion": float(motion),
        "faces": float(faces),
        "subject": subject,
    }


def score_window(stats: dict[str, float]) -> float:
    """Higher is better. Sharp, well exposed, some action but no shaking."""
    exposure = 1.0 - min(abs(stats["bright"] - 125.0) / 125.0, 1.0)
    motion = stats["motion"]
    if motion < 1.0:
        action = 0.6
    elif motion <= 8.0:
        action = 1.0
    else:
        action = max(0.0, 1.0 - (motion - 8.0) / 12.0)
    return round(0.45 * stats["sharp"] + 0.25 * exposure + 0.2 * action + 0.1 * stats["faces"], 4)


def _best_windows(
    clip_id: str, shot: int, a: float, b: float, samples: list[Sample], reference: float
) -> list[Segment]:
    start_min = a + (EDGE_MARGIN if b - a > 2 * SEGMENT_SECONDS else 0.0)
    end_max = b - (EDGE_MARGIN if b - a > 2 * SEGMENT_SECONDS else 0.0)
    length = min(SEGMENT_SECONDS, end_max - start_min)
    if length < 0.8:
        return []

    candidates: list[Segment] = []
    t = start_min
    while t + length <= end_max + 1e-6:
        window = [s for s in samples if t <= s.t < t + length]
        if window:
            stats = _window_stats(window, reference)
            candidates.append(
                Segment(
                    clip_id=clip_id,
                    start=round(t, 3),
                    end=round(t + length, 3),
                    score=score_window(stats),
                    sharpness=round(stats["sharp"], 3),
                    brightness=round(stats["bright"], 1),
                    motion=round(stats["motion"], 2),
                    face_ratio=round(stats["faces"], 2),
                    subject_x=round(stats["subject"], 3),
                    shot=shot,
                )
            )
        t += WINDOW_STEP

    # Greedy pick of non overlapping windows, best first.
    picked: list[Segment] = []
    limit = max(1, int((end_max - start_min) // (length + 0.6)))
    for seg in sorted(candidates, key=lambda s: s.score, reverse=True):
        if len(picked) >= limit:
            break
        if all(seg.end <= p.start or seg.start >= p.end for p in picked):
            picked.append(seg)
    return sorted(picked, key=lambda s: s.start)
