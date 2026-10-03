"""Generate simple synthetic dance tracks (kick, hats, bassline, chord pad) for tests."""
from __future__ import annotations

import numpy as np
import soundfile as sf

SR = 22050
NOTE = {"C": 0, "C#": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def make_track(path, bpm: float, root: str, minor: bool = True, seconds: float = 90.0,
               fade_out: float = 0.0, ambient_intro: float = 0.0) -> None:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    beat = 60.0 / bpm
    third = 3 if minor else 4
    r = 48 + NOTE[root]
    chord = [r + 12, r + 12 + third, r + 19]
    # Pad (harmonic content for key detection), whole track.
    for m in chord:
        y += 0.08 * np.sin(2 * np.pi * _hz(m) * t)
    k = 0
    while k * beat < seconds:
        s = int(k * beat * SR)
        if k * beat >= ambient_intro:
            # Kick: pitch-swept sine, louder on the bar's first beat.
            d = np.arange(int(0.25 * SR)) / SR
            kick = np.sin(2 * np.pi * (50 + 120 * np.exp(-d * 30)) * d) * np.exp(-d * 12)
            kick *= 1.0 if k % 4 == 0 else 0.8
            e = min(n, s + len(kick))
            y[s:e] += kick[:e - s]
            # Off-beat bass note + hat.
            o = int((k + 0.5) * beat * SR)
            d2 = np.arange(int(0.2 * SR)) / SR
            bass = 0.35 * np.sin(2 * np.pi * _hz(r - 12) * d2) * np.exp(-d2 * 8)
            hat = 0.05 * np.random.default_rng(k).standard_normal(len(d2) // 4) * np.exp(-np.arange(len(d2) // 4) / 200)
            e = min(n, o + len(bass))
            if o < n:
                y[o:e] += bass[:e - o]
                eh = min(n, o + len(hat))
                y[o:eh] += hat[:eh - o]
        k += 1
    if fade_out:
        f = int(fade_out * SR)
        y[-f:] *= np.linspace(1, 0, f) ** 2
    y /= np.max(np.abs(y)) * 1.1
    sf.write(path, y, SR)
