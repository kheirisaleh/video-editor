"""Beat tracking for music tracks, so cuts can land on the beat.

A compact onset based tracker with NumPy: spectral flux onset envelope, tempo from
its autocorrelation, beat phase from the best matching grid, then every beat is
snapped to the nearest onset peak.
"""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SR = 22050
HOP = 512
WIN = 2048


@dataclass
class BeatInfo:
    tempo: float
    beats: list[float]
    duration: float
    intro_end: float = 0.0
    downbeats: list[float] = field(default_factory=list)


def decode(path: Path, max_seconds: float = 240.0) -> np.ndarray:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found")
    proc = subprocess.run(
        [ffmpeg, "-v", "error", "-t", str(max_seconds), "-i", str(path),
         "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True,
    )  # fmt: skip
    return np.frombuffer(proc.stdout, dtype=np.float32)


def onset_envelope(audio: np.ndarray) -> np.ndarray:
    if audio.size < WIN:
        return np.zeros(1, dtype=np.float32)
    frames = 1 + (audio.size - WIN) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(frames)[:, None]
    window = np.hanning(WIN).astype(np.float32)
    spec = np.abs(np.fft.rfft(audio[idx] * window, axis=1))
    log_spec = np.log1p(100.0 * spec)
    flux = np.maximum(np.diff(log_spec, axis=0), 0.0).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    # Remove the slow trend so loud passages do not dominate.
    kernel = np.ones(16) / 16
    flux = flux - np.convolve(flux, kernel, mode="same")
    flux = np.maximum(flux, 0.0)
    peak = flux.max()
    return (flux / peak).astype(np.float32) if peak > 0 else flux.astype(np.float32)


def estimate_tempo(env: np.ndarray, fps: float) -> float:
    """Tempo in BPM, preferring the 80 to 140 range common in soft background music."""
    n = env.size
    if n < 8:
        return 120.0
    padded = np.fft.rfft(env - env.mean(), n=2 * n)
    ac = np.fft.irfft(padded * np.conj(padded))[:n]
    best_lag, best_score = fps * 0.5, -np.inf
    for lag in range(max(int(fps * 60.0 / 180.0), 2), min(int(fps * 60.0 / 60.0) + 1, n - 1)):
        if not (ac[lag] >= ac[lag - 1] and ac[lag] >= ac[lag + 1]):
            continue  # only local maxima of the autocorrelation
        bpm = fps * 60.0 / lag
        # Log Gaussian preference around 110 BPM.
        weight = np.exp(-0.5 * (np.log2(bpm / 110.0) / 0.9) ** 2)
        if ac[lag] * weight > best_score:
            best_lag, best_score = float(lag), ac[lag] * weight
    lag = int(best_lag)
    if 1 <= lag < n - 1:
        # Parabolic interpolation for a sub frame period.
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        denom = a - 2 * b + c
        if denom != 0:
            best_lag = lag + 0.5 * (a - c) / denom
    return float(fps * 60.0 / best_lag)


def track(env: np.ndarray, fps: float, tempo: float) -> list[float]:
    """Follow the beats: start on the best grid phase, then step one period at a time
    and lock onto the onset peak near each expected beat, so small tempo errors and
    slight timing drift in the music do not accumulate."""
    period = fps * 60.0 / tempo
    n = env.size
    best_offset, best_score = 0.0, -1.0
    for offset in np.arange(0.0, period, 0.25):
        grid = np.arange(offset, n - 1, period)
        score = float(env[np.round(grid).astype(int)].sum())
        if score > best_score:
            best_offset, best_score = float(offset), score
    beats = []
    radius = max(int(round(period * 0.15)), 1)
    position = best_offset
    while position < n - 1:
        centre = int(round(position))
        lo, hi = max(centre - radius, 0), min(centre + radius + 1, n)
        local = lo + int(np.argmax(env[lo:hi]))
        # Only lock when the peak is clearly there; otherwise keep the steady grid.
        frame = float(local) if env[local] > 0.15 else position
        # Flux of frame f compares it with frame f-1 and peaks when the onset is
        # in the middle of the window, so the onset is half a window plus one hop later.
        beats.append(frame / fps + (WIN / 2 + HOP) / SR)
        position = frame + period
    return beats


def intro_end(audio: np.ndarray) -> float:
    """First moment the track reaches half of its typical loudness."""
    block = SR // 10
    if audio.size < block * 4:
        return 0.0
    rms = np.sqrt(np.mean(audio[: audio.size // block * block].reshape(-1, block) ** 2, axis=1))
    level = np.median(rms) * 0.5
    above = np.nonzero(rms >= level)[0]
    return float(above[0] * block / SR) if above.size else 0.0


def analyze_music(path: Path) -> BeatInfo:
    audio = decode(path)
    duration = audio.size / SR
    env = onset_envelope(audio)
    fps = SR / HOP
    tempo = estimate_tempo(env, fps)
    beats = [round(b, 3) for b in track(env, fps, tempo)]
    return BeatInfo(
        tempo=round(tempo, 1),
        beats=beats,
        duration=round(duration, 3),
        intro_end=round(intro_end(audio), 3),
        downbeats=beats[::4],
    )
