"""Headless session state for the GUI.

`MasterSession` holds everything the interface needs -- the loaded audio, its
analysis, the assistant's advice, the current settings, and the last result --
and runs the (slow) mastering step on a background thread so the UI never
freezes. It contains no GUI code at all, which means it can be unit-tested
without a display.
"""

from __future__ import annotations

import os
import threading
from typing import List, Optional, Tuple

from . import audio_io
from .advisor import Advice, advise
from .analysis import LoudnessStats, analyze
from .audio_io import Audio
from .chain import MasterResult, master
from .presets import STRENGTHS, TARGETS, TONES

# Ordered lists so the GUI can show them in combo boxes.
TONE_KEYS: List[str] = ["transparent", "warm", "bright", "open"]
STRENGTH_KEYS: List[str] = ["light", "medium", "strong"]
TARGET_CHOICES: List[Tuple[str, float]] = [
    ("Streaming (-14)", -14.0),
    ("Apple Music (-16)", -16.0),
    ("Loud CD (-9)", -9.0),
    ("Club (-8)", -8.0),
]


class MasterSession:
    def __init__(self) -> None:
        # Input
        self.input_path: Optional[str] = None
        self.audio: Optional[Audio] = None
        self.input_stats: Optional[LoudnessStats] = None
        self.advice: Optional[Advice] = None

        # Settings (defaults match the CLI)
        self.target_lufs: float = TARGETS["streaming"]
        self.true_peak: float = -1.0
        self.tone: str = "transparent"
        self.strength: str = "medium"
        self.reference_path: Optional[str] = None

        # Output / result
        self.output_path: Optional[str] = None
        self.result: Optional[MasterResult] = None
        self.status: str = "Load a bounce (WAV) to begin."
        self.error: Optional[str] = None

        self._busy = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    # --- state queries ----------------------------------------------------
    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    @property
    def has_audio(self) -> bool:
        return self.audio is not None

    # --- loading ----------------------------------------------------------
    def load(self, path: str) -> None:
        """Load a file, analyse it, and run the assistant. Cheap enough for the
        UI thread (analysis of a few minutes of audio is well under a second)."""
        self.error = None
        try:
            self.audio = audio_io.load(path)
        except Exception as exc:  # bad/unsupported file
            self.error = f"Could not load file: {exc}"
            self.status = self.error
            return
        self.input_path = path
        self.result = None
        self.output_path = None
        self.input_stats = analyze(self.audio)
        self.advice = advise(self.audio, self.target_lufs)
        self.status = f"Loaded {os.path.basename(path)}."

    def load_reference(self, path: str) -> None:
        self.reference_path = path or None

    def clear_reference(self) -> None:
        self.reference_path = None

    def apply_recommendations(self) -> None:
        if self.advice is not None:
            self.tone = self.advice.recommended_tone
            self.strength = self.advice.recommended_strength
            self.status = (f"Applied assistant settings: {self.tone} / "
                           f"{self.strength}.")

    def reanalyze_advice(self) -> None:
        """Refresh advice against the current target (loudness advice depends on it)."""
        if self.audio is not None:
            self.advice = advise(self.audio, self.target_lufs)

    def default_output_path(self) -> str:
        root, _ = os.path.splitext(self.input_path or "output.wav")
        return f"{root}.mastered.wav"

    # --- mastering (background) ------------------------------------------
    def start_master(self, output_path: Optional[str] = None) -> None:
        """Kick off mastering on a worker thread. No-op if busy or no audio."""
        if self.audio is None or self.busy:
            return
        self.output_path = output_path or self.default_output_path()
        with self._lock:
            self._busy = True
        self.error = None
        self.status = "Mastering..."
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def run_master_sync(self, output_path: Optional[str] = None) -> Optional[MasterResult]:
        """Synchronous mastering, used by tests."""
        self.output_path = output_path or self.default_output_path()
        self._run()
        return self.result

    def _run(self) -> None:
        try:
            reference = (audio_io.load(self.reference_path)
                         if self.reference_path else None)
            result = master(
                self.audio,
                target_lufs=self.target_lufs,
                true_peak_db=self.true_peak,
                tone=self.tone,
                strength=self.strength,
                reference=reference,
            )
            audio_io.save(self.output_path, result.audio)
            with self._lock:
                self.result = result
                self.status = f"Done -> {os.path.basename(self.output_path)}"
        except Exception as exc:
            with self._lock:
                self.error = f"Mastering failed: {exc}"
                self.status = self.error
        finally:
            with self._lock:
                self._busy = False
