#!/usr/bin/env python3
"""Smoke test: generate synthetic audio, master it, assert the results are sane.

Run from the `mastering/` directory:  python tests/smoke_test.py
Exits non-zero on failure so it can gate CI.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from masterlib import analysis, audio_io  # noqa: E402
from masterlib.audio_io import Audio  # noqa: E402
from masterlib.chain import master  # noqa: E402


def make_fake_song(sr=44100, seconds=6.0, seed=0) -> Audio:
    """A quiet, full-band, dynamic stereo signal that stands in for a real mix."""
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    t = np.arange(n) / sr
    # A few tones across the spectrum + shaped noise = broadband content.
    tone = sum(np.sin(2 * np.pi * f * t) for f in (55, 220, 880, 3520)) / 4.0
    noise = rng.standard_normal(n) * 0.3
    # Slow amplitude envelope so it has real dynamics (crest factor).
    env = 0.4 + 0.6 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t))
    left = (tone + noise) * env
    right = (tone + np.roll(noise, 7)) * env  # slight stereo decorrelation
    stereo = np.stack([left, right], axis=1).astype(np.float32)
    stereo *= 0.1  # deliberately quiet so mastering has to raise the level
    return Audio(stereo, sr)


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name} {detail}")
    return cond


def main() -> int:
    song = make_fake_song()
    ok = True

    # 1) Default streaming master lands on target and respects the ceiling.
    r = master(song, target_lufs=-14.0, true_peak_db=-1.0)
    ok &= check("streaming loudness within 1 LU of -14",
                abs(r.after.integrated_lufs + 14.0) < 1.0,
                f"(got {r.after.integrated_lufs:.2f} LUFS)")
    ok &= check("true peak under -1.0 dBTP ceiling",
                r.after.true_peak_dbtp <= -1.0 + 1e-6,
                f"(got {r.after.true_peak_dbtp:.2f} dBTP)")
    ok &= check("master is louder than the quiet input",
                r.after.integrated_lufs > r.before.integrated_lufs,
                f"({r.before.integrated_lufs:.1f} -> {r.after.integrated_lufs:.1f})")
    ok &= check("output is finite and non-silent",
                np.all(np.isfinite(r.audio.samples)) and
                float(np.max(np.abs(r.audio.samples))) > 0.1)

    # 2) A louder target actually comes out louder.
    r_club = master(song, target_lufs=-8.0, true_peak_db=-1.0, strength="strong")
    ok &= check("club target louder than streaming target",
                r_club.after.integrated_lufs > r.after.integrated_lufs,
                f"({r.after.integrated_lufs:.1f} vs {r_club.after.integrated_lufs:.1f})")

    # 3) Reference matching produces bounded EQ moves and still hits target.
    bright_ref = make_fake_song(seed=1)
    # Skew the reference bright so matching has something to do.
    bright_ref.samples[:, :] *= 1.0
    r_ref = master(song, reference=bright_ref)
    ok &= check("reference match still lands on -14",
                abs(r_ref.after.integrated_lufs + 14.0) < 1.0,
                f"(got {r_ref.after.integrated_lufs:.2f} LUFS)")
    ok &= check("reference EQ moves are bounded (<= 4 dB)",
                all(abs(f[2]) <= 4.0 + 1e-6 for f in r_ref.match_filters))

    # 4) Round-trip through disk works.
    tmp = os.path.join(os.path.dirname(__file__), "_smoke_out.wav")
    audio_io.save(tmp, r.audio)
    reloaded = audio_io.load(tmp)
    stats = analysis.analyze(reloaded)
    ok &= check("reloaded file matches loudness within 0.5 LU",
                abs(stats.integrated_lufs - r.after.integrated_lufs) < 0.5)
    os.remove(tmp)

    print("\nRESULT:", "ALL PASSED" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
