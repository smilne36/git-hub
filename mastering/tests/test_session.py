#!/usr/bin/env python3
"""Headless tests for MasterSession -- the GUI's logic without any GUI.

Run from the `mastering/` directory:  python tests/test_session.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from masterlib import audio_io  # noqa: E402
from masterlib.session import STRENGTH_KEYS, TONE_KEYS, MasterSession  # noqa: E402
from tests.smoke_test import make_fake_song  # noqa: E402


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")
    return cond


def main() -> int:
    ok = True
    tmpdir = os.path.dirname(os.path.abspath(__file__))
    in_path = os.path.join(tmpdir, "_session_in.wav")
    out_path = os.path.join(tmpdir, "_session_out.wav")
    audio_io.save(in_path, make_fake_song(seconds=6))

    s = MasterSession()
    ok &= check("starts with no audio", not s.has_audio)

    s.load(in_path)
    ok &= check("load populates audio + stats + advice",
                s.has_audio and s.input_stats is not None and s.advice is not None)
    ok &= check("no error on good file", s.error is None)
    ok &= check("recommended tone is valid",
                s.advice.recommended_tone in TONE_KEYS)
    ok &= check("recommended strength is valid",
                s.advice.recommended_strength in STRENGTH_KEYS)

    s.apply_recommendations()
    ok &= check("apply_recommendations sets tone/strength",
                s.tone == s.advice.recommended_tone
                and s.strength == s.advice.recommended_strength)

    # Changing the target refreshes advice without crashing.
    s.target_lufs = -8.0
    s.reanalyze_advice()
    ok &= check("reanalyze after target change keeps advice", s.advice is not None)
    s.target_lufs = -14.0

    # Synchronous master (used by tests) writes a file and hits the target.
    result = s.run_master_sync(out_path)
    ok &= check("sync master produces a result", result is not None)
    ok &= check("output file written", os.path.isfile(out_path))
    ok &= check("lands within 1 LU of -14",
                abs(result.after.integrated_lufs + 14.0) < 1.0,
                f"(got {result.after.integrated_lufs:.2f})")
    ok &= check("not busy after finishing", not s.busy)

    # Background master path: start, then wait for the worker to finish.
    s2 = MasterSession()
    s2.load(in_path)
    s2.start_master(out_path)
    ok &= check("busy immediately after start", s2.busy)
    for _ in range(200):  # up to ~20s
        if not s2.busy:
            break
        time.sleep(0.1)
    ok &= check("background master finishes", not s2.busy)
    ok &= check("background master has result", s2.result is not None)

    # Bad file sets an error rather than raising.
    s3 = MasterSession()
    s3.load(os.path.join(tmpdir, "does_not_exist.wav"))
    ok &= check("missing file yields an error, no crash", s3.error is not None)

    for p in (in_path, out_path):
        if os.path.isfile(p):
            os.remove(p)

    print("\nRESULT:", "ALL PASSED" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
