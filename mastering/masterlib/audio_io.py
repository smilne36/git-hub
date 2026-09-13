"""Audio loading and saving.

Internal convention: audio is a float32 numpy array of shape (frames, channels).
`pedalboard` wants (channels, frames), so `to_pedalboard` / `from_pedalboard`
transpose at the boundary. Everything else in the package uses (frames, channels).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import soundfile as sf


@dataclass
class Audio:
    samples: np.ndarray  # float32, shape (frames, channels)
    sr: int

    @property
    def channels(self) -> int:
        return self.samples.shape[1]

    @property
    def frames(self) -> int:
        return self.samples.shape[0]

    @property
    def duration(self) -> float:
        return self.frames / self.sr


def load(path: str) -> Audio:
    """Load any libsndfile-supported file (WAV/FLAC/AIFF/OGG...) as float32."""
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    return Audio(samples=data, sr=int(sr))


def save(path: str, audio: Audio, subtype: str = "PCM_24") -> None:
    """Write to disk. Defaults to 24-bit PCM WAV, the sane mastering delivery format."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    sf.write(path, audio.samples, audio.sr, subtype=subtype)


def to_pedalboard(audio: Audio) -> np.ndarray:
    """(frames, channels) -> (channels, frames) contiguous float32 for pedalboard."""
    return np.ascontiguousarray(audio.samples.T)


def from_pedalboard(data: np.ndarray, sr: int) -> Audio:
    """(channels, frames) -> Audio with (frames, channels)."""
    if data.ndim == 1:
        data = data[np.newaxis, :]
    return Audio(samples=np.ascontiguousarray(data.T).astype(np.float32), sr=sr)


def try_write_mp3(path: str, audio: Audio, bitrate_kbps: int = 320) -> bool:
    """Best-effort MP3 export via pedalboard's AudioFile. Returns False if the
    build has no MP3 encoder rather than raising, so callers can fall back to WAV."""
    try:
        from pedalboard.io import AudioFile

        with AudioFile(
            path, "w", samplerate=audio.sr, num_channels=audio.channels,
            quality=bitrate_kbps,
        ) as f:
            f.write(to_pedalboard(audio))
        return True
    except Exception:
        return False
