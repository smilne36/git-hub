"""Render an audible preview of a planned transition."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from .match import Match

SR = 44100
BASS_HZ = 200


def _load(path: str, offset: float, duration: float) -> np.ndarray:
    y, _ = librosa.load(path, sr=SR, mono=False, offset=max(0.0, offset), duration=max(0.01, duration))
    if y.ndim == 1:
        y = np.stack([y, y])
    return y


def _fit(y: np.ndarray, n: int) -> np.ndarray:
    if y.shape[1] >= n:
        return y[:, :n]
    return np.pad(y, ((0, 0), (0, n - y.shape[1])))


def _split(y: np.ndarray, hz: float = BASS_HZ) -> tuple[np.ndarray, np.ndarray]:
    sos = butter(4, hz, btype="low", fs=SR, output="sos")
    low = sosfiltfilt(sos, y, axis=-1)
    return low, y - low


def _highpass(y: np.ndarray, hz: float) -> np.ndarray:
    return sosfiltfilt(butter(2, hz, btype="high", fs=SR, output="sos"), y, axis=-1)


def _rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(y ** 2)) + 1e-9)


def _match_level(y: np.ndarray, ref: np.ndarray, probe: np.ndarray, max_db: float = 6.0) -> np.ndarray:
    """Scale `y` so its `probe` section is as loud as `ref` (no volume jump on the next tune)."""
    if ref.size == 0 or probe.size == 0:
        return y
    gain_db = np.clip(20 * np.log10(_rms(ref) / _rms(probe)), -max_db, max_db)
    return y * 10 ** (gain_db / 20)


def _change_speed(y: np.ndarray, rate: float, keylock: str) -> np.ndarray:
    if abs(rate - 1) < 1e-3:
        return y
    if keylock == "always" or (keylock == "auto" and abs(rate - 1) > 0.03):
        return librosa.effects.time_stretch(y, rate=rate)
    # Vinyl-style: resample (pitch moves with tempo); cleaner transients for small nudges.
    return librosa.resample(y, orig_sr=SR, target_sr=int(round(SR / rate)))


def _blend(m: Match, lead: float, tail: float, keylock: str) -> np.ndarray:
    a, b, p = m.outgoing, m.incoming, m.plan
    lead = min(lead, p.out_start)
    n_lead, n_ov, n_tail = int(lead * SR), int(p.overlap * SR), int(tail * SR)
    ya = _fit(_load(a.path, p.out_start - lead, lead + p.overlap), n_lead + n_ov)
    yb = _load(b.path, p.in_start, (p.overlap + tail) * p.rate)
    yb = _fit(_change_speed(yb, p.rate, keylock), n_ov + n_tail)
    yb = _match_level(yb, ya[:, :n_lead] if n_lead else ya, yb[:, n_ov:] if n_tail else yb)

    a_low, a_high = _split(ya[:, n_lead:])
    b_low, b_high = _split(yb[:, :n_ov])
    t = np.linspace(0, 1, n_ov, endpoint=False)
    # Highs: bring the new tune in over the first half, take the old one out over the second.
    g_b_high = np.sin(np.pi / 2 * np.minimum(1, 2 * t))
    g_a_high = np.sin(np.pi / 2 * np.minimum(1, 2 * (1 - t)))
    # Bass swap at the halfway point, ramped over one beat so it doesn't click.
    ramp = max(1e-3, a.beat_len / max(p.overlap, 1e-3))
    s = np.clip((t - 0.5) / ramp + 0.5, 0, 1)
    mix = a_low * (1 - s) + a_high * g_a_high + b_low * s + b_high * g_b_high
    return np.concatenate([ya[:, :n_lead], mix, yb[:, n_ov:]], axis=1)


def _echo_out(m: Match, lead: float, tail: float) -> np.ndarray:
    a, b, p = m.outgoing, m.incoming, m.plan
    lead = min(lead, p.out_start)
    ya = _load(a.path, p.out_start - lead, lead)
    grab = ya[:, -int(2 * a.beat_len * SR):].copy()  # last half bar before the cut
    fade = min(int(0.01 * SR), grab.shape[1] // 2)
    if fade:
        env = np.ones(grab.shape[1])
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        grab *= env
    grab = _highpass(grab, 300)
    delay, feedback, repeats = int(0.75 * a.beat_len * SR), 0.55, 8
    echo = np.zeros((2, delay * repeats + grab.shape[1]))
    for k in range(repeats):
        echo[:, k * delay:k * delay + grab.shape[1]] += grab * feedback ** (k + 1)

    yb = _fit(_load(b.path, p.in_start, tail), int(tail * SR))
    yb = _match_level(yb, ya, yb)
    ramp = min(int(0.01 * SR), yb.shape[1])
    yb[:, :ramp] *= np.linspace(0, 1, ramp)
    after = yb.copy()
    n = min(after.shape[1], echo.shape[1])
    after[:, :n] += 0.7 * echo[:, :n]
    return np.concatenate([ya, after], axis=1)


def _fade(m: Match, lead: float, tail: float) -> np.ndarray:
    a, b, p = m.outgoing, m.incoming, m.plan
    lead = min(lead, p.out_start)
    n_lead, n_ov, n_tail = int(lead * SR), int(p.overlap * SR), int(tail * SR)
    ya = _fit(_load(a.path, p.out_start - lead, lead + p.overlap), n_lead + n_ov)
    yb = _fit(_load(b.path, p.in_start, p.overlap + tail), n_ov + n_tail)
    yb = _match_level(yb, ya[:, :n_lead] if n_lead else ya, yb[:, n_ov:] if n_tail else yb)
    t = np.linspace(0, 1, n_ov, endpoint=False)
    mix = ya[:, n_lead:] * np.cos(np.pi / 2 * t) + yb[:, :n_ov] * np.sin(np.pi / 2 * t)
    return np.concatenate([ya[:, :n_lead], mix, yb[:, n_ov:]], axis=1)


def render(m: Match, dest: Path, lead: float = 20.0, tail: float = 20.0, keylock: str = "auto") -> Path:
    """Write the transition (lead-in of the outgoing track -> mix -> incoming) to `dest`.

    `dest` should have no extension; .mp3 is written when ffmpeg exists, .wav otherwise.
    """
    style = m.plan.style
    if style == "blend":
        y = _blend(m, lead, tail, keylock)
    elif style == "fade":
        y = _fade(m, lead, tail)
    else:
        y = _echo_out(m, lead, tail)
    peak = np.max(np.abs(y)) + 1e-9
    y = y * (10 ** (-1 / 20) / peak)  # normalise to -1 dBFS

    dest.parent.mkdir(parents=True, exist_ok=True)
    wav = dest.with_suffix(".wav")
    sf.write(wav, y.T, SR)
    if shutil.which("ffmpeg"):
        mp3 = dest.with_suffix(".mp3")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "192k", str(mp3)])
        if r.returncode == 0:
            wav.unlink()
            return mp3
    return wav
