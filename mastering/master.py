#!/usr/bin/env python3
"""Auto-master a stereo bounce for streaming.

Examples
--------
    # Master a bounce to the streaming default (-14 LUFS, -1 dBTP true peak):
    python master.py mysong.wav

    # Just measure a file, change nothing:
    python master.py mysong.wav --analyze

    # A brighter, harder master aimed at club loudness:
    python master.py mysong.wav --tone bright --strength strong --target club

    # Match the tonal balance of a track you love, then also export an MP3:
    python master.py mysong.wav --reference favourite.wav --mp3

Run `python master.py -h` for the full list of options.
"""

from __future__ import annotations

import argparse
import os
import sys

from masterlib import audio_io
from masterlib.analysis import LoudnessStats
from masterlib.chain import MasterResult, master
from masterlib.presets import (
    DEFAULT_STRENGTH,
    DEFAULT_TONE,
    DEFAULT_TRUE_PEAK_DB,
    STRENGTHS,
    TARGETS,
    TONES,
)


def _fmt_db(x: float) -> str:
    return "-inf" if x == float("-inf") else f"{x:+.1f}"


def _print_stats(label: str, s: LoudnessStats) -> None:
    print(f"  {label:<8} "
          f"LUFS {s.integrated_lufs:6.1f}   "
          f"true-peak {_fmt_db(s.true_peak_dbtp):>6} dBTP   "
          f"peak {_fmt_db(s.sample_peak_dbfs):>6} dBFS   "
          f"crest {s.crest_db:4.1f} dB")


def _print_report(result: MasterResult, out_path: str) -> None:
    print("\n=== Mastering report ===")
    print(f"  target    {result.target_lufs:.1f} LUFS  /  "
          f"ceiling {result.true_peak_ceiling_db:.1f} dBTP")
    print(f"  tone      {result.tone} ({TONES[result.tone].description})")
    print(f"  strength  {result.strength}")
    if result.reference_matched:
        moves = ", ".join(
            f"{f[1]:.0f}Hz {f[2]:+.1f}dB" for f in result.match_filters
        ) or "(no significant moves)"
        print(f"  reference EQ moves: {moves}")
    print(f"  makeup    {result.makeup_gain_db:+.1f} dB into the limiter")
    print()
    _print_stats("before", result.before)
    _print_stats("after", result.after)
    loud_change = result.after.integrated_lufs - result.before.integrated_lufs
    crest_change = result.after.crest_db - result.before.crest_db
    print(f"\n  loudness change {loud_change:+.1f} LU   "
          f"dynamics change {crest_change:+.1f} dB (negative = more compressed)")
    print(f"\n  wrote: {out_path}")


def _default_output(input_path: str) -> str:
    root, _ = os.path.splitext(input_path)
    return f"{root}.mastered.wav"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Auto-master a stereo bounce for streaming.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("input", help="input audio file (WAV/FLAC/AIFF/OGG)")
    p.add_argument("-o", "--output", help="output WAV path")
    p.add_argument("--analyze", action="store_true",
                   help="only measure the input and print stats; write nothing")
    p.add_argument("--target", choices=sorted(TARGETS),
                   help="named loudness target (overrides --target-lufs)")
    p.add_argument("--target-lufs", type=float, default=TARGETS["streaming"],
                   help="explicit integrated loudness target in LUFS")
    p.add_argument("--true-peak", type=float, default=DEFAULT_TRUE_PEAK_DB,
                   help="true-peak ceiling in dBTP")
    p.add_argument("--tone", choices=sorted(TONES), default=DEFAULT_TONE,
                   help="tonal colouring")
    p.add_argument("--strength", choices=sorted(STRENGTHS), default=DEFAULT_STRENGTH,
                   help="compression/limiting intensity")
    p.add_argument("--reference", help="reference track to match tonal balance to")
    p.add_argument("--match-strength", type=float, default=0.6,
                   help="how far to move toward the reference, 0..1")
    p.add_argument("--mp3", action="store_true",
                   help="also write a 320 kbps MP3 alongside the WAV (if supported)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2

    audio = audio_io.load(args.input)
    print(f"loaded {args.input}: {audio.duration:.1f}s, {audio.channels}ch, {audio.sr} Hz")

    if args.analyze:
        from masterlib.analysis import analyze
        print("\n=== Analysis ===")
        _print_stats("input", analyze(audio))
        return 0

    target_lufs = TARGETS[args.target] if args.target else args.target_lufs

    reference = None
    if args.reference:
        if not os.path.isfile(args.reference):
            print(f"error: reference not found: {args.reference}", file=sys.stderr)
            return 2
        reference = audio_io.load(args.reference)

    result = master(
        audio,
        target_lufs=target_lufs,
        true_peak_db=args.true_peak,
        tone=args.tone,
        strength=args.strength,
        reference=reference,
        match_strength=args.match_strength,
    )

    out_path = args.output or _default_output(args.input)
    audio_io.save(out_path, result.audio)
    _print_report(result, out_path)

    if args.mp3:
        mp3_path = os.path.splitext(out_path)[0] + ".mp3"
        if audio_io.try_write_mp3(mp3_path, result.audio):
            print(f"  wrote: {mp3_path}")
        else:
            print("  note: MP3 export unavailable in this pedalboard build; "
                  "kept WAV only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
