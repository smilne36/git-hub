"""Score how well one track flows into another and plan the transition."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .analyze import TrackAnalysis
from .keys import camelot_compat

MAX_BEATMATCH = 0.06  # beyond +-6% stretch a blend sounds wrong; switch to echo-out

WEIGHTS = {"tempo": 0.30, "key": 0.25, "energy": 0.15, "timbre": 0.15, "mixability": 0.15}


@dataclass
class Plan:
    style: str          # "blend" | "echo_out" | "fade"
    out_start: float    # time in the outgoing track where the transition begins
    in_start: float     # time in the incoming track that lands at out_start
    overlap: float      # seconds both tracks play together (or echo tail length)
    bars: int
    rate: float         # playback rate applied to the incoming track (1 = untouched)
    multiplier: float   # tempo relation used (1, 2 = half-time incoming, 0.5 = double-time)


@dataclass
class Match:
    outgoing: TrackAnalysis
    incoming: TrackAnalysis
    score: float
    parts: dict[str, float]
    reasons: list[str]
    plan: Plan
    preview: str | None = field(default=None)


def tempo_relation(bpm_out: float, bpm_in: float) -> tuple[float, float, float]:
    """Return (relative mismatch, multiplier, stretch rate for the incoming track).

    Half/double time counts as a match: a 70 BPM dancehall riddim sits on a 140 BPM grid.
    """
    best = min((abs(bpm_out / (bpm_in * m) - 1), m) for m in (1.0, 2.0, 0.5))
    pct, m = best
    return pct, m, bpm_out / (bpm_in * m)


def _energy_vec(t: TrackAnalysis, seg) -> np.ndarray:
    return np.array([
        (seg.rms_db - t.loudness_db) / 6.0,
        seg.onset_rate / 4.0,
        seg.low_ratio * 4.0,
        seg.centroid / 2000.0,
    ])


def _timbre(a, b) -> float:
    va, vb = np.array(a.mfcc[1:]), np.array(b.mfcc[1:])  # skip c0 (overall level)
    cos = float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-9))
    return float(np.clip((cos - 0.5) / 0.5, 0.0, 1.0))


def _pick_downbeat(beats: list[float], target: float, lo: float, hi: float) -> float:
    cands = [b for b in beats if lo <= b <= hi]
    if not cands:
        return float(np.clip(target, lo, hi))
    return min(cands, key=lambda b: abs(b - target))


def plan_transition(a: TrackAnalysis, b: TrackAnalysis, bars: int | None = None) -> Plan:
    pct, m, rate = tempo_relation(a.bpm, b.bpm)
    in_start = next((d for d in b.downbeats if d >= b.start), b.start)

    if pct <= MAX_BEATMATCH:
        style = "blend"
        n = bars or (16 if a.outro_type == "beat" and b.intro_type == "beat" else 8)
        overlap = n * a.bar_len
        # Finish the blend about where the outgoing track's groove drops away.
        lo = a.start + min(overlap, (a.end - a.start) / 2)
        hi = max(lo, a.end - overlap)
        out_start = _pick_downbeat(a.downbeats, a.groove_end - overlap, lo, hi)
        overlap = min(overlap, a.end - out_start)
        return Plan(style, out_start, in_start, overlap, n, rate, m)

    if a.outro_type == "fade" and a.end - a.groove_end >= 4:
        overlap = float(min(10.0, a.end - a.groove_end))
        return Plan("fade", a.groove_end, b.start, overlap, 0, 1.0, 1.0)

    # Tempos too far apart to beatmatch (e.g. dancehall -> house): echo out on the bar
    # and drop the next tune, the way a selector would.
    cut = _pick_downbeat(a.downbeats, a.groove_end, a.start + (a.end - a.start) / 2, a.end)
    return Plan("echo_out", cut, in_start, 2 * a.bar_len, 2, 1.0, 1.0)


def score_pair(a: TrackAnalysis, b: TrackAnalysis, bars: int | None = None) -> Match:
    """`a` plays first and mixes into `b`."""
    reasons = []
    pct, m, rate = tempo_relation(a.bpm, b.bpm)
    tempo = float(np.exp(-(pct / 0.04) ** 2))
    rel = {1.0: "", 2.0: " (half-time)", 0.5: " (double-time)"}[m]
    if pct <= MAX_BEATMATCH:
        reasons.append(f"BPM {a.bpm:.1f} -> {b.bpm:.1f}{rel}, next track "
                       + ("untouched" if abs(rate - 1) < 5e-4 else
                          f"{'sped up' if rate > 1 else 'slowed'} {100 * abs(rate - 1):.1f}% to beatmatch"))
    else:
        reasons.append(f"BPM {a.bpm:.1f} -> {b.bpm:.1f}: {100 * pct:.0f}% apart, too far to beatmatch")

    k, why = camelot_compat(a.outro.camelot, b.intro.camelot)
    conf = min(a.outro.key_confidence, b.intro.key_confidence)
    key = conf * k + (1 - conf) * 0.6
    reasons.append(f"Key {a.outro.key} ({a.outro.camelot}) -> {b.intro.key} ({b.intro.camelot}): {why}"
                   + ("" if conf > 0.4 else ", low confidence"))

    diff = float(np.linalg.norm(_energy_vec(a, a.outro) - _energy_vec(b, b.intro)))
    energy = float(np.exp(-diff))
    reasons.append(f"Energy {'close' if energy > 0.6 else 'shift'} (outro {a.outro_type}, intro {b.intro_type})")

    timbre = _timbre(a.outro, b.intro)

    plan = plan_transition(a, b, bars)
    mixability = {"blend": 1.0, "fade": 0.7, "echo_out": 0.5}[plan.style]
    if plan.style == "blend" and "ambient" in (a.outro_type, b.intro_type):
        mixability = 0.85
    reasons.append(f"Transition: {plan.style.replace('_', ' ')}"
                   + (f" over {plan.bars} bars" if plan.style == "blend" else ""))

    parts = {"tempo": tempo, "key": key, "energy": energy, "timbre": timbre, "mixability": mixability}
    score = sum(WEIGHTS[n] * v for n, v in parts.items())
    return Match(a, b, round(100 * score, 1), {n: round(v, 3) for n, v in parts.items()}, reasons, plan)


def rank(song: TrackAnalysis, library: list[TrackAnalysis], bars: int | None = None):
    """Return (best songs to play before `song`, best songs to play after it)."""
    others = [t for t in library if t.path != song.path]
    before = sorted((score_pair(t, song, bars) for t in others), key=lambda x: -x.score)
    after = sorted((score_pair(song, t, bars) for t in others), key=lambda x: -x.score)
    return before, after
