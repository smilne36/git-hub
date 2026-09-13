"""Presets: loudness targets, tone curves, and processing strengths.

These are deliberately conservative. Auto-mastering that hits your mix with a
sledgehammer sounds worse than doing nothing; the defaults aim for "cleaner and
competitively loud" rather than "obviously processed".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# --- Loudness targets (integrated LUFS) --------------------------------------
# Most streaming services normalise playback toward roughly -14 LUFS, so a
# louder master just gets turned down (and loses dynamics for nothing).
TARGETS = {
    "streaming": -14.0,   # Spotify / YouTube / SoundCloud normalised playback
    "spotify": -14.0,
    "youtube": -14.0,
    "soundcloud": -14.0,
    "apple": -16.0,       # Apple Music "Sound Check" reference
    "cd": -9.0,           # traditional loud CD master
    "club": -8.0,         # hot master for DJ / club playback
}
DEFAULT_TARGET_LUFS = -14.0
DEFAULT_TRUE_PEAK_DB = -1.0  # dBTP ceiling; -1.0 is the safe streaming convention


# --- Tone shaping ------------------------------------------------------------
# Each entry: (filter_kind, frequency_hz, gain_db, q)
#   filter_kind in {"low_shelf", "high_shelf", "peak"}
Filter = Tuple[str, float, float, float]


@dataclass
class Tone:
    name: str
    description: str
    filters: List[Filter] = field(default_factory=list)


TONES = {
    "transparent": Tone(
        "transparent", "No tonal colouring; just level, glue and loudness.", []
    ),
    "warm": Tone(
        "warm",
        "Rounder low end, slightly softer highs.",
        [("low_shelf", 120.0, 1.5, 0.7), ("high_shelf", 9000.0, -1.0, 0.7)],
    ),
    "bright": Tone(
        "bright",
        "Adds presence and 'air' up top.",
        [("high_shelf", 8000.0, 2.0, 0.7), ("peak", 3000.0, 1.0, 1.0)],
    ),
    "open": Tone(
        "open",
        "Tightens low-mid mud and lifts the very top for a modern, airy master.",
        [
            ("peak", 300.0, -1.5, 1.0),
            ("high_shelf", 12000.0, 1.5, 0.7),
            ("low_shelf", 60.0, 1.0, 0.7),
        ],
    ),
}
DEFAULT_TONE = "transparent"


# --- Processing strength -----------------------------------------------------
@dataclass
class Strength:
    name: str
    comp_threshold_db: float
    comp_ratio: float
    comp_attack_ms: float
    comp_release_ms: float
    limiter_release_ms: float


STRENGTHS = {
    "light": Strength("light", -14.0, 1.5, 30.0, 250.0, 150.0),
    "medium": Strength("medium", -18.0, 2.0, 20.0, 200.0, 120.0),
    "strong": Strength("strong", -22.0, 2.5, 10.0, 150.0, 90.0),
}
DEFAULT_STRENGTH = "medium"

# Subsonic high-pass: clears inaudible rumble that eats limiter headroom.
HIGHPASS_HZ = 30.0
