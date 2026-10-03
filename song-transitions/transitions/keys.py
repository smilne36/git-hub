"""Musical key detection and Camelot-wheel compatibility (harmonic mixing)."""
from __future__ import annotations

import numpy as np

PITCHES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# Krumhansl-Kessler key profiles.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _camelot_number(major_pc: int) -> int:
    # C major = 8B, and each step clockwise is a fifth (7 semitones) up.
    return (8 + 7 * major_pc - 1) % 12 + 1


def camelot(pc: int, minor: bool) -> str:
    if minor:
        return f"{_camelot_number((pc + 3) % 12)}A"  # same number as its relative major
    return f"{_camelot_number(pc)}B"


def key_name(pc: int, minor: bool) -> str:
    return f"{PITCHES[pc]}{'m' if minor else ''}"


def estimate_key(chroma_mean: np.ndarray) -> tuple[str, str, float]:
    """Return (key name, Camelot code, confidence 0..1) from a 12-bin mean chroma."""
    c = np.asarray(chroma_mean, dtype=float)
    if not np.any(c > 0):
        return "?", "?", 0.0
    scores = []
    for minor, profile in ((False, _MAJOR), (True, _MINOR)):
        for pc in range(12):
            r = np.corrcoef(c, np.roll(profile, pc))[0, 1]
            scores.append((0.0 if np.isnan(r) else r, pc, minor))
    scores.sort(reverse=True)
    best_r, pc, minor = scores[0]
    # Percussive tracks (lots of techno) have flat chroma -> low correlation.
    confidence = float(np.clip((best_r - 0.3) / 0.5, 0.0, 1.0))
    return key_name(pc, minor), camelot(pc, minor), confidence


def _parse(code: str) -> tuple[int, str] | None:
    if not code or code == "?":
        return None
    return int(code[:-1]), code[-1]


def camelot_compat(a: str, b: str) -> tuple[float, str]:
    """Score how well key `a` flows into key `b` (1 = perfect)."""
    pa, pb = _parse(a), _parse(b)
    if pa is None or pb is None:
        return 0.6, "key unknown"
    (na, la), (nb, lb) = pa, pb
    up = (nb - na) % 12
    dist = min(up, 12 - up)
    if dist == 0 and la == lb:
        return 1.0, "same key"
    if dist == 0:
        return 0.85, "relative major/minor"
    if dist == 1 and la == lb:
        return 0.9, "adjacent on Camelot wheel"
    if dist == 1:
        return 0.6, "diagonal Camelot move"
    if dist == 2 and la == lb:
        return 0.55, "two steps (energy boost)"
    if up == 7 and la == lb:
        return 0.5, "semitone lift"
    return 0.15, "keys clash"
