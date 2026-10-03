"""Audio analysis: tempo, beat grid, key, energy and intro/outro shape."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import librosa
import numpy as np

from .keys import estimate_key

ANALYSIS_VERSION = 1
SR = 22050
HOP = 512
SEGMENT_SECONDS = 45.0  # how much of the intro / outro to characterise
EDGE_SECONDS = 8.0      # window used to classify intro / outro type
FADE_SECONDS = 4.0      # a quiet tail at least this long counts as a fade-out


@dataclass
class Segment:
    start: float
    end: float
    rms_db: float
    centroid: float
    low_ratio: float
    onset_rate: float
    kick_presence: float
    mfcc: list[float]
    key: str
    camelot: str
    key_confidence: float


@dataclass
class TrackAnalysis:
    path: str
    title: str
    duration: float
    start: float          # first non-silent moment
    end: float            # last non-silent moment
    bpm: float
    beats: list[float]
    downbeats: list[float]
    key: str
    camelot: str
    key_confidence: float
    loudness_db: float    # median frame level of the track body
    groove_start: float   # where the track reaches full level
    groove_end: float     # where it drops away (start of fade / outro tail)
    intro: Segment
    outro: Segment
    intro_type: str       # "beat" | "ambient" | "fade"
    outro_type: str
    source: str = "local"
    version: int = ANALYSIS_VERSION

    @property
    def beat_len(self) -> float:
        return 60.0 / self.bpm

    @property
    def bar_len(self) -> float:
        return 4 * self.beat_len

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TrackAnalysis":
        d = dict(d)
        d["intro"] = Segment(**d["intro"])
        d["outro"] = Segment(**d["outro"])
        return cls(**d)


def _frames(t: float) -> int:
    return int(round(t * SR / HOP))


def _kick_presence(low_env: np.ndarray, beat_frames: np.ndarray, f0: int, f1: int, ref: float) -> float:
    """Fraction of beats in [f0, f1) carrying a solid low-end hit."""
    sel = beat_frames[(beat_frames >= f0) & (beat_frames < f1)]
    if len(sel) == 0 or ref <= 0:
        return 0.0
    return float(np.mean(low_env[sel] >= 0.5 * ref))


def _segment(y, t0, t1, onset_env, low_env, beat_frames, low_ref) -> Segment:
    t1 = max(t1, t0 + 1.0)
    seg = y[int(t0 * SR):int(t1 * SR)]
    if len(seg) < 2048:
        seg = np.pad(seg, (0, 2048 - len(seg)))
    rms_db = float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9))
    spec = np.abs(librosa.stft(seg, n_fft=2048, hop_length=HOP))
    power = spec ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=2048)
    total = power.sum() + 1e-12
    low_ratio = float(power[freqs < 150].sum() / total)
    centroid = float(librosa.feature.spectral_centroid(S=spec, sr=SR).mean())
    mel = librosa.feature.melspectrogram(S=power, sr=SR)
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel), n_mfcc=13).mean(axis=1)
    f0, f1 = _frames(t0), _frames(t1)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env[f0:f1], sr=SR, hop_length=HOP)
    chroma = librosa.feature.chroma_cqt(y=seg, sr=SR, hop_length=2048)
    key, cam, conf = estimate_key(chroma.mean(axis=1))
    return Segment(
        start=round(t0, 3), end=round(t1, 3), rms_db=rms_db, centroid=centroid,
        low_ratio=low_ratio, onset_rate=len(onsets) / (t1 - t0),
        kick_presence=_kick_presence(low_env, beat_frames, f0, f1, low_ref),
        mfcc=[float(v) for v in mfcc], key=key, camelot=cam, key_confidence=conf,
    )


def _edge_type(kick: float, quiet_tail: float = 0.0) -> str:
    if quiet_tail >= FADE_SECONDS:
        return "fade"
    return "beat" if kick >= 0.6 else "ambient"


def analyze_file(path: str | Path, source: str = "local") -> TrackAnalysis:
    path = Path(path)
    y, _ = librosa.load(str(path), sr=SR, mono=True)
    duration = len(y) / SR
    _, (i0, i1) = librosa.effects.trim(y, top_db=50)
    start, end = i0 / SR, i1 / SR

    onset_env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    _, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=SR, hop_length=HOP)
    beat_frames = np.asarray(beat_frames, dtype=int)
    beats = librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP)
    if len(beats) > 8:
        # Least-squares fit of the beat grid gives a steadier BPM than the tempo estimate.
        idx = np.arange(len(beats))
        slope = np.polyfit(idx, beats, 1)[0]
        bpm = 60.0 / slope
    else:
        bpm = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=onset_env, sr=SR, hop_length=HOP))[0])

    # Low-band (kick / bass) onsets, used for downbeat phase and kick presence.
    mel = librosa.feature.melspectrogram(y=y, sr=SR, hop_length=HOP, n_mels=64, fmax=8000)
    low_env = librosa.onset.onset_strength(S=librosa.power_to_db(mel[:6]), sr=SR, hop_length=HOP)
    n = min(len(low_env), len(onset_env))
    low_env, onset_env = low_env[:n], onset_env[:n]
    beat_frames = beat_frames[beat_frames < n]
    beats = beats[:len(beat_frames)]
    low_ref = float(np.median(low_env[beat_frames])) if len(beat_frames) else 0.0

    # Downbeat phase: bar starts tend to carry stronger low-end + harmonic changes.
    if len(beat_frames) >= 8:
        strength = low_env / (low_env.max() + 1e-9) + onset_env / (onset_env.max() + 1e-9)
        phase = int(np.argmax([strength[beat_frames[k::4]].mean() for k in range(4)]))
        downbeats = beats[phase::4]
    else:
        downbeats = beats

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=1.0)
    body = rms_db[_frames(start):_frames(end)]
    loudness = float(np.median(body)) if len(body) else float(np.median(rms_db))
    win = max(1, _frames(1.0))
    smooth = np.convolve(rms_db, np.ones(win) / win, mode="same")
    loud = np.where(smooth >= loudness - 6)[0]
    times = librosa.frames_to_time(np.arange(len(smooth)), sr=SR, hop_length=HOP)
    groove_start = float(times[loud[0]]) if len(loud) else start
    groove_end = float(times[loud[-1]]) if len(loud) else end

    seg_len = min(SEGMENT_SECONDS, (end - start) / 2)
    intro = _segment(y, start, start + seg_len, onset_env, low_env, beat_frames, low_ref)
    outro_end = max(groove_end, start + seg_len)
    outro = _segment(y, outro_end - seg_len, outro_end, onset_env, low_env, beat_frames, low_ref)

    edge = min(EDGE_SECONDS, (end - start) / 4)
    intro_type = _edge_type(_kick_presence(low_env, beat_frames, _frames(start), _frames(start + edge), low_ref))
    outro_type = _edge_type(_kick_presence(low_env, beat_frames, _frames(end - edge), _frames(end), low_ref),
                            quiet_tail=end - groove_end)

    chroma = librosa.feature.chroma_cqt(y=y[int(start * SR):int(end * SR)], sr=SR, hop_length=4096)
    key, cam, conf = estimate_key(chroma.mean(axis=1))

    return TrackAnalysis(
        path=str(path.resolve()), title=path.stem, duration=duration,
        start=float(start), end=float(end), bpm=float(bpm),
        beats=[round(float(b), 4) for b in beats],
        downbeats=[round(float(b), 4) for b in downbeats],
        key=key, camelot=cam, key_confidence=conf, loudness_db=loudness,
        groove_start=groove_start, groove_end=groove_end,
        intro=intro, outro=outro, intro_type=intro_type, outro_type=outro_type,
        source=source,
    )


def _cache_key(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{ANALYSIS_VERSION}"
    return hashlib.sha1(raw.encode()).hexdigest()


def analyze_cached(path: str | Path, cache_dir: Path, source: str = "local") -> TrackAnalysis:
    path = Path(path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{_cache_key(path)}.json"
    if cache_file.exists():
        try:
            ta = TrackAnalysis.from_dict(json.loads(cache_file.read_text()))
            ta.source = source
            return ta
        except (TypeError, ValueError, KeyError):
            pass
    ta = analyze_file(path, source=source)
    cache_file.write_text(json.dumps(ta.to_dict()))
    return ta
