"""Measurement: loudness (LUFS), true peak (dBTP), sample peak, crest factor,
and a coarse log-band spectrum used for reference matching and reporting.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyloudnorm as pyln
from scipy.signal import resample_poly

from .audio_io import Audio

# Band centres (Hz) used for spectrum reporting and reference matching.
BAND_CENTERS = np.array(
    [40, 80, 160, 315, 630, 1250, 2500, 5000, 10000, 16000], dtype=float
)


@dataclass
class LoudnessStats:
    integrated_lufs: float  # ITU-R BS.1770 integrated loudness
    sample_peak_dbfs: float  # peak sample value in dBFS
    true_peak_dbtp: float  # inter-sample (oversampled) peak in dBTP
    crest_db: float  # peak-to-RMS ratio; a rough "dynamics" indicator
    duration_s: float
    sample_rate: int
    channels: int


def _db(x: float) -> float:
    return -np.inf if x <= 0 else 20.0 * np.log10(x)


def integrated_loudness(audio: Audio) -> float:
    """Integrated loudness in LUFS. Requires ~>=0.4s of audio."""
    meter = pyln.Meter(audio.sr)
    data = audio.samples if audio.channels > 1 else audio.samples[:, 0]
    return float(meter.integrated_loudness(data))


def sample_peak_dbfs(audio: Audio) -> float:
    return _db(float(np.max(np.abs(audio.samples))) if audio.frames else 0.0)


def true_peak_dbtp(audio: Audio, oversample: int = 4) -> float:
    """Estimate inter-sample true peak by 4x oversampling each channel.

    This is what streaming platforms police; a signal can sit at 0 dBFS on the
    samples yet reconstruct above 0 between them, causing D/A clipping.
    """
    peak = 0.0
    for ch in range(audio.channels):
        up = resample_poly(audio.samples[:, ch], oversample, 1)
        peak = max(peak, float(np.max(np.abs(up))) if up.size else 0.0)
    return _db(peak)


def crest_factor_db(audio: Audio) -> float:
    if not audio.frames:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(audio.samples))))
    peak = float(np.max(np.abs(audio.samples)))
    if rms <= 0 or peak <= 0:
        return 0.0
    return _db(peak) - _db(rms)


def band_levels_db(audio: Audio, centers: np.ndarray = BAND_CENTERS) -> np.ndarray:
    """Average magnitude (dB) of a mono sum in log-spaced bands around `centers`.
    Normalised so the mean band is 0 dB, so it describes tonal *balance*, not level."""
    mono = audio.samples.mean(axis=1)
    n = int(2 ** np.ceil(np.log2(len(mono)))) if len(mono) else 1024
    spec = np.abs(np.fft.rfft(mono, n=n))
    freqs = np.fft.rfftfreq(n, d=1.0 / audio.sr)
    # Band edges are geometric midpoints between adjacent centres.
    edges = np.sqrt(centers[:-1] * centers[1:])
    edges = np.concatenate(([centers[0] / 1.5], edges, [centers[-1] * 1.5]))
    levels = np.zeros(len(centers))
    for i in range(len(centers)):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        band = spec[mask]
        levels[i] = _db(float(np.sqrt(np.mean(band ** 2)))) if band.size else -np.inf
    finite = levels[np.isfinite(levels)]
    if finite.size:
        levels = levels - float(np.mean(finite))
    return levels


def analyze(audio: Audio) -> LoudnessStats:
    return LoudnessStats(
        integrated_lufs=integrated_loudness(audio),
        sample_peak_dbfs=sample_peak_dbfs(audio),
        true_peak_dbtp=true_peak_dbtp(audio),
        crest_db=crest_factor_db(audio),
        duration_s=audio.duration,
        sample_rate=audio.sr,
        channels=audio.channels,
    )
