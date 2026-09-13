"""Reference matching (optional).

Given a commercial track you like, nudge your master's tonal balance toward it.
This is intentionally gentle: it builds a handful of peaking EQ moves capped at a
few dB, so it steers the tone without rebuilding your mix. It matches *balance*,
not level (loudness is handled separately by the limiter/normalisation stage).
"""

from __future__ import annotations

from typing import List

import numpy as np

from .analysis import BAND_CENTERS, band_levels_db
from .audio_io import Audio
from .presets import Filter

MAX_CORRECTION_DB = 4.0  # never push any band more than this
MATCH_Q = 1.0


def build_match_filters(
    source: Audio, reference: Audio, strength: float = 0.6
) -> List[Filter]:
    """Return peaking EQ moves that steer `source` toward `reference`'s balance.

    `strength` in [0, 1] scales how far we go (0.6 = "obvious but musical").
    """
    src = band_levels_db(source)
    ref = band_levels_db(reference)
    diff = ref - src
    # Ignore non-finite (silent) bands.
    diff = np.where(np.isfinite(diff), diff, 0.0)
    # Smooth across neighbouring bands so we don't chase narrow peaks.
    smoothed = _smooth(diff)
    corrections = np.clip(smoothed * strength, -MAX_CORRECTION_DB, MAX_CORRECTION_DB)

    filters: List[Filter] = []
    for center, gain in zip(BAND_CENTERS, corrections):
        if abs(gain) < 0.25:  # skip negligible moves
            continue
        filters.append(("peak", float(center), float(gain), MATCH_Q))
    return filters


def _smooth(x: np.ndarray) -> np.ndarray:
    kernel = np.array([0.25, 0.5, 0.25])
    padded = np.pad(x, 1, mode="edge")
    return np.convolve(padded, kernel, mode="valid")
