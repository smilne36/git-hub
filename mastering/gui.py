#!/usr/bin/env python3
"""Dear ImGui front-end for the auto-mastering engine.

Run it with:  python gui.py

A single-window app: load a bounce, read the assistant's advice, tweak the
settings with sliders/combos, hit Master, and see the before/after numbers.
All the DSP lives in `masterlib`; this file is only the interface.
"""

from __future__ import annotations

import os
from typing import Optional

from imgui_bundle import hello_imgui, imgui
from imgui_bundle import portable_file_dialogs as pfd

from masterlib.analysis import LoudnessStats
from masterlib.presets import TONES
from masterlib.session import (
    STRENGTH_KEYS,
    TARGET_CHOICES,
    TONE_KEYS,
    MasterSession,
)

# Colours (r, g, b, a) for assistant findings by severity.
_SEVERITY_COLOR = {
    "ok": (0.45, 0.80, 0.45, 1.0),
    "tip": (0.55, 0.75, 1.00, 1.0),
    "warn": (1.00, 0.65, 0.35, 1.0),
}

# Module-level UI state (imgui is immediate-mode; state lives outside the frame).
_session = MasterSession()
_open_dialog: Optional[pfd.open_file] = None
_ref_dialog: Optional[pfd.open_file] = None
_save_dialog: Optional[pfd.save_file] = None

_AUDIO_FILTERS = ["Audio files", "*.wav *.flac *.aiff *.aif *.ogg", "All files", "*"]

# Frame counter, used only by the offscreen smoke test (AUTOMASTER_SMOKE).
_frame = 0


def _col(rgba) -> imgui.ImVec4:
    return imgui.ImVec4(*rgba)


def _fmt(x: float, suffix: str = "") -> str:
    if x == float("-inf"):
        return "-inf" + suffix
    return f"{x:+.1f}{suffix}"


def _stats_line(label: str, s: LoudnessStats) -> None:
    imgui.text(f"{label:<7} {s.integrated_lufs:6.1f} LUFS   "
               f"peak {_fmt(s.true_peak_dbtp, ' dBTP')}   "
               f"crest {s.crest_db:.1f} dB")


def _poll_dialogs() -> None:
    """Resolve any pending native file dialogs (portable-file-dialogs is async)."""
    global _open_dialog, _ref_dialog, _save_dialog
    if _open_dialog is not None and _open_dialog.ready():
        picked = _open_dialog.result()
        if picked:
            _session.load(picked[0])
        _open_dialog = None
    if _ref_dialog is not None and _ref_dialog.ready():
        picked = _ref_dialog.result()
        if picked:
            _session.load_reference(picked[0])
        _ref_dialog = None
    if _save_dialog is not None and _save_dialog.ready():
        chosen = _save_dialog.result()
        if chosen:
            _session.start_master(chosen)
        _save_dialog = None


def _draw_input_panel() -> None:
    global _open_dialog
    imgui.separator_text("1. Your bounce")
    if imgui.button("Open WAV..."):
        _open_dialog = pfd.open_file("Select a stereo bounce", filters=_AUDIO_FILTERS)
    if _session.input_path:
        imgui.same_line()
        imgui.text_disabled(_session.input_path)

    s = _session.input_stats
    if s is not None:
        imgui.spacing()
        _stats_line("input", s)
        imgui.text_disabled(f"{s.duration_s:.1f}s  |  {s.channels}ch  |  {s.sample_rate} Hz")


def _draw_assistant_panel() -> None:
    if _session.advice is None:
        return
    imgui.separator_text("2. Assistant")
    for severity, text in _session.advice.findings:
        color = _SEVERITY_COLOR.get(severity, (1, 1, 1, 1))
        imgui.push_text_wrap_pos(0.0)
        imgui.text_colored(_col(color), text)
        imgui.pop_text_wrap_pos()
    imgui.spacing()
    if imgui.button("Use assistant's recommended settings"):
        _session.apply_recommendations()


def _draw_settings_panel() -> None:
    global _ref_dialog
    imgui.separator_text("3. Settings")

    # Loudness target -- named presets plus a fine-tune slider.
    labels = [c[0] for c in TARGET_CHOICES]
    current = next((i for i, c in enumerate(TARGET_CHOICES)
                    if abs(c[1] - _session.target_lufs) < 1e-6), -1)
    changed, idx = imgui.combo("Loudness target", current, labels)
    if changed:
        _session.target_lufs = TARGET_CHOICES[idx][1]
        _session.reanalyze_advice()
    changed, val = imgui.slider_float("  fine-tune (LUFS)", _session.target_lufs,
                                      -20.0, -6.0, "%.1f")
    if changed:
        _session.target_lufs = val
        _session.reanalyze_advice()

    # Tone.
    t_idx = TONE_KEYS.index(_session.tone)
    changed, t_idx = imgui.combo("Tone", t_idx, TONE_KEYS)
    if changed:
        _session.tone = TONE_KEYS[t_idx]
    imgui.text_disabled("  " + TONES[_session.tone].description)

    # Strength.
    s_idx = STRENGTH_KEYS.index(_session.strength)
    changed, s_idx = imgui.combo("Strength", s_idx, STRENGTH_KEYS)
    if changed:
        _session.strength = STRENGTH_KEYS[s_idx]

    # True-peak ceiling.
    changed, tp = imgui.slider_float("True-peak ceiling (dBTP)", _session.true_peak,
                                     -3.0, 0.0, "%.1f")
    if changed:
        _session.true_peak = tp

    # Optional reference track.
    if imgui.button("Reference track..."):
        _ref_dialog = pfd.open_file("Match tone to this track", filters=_AUDIO_FILTERS)
    if _session.reference_path:
        imgui.same_line()
        imgui.text_disabled(_session.reference_path)
        if imgui.button("clear reference"):
            _session.clear_reference()


def _draw_action_panel() -> None:
    global _save_dialog
    imgui.separator_text("4. Master")

    disabled = _session.busy or not _session.has_audio
    imgui.begin_disabled(disabled)
    if imgui.button("Master  ->  save next to original", imgui.ImVec2(280, 34)):
        _session.start_master()
    imgui.same_line()
    if imgui.button("Master as...", imgui.ImVec2(120, 34)):
        _save_dialog = pfd.save_file("Save master as",
                                     _session.default_output_path(),
                                     ["WAV", "*.wav"])
    imgui.end_disabled()

    if _session.busy:
        imgui.text("Working...")

    if _session.result is not None:
        r = _session.result
        imgui.spacing()
        imgui.separator_text("Result")
        _stats_line("before", r.before)
        _stats_line("after", r.after)
        loud = r.after.integrated_lufs - r.before.integrated_lufs
        imgui.text_disabled(f"loudness {loud:+.1f} LU   makeup {r.makeup_gain_db:+.1f} dB "
                            f"into the limiter")
        if _session.output_path:
            imgui.text_colored(_col((0.45, 0.80, 0.45, 1.0)), f"Saved: {_session.output_path}")


def _gui() -> None:
    _poll_dialogs()
    imgui.text("Auto-master a stereo bounce for streaming.")
    if _session.error:
        imgui.text_colored(_col((1.0, 0.4, 0.4, 1.0)), _session.error)
    imgui.spacing()

    _draw_input_panel()
    _draw_assistant_panel()
    _draw_settings_panel()
    _draw_action_panel()

    # Status bar pinned to the bottom.
    imgui.set_cursor_pos_y(imgui.get_window_height() - 32)
    imgui.separator()
    imgui.text_disabled(_session.status)

    _smoke_step()


def _smoke_step() -> None:
    """Offscreen self-test: render a handful of frames exercising every panel
    (loading a file, applying recommendations) then quit. Enabled only when
    AUTOMASTER_SMOKE is set, so it never affects normal use."""
    global _frame
    if not os.environ.get("AUTOMASTER_SMOKE"):
        return
    _frame += 1
    if _frame == 2 and os.environ.get("AUTOMASTER_SMOKE_FILE"):
        _session.load(os.environ["AUTOMASTER_SMOKE_FILE"])
    elif _frame == 4:
        _session.apply_recommendations()
    elif _frame >= 6:
        hello_imgui.get_runner_params().app_shall_exit = True


def main() -> None:
    hello_imgui.run(
        _gui,
        window_title="Auto-Master",
        window_size=(560, 720),
        fps_idle=10,
    )


if __name__ == "__main__":
    main()
