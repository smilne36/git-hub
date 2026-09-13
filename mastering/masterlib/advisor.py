"""Mastering assistant.

Looks at a bounce and explains, in plain English, what it needs before mastering
-- and recommends tone/strength settings. This is the "help me, I find this hard
in Ableton" part: it turns raw numbers (LUFS, crest factor, spectral balance)
into advice a musician can act on, and picks sensible settings automatically.

The recommendations are heuristics, not gospel. They aim to be safe and
explain their reasoning so you learn what to listen for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from . import analysis
from .audio_io import Audio

# Severity tags -> a leading glyph for the CLI printout.
GLYPHS = {"ok": "OK ", "tip": "-> ", "warn": "!! "}


@dataclass
class Advice:
    findings: List[Tuple[str, str]] = field(default_factory=list)  # (severity, text)
    recommended_tone: str = "transparent"
    recommended_strength: str = "medium"
    summary: str = ""

    def add(self, severity: str, text: str) -> None:
        self.findings.append((severity, text))


def advise(audio: Audio, target_lufs: float = -14.0) -> Advice:
    a = Advice()
    stats = analysis.analyze(audio)
    bands = analysis.band_levels_db(audio)  # balance, mean = 0 dB

    # --- Headroom in the bounce -------------------------------------------
    peak = stats.sample_peak_dbfs
    if peak > -0.3:
        a.add("warn", f"Your bounce peaks at {peak:+.1f} dBFS -- it's basically "
                      "slammed to the ceiling and may already be clipping. "
                      "Re-export from Ableton with peaks around -6 dBFS so the "
                      "master has room to work.")
    elif peak > -1.5:
        a.add("tip", f"Bounce peaks at {peak:+.1f} dBFS -- a little hot. "
                     "Around -6 dBFS gives the cleanest master, but this is workable.")
    else:
        a.add("ok", f"Good headroom in the bounce (peaks at {peak:+.1f} dBFS).")

    # --- Dynamics (crest factor) -> compression strength ------------------
    crest = stats.crest_db
    if crest >= 14:
        a.recommended_strength = "strong"
        a.add("tip", f"Very dynamic mix (crest {crest:.1f} dB). To get "
                     "competitively loud it needs firm limiting -- expect the "
                     "peaks to come down noticeably. Using 'strong'.")
    elif crest >= 9:
        a.recommended_strength = "medium"
        a.add("ok", f"Healthy dynamics (crest {crest:.1f} dB). 'medium' processing "
                    "should glue it without squashing.")
    else:
        a.recommended_strength = "light"
        a.add("warn", f"Low dynamics (crest {crest:.1f} dB) -- this mix is already "
                      "heavily compressed/limited. Mastering can't add much and "
                      "may distort, so using 'light'. Consider a more open mix.")

    # --- Loudness gap to target -------------------------------------------
    gap = target_lufs - stats.integrated_lufs
    if stats.integrated_lufs > target_lufs + 0.5:
        a.add("tip", f"Already louder ({stats.integrated_lufs:.1f} LUFS) than the "
                     f"{target_lufs:.0f} LUFS target -- streaming will turn it "
                     "*down*. It'll be normalised to target and dynamics preserved.")
    elif gap > 12:
        a.add("tip", f"Quiet mix ({stats.integrated_lufs:.1f} LUFS); needs about "
                     f"{gap:.0f} dB to reach {target_lufs:.0f} LUFS. That's a lot "
                     "of limiting -- fine, but the louder sections will compress most.")
    else:
        a.add("ok", f"Loudness ({stats.integrated_lufs:.1f} LUFS) is a comfortable "
                    f"{gap:.0f} dB under target; mastering will lift it cleanly.")

    # --- Tonal balance -> tone preset -------------------------------------
    low = float(np.mean(bands[0:3]))      # 40-160 Hz  (sub/bass)
    low_mid = float(np.mean(bands[3:5]))  # 315-630 Hz (mud / body)
    high = float(np.mean(bands[7:]))      # 5k-16k Hz  (presence / air)

    if low_mid > 3.0:
        a.recommended_tone = "open"
        a.add("tip", f"Low-mids are built up (+{low_mid:.0f} dB around 300-600 Hz) "
                     "-- sounds muddy/boxy. 'open' scoops that and adds air.")
    elif high < -3.0:
        a.recommended_tone = "bright"
        a.add("tip", f"Top end is dull ({high:.0f} dB above 5 kHz). "
                     "'bright' adds presence and air.")
    elif high > 3.0:
        a.recommended_tone = "warm"
        a.add("tip", f"Top end is hot (+{high:.0f} dB above 5 kHz) -- may sound "
                     "harsh/fatiguing. 'warm' softens it.")
    else:
        a.recommended_tone = "transparent"
        a.add("ok", "Tonal balance looks even; no colouring needed ('transparent').")

    if low > 4.0:
        a.add("warn", f"Bass is heavy (+{low:.0f} dB in the low end). Mastering "
                      "won't fix a boomy mix -- tame the kick/bass balance in "
                      "Ableton for the best result.")

    # --- Mono / stereo ----------------------------------------------------
    if stats.channels == 1:
        a.add("tip", "File is mono. That's fine, but you lose stereo width; "
                     "bounce in stereo if your mix has panning/width.")

    a.summary = (f"Recommended: --tone {a.recommended_tone} "
                 f"--strength {a.recommended_strength}")
    return a
