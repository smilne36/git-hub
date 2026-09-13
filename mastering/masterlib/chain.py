"""The mastering chain.

Signal flow (classic, top to bottom):

    DC removal
      -> subsonic high-pass (clear inaudible rumble)
      -> tone EQ            (preset colour and/or reference match)
      -> glue compressor    (slow, low ratio -- cohesion, not squashing)
      -> makeup gain        (push toward target loudness)
      -> brickwall limiter  (catch peaks, add density, guarantee ceiling)
      -> loudness targeting (iterate makeup gain to land on target LUFS)
      -> true-peak safety   (scale down if inter-sample peaks exceed ceiling)

Everything is plain, inspectable DSP. No hidden AI models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from pedalboard import (
    Compressor,
    Gain,
    HighpassFilter,
    HighShelfFilter,
    Limiter,
    LowShelfFilter,
    Pedalboard,
    PeakFilter,
)

from . import analysis
from .audio_io import Audio, from_pedalboard, to_pedalboard
from .analysis import LoudnessStats
from .presets import (
    DEFAULT_STRENGTH,
    DEFAULT_TARGET_LUFS,
    DEFAULT_TONE,
    DEFAULT_TRUE_PEAK_DB,
    HIGHPASS_HZ,
    STRENGTHS,
    TONES,
    Filter,
)
from .reference import build_match_filters

# Convergence settings for the loudness-targeting loop.
_MAX_ITERS = 8
_TOLERANCE_LU = 0.3
# Leave a little headroom below the ceiling for inter-sample overshoot.
_LIMITER_HEADROOM_DB = 0.3


@dataclass
class MasterResult:
    audio: Audio
    before: LoudnessStats
    after: LoudnessStats
    target_lufs: float
    true_peak_ceiling_db: float
    tone: str
    strength: str
    makeup_gain_db: float
    reference_matched: bool
    match_filters: List[Filter]


def _eq_plugin(kind: str, freq: float, gain: float, q: float):
    if kind == "low_shelf":
        return LowShelfFilter(cutoff_frequency_hz=freq, gain_db=gain, q=q)
    if kind == "high_shelf":
        return HighShelfFilter(cutoff_frequency_hz=freq, gain_db=gain, q=q)
    if kind == "peak":
        return PeakFilter(cutoff_frequency_hz=freq, gain_db=gain, q=q)
    raise ValueError(f"unknown filter kind: {kind!r}")


def _remove_dc(audio: Audio) -> Audio:
    out = audio.samples - audio.samples.mean(axis=0, keepdims=True)
    return Audio(out.astype(np.float32), audio.sr)


def _tone_stage(filters: List[Filter], strength_name: str) -> Pedalboard:
    s = STRENGTHS[strength_name]
    plugins = [HighpassFilter(cutoff_frequency_hz=HIGHPASS_HZ)]
    plugins += [_eq_plugin(*f) for f in filters]
    plugins.append(
        Compressor(
            threshold_db=s.comp_threshold_db,
            ratio=s.comp_ratio,
            attack_ms=s.comp_attack_ms,
            release_ms=s.comp_release_ms,
        )
    )
    return Pedalboard(plugins)


def _target_loudness(
    tone_audio: Audio, target_lufs: float, ceiling_db: float, limiter_release_ms: float
):
    """Iterate makeup gain into a limiter until integrated loudness hits target.

    Returns (audio, makeup_gain_db). The limiter both prevents clipping and adds
    density, so loudness rises sub-linearly with gain near heavy limiting; a few
    Newton-ish steps converge quickly for real material.
    """
    base = analysis.integrated_loudness(tone_audio)
    if not np.isfinite(base):  # silence -> nothing to do
        return tone_audio, 0.0

    limiter_thresh = ceiling_db - _LIMITER_HEADROOM_DB
    src = to_pedalboard(tone_audio)
    makeup = target_lufs - base  # first guess: pure level difference
    best = None  # (abs_error, audio, makeup)

    for _ in range(_MAX_ITERS):
        board = Pedalboard(
            [Gain(gain_db=makeup),
             Limiter(threshold_db=limiter_thresh, release_ms=limiter_release_ms)]
        )
        out = from_pedalboard(board(src, tone_audio.sr), tone_audio.sr)
        measured = analysis.integrated_loudness(out)
        if not np.isfinite(measured):
            return tone_audio, 0.0
        err = target_lufs - measured
        if best is None or abs(err) < best[0]:
            best = (abs(err), out, makeup)
        if abs(err) <= _TOLERANCE_LU:
            break
        makeup += err  # nudge by the residual loudness error

    _, out_audio, makeup_used = best

    # Guarantee the true-peak ceiling even after inter-sample reconstruction.
    tp = analysis.true_peak_dbtp(out_audio)
    if tp > ceiling_db:
        scale = 10.0 ** ((ceiling_db - tp) / 20.0)
        out_audio = Audio((out_audio.samples * scale).astype(np.float32), out_audio.sr)
    return out_audio, makeup_used


def master(
    audio: Audio,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    true_peak_db: float = DEFAULT_TRUE_PEAK_DB,
    tone: str = DEFAULT_TONE,
    strength: str = DEFAULT_STRENGTH,
    reference: Optional[Audio] = None,
    match_strength: float = 0.6,
) -> MasterResult:
    """Master a stereo bounce and return the audio plus a before/after report."""
    if tone not in TONES:
        raise ValueError(f"unknown tone {tone!r}; choose from {sorted(TONES)}")
    if strength not in STRENGTHS:
        raise ValueError(f"unknown strength {strength!r}; choose from {sorted(STRENGTHS)}")

    before = analysis.analyze(audio)

    filters = list(TONES[tone].filters)
    match_filters: List[Filter] = []
    if reference is not None:
        match_filters = build_match_filters(audio, reference, strength=match_strength)
        filters += match_filters

    work = _remove_dc(audio)
    tone_board = _tone_stage(filters, strength)
    toned = from_pedalboard(tone_board(to_pedalboard(work), work.sr), work.sr)

    mastered, makeup = _target_loudness(
        toned, target_lufs, true_peak_db, STRENGTHS[strength].limiter_release_ms
    )
    after = analysis.analyze(mastered)

    return MasterResult(
        audio=mastered,
        before=before,
        after=after,
        target_lufs=target_lufs,
        true_peak_ceiling_db=true_peak_db,
        tone=tone,
        strength=strength,
        makeup_gain_db=makeup,
        reference_matched=reference is not None,
        match_filters=match_filters,
    )
