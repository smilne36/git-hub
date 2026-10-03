"""Command line: python -m transitions suggest my_song.mp3 --library ~/Music ..."""
from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import report
from .analyze import analyze_cached
from .match import rank
from .render import render
from .sources import Candidate, fetch_soundcloud, resolve_spotify, scan_local

DEFAULT_CACHE = Path(os.environ.get("TRANSITIONS_CACHE", "~/.cache/song-transitions")).expanduser()


def _analyze_one(args):
    path, cache, source = args
    try:
        return analyze_cached(path, cache, source)
    except Exception as e:  # corrupt / unsupported file shouldn't kill the run
        print(f"  ! skipped {Path(path).name}: {e}", file=sys.stderr)
        return None


def _analyze_all(cands: list[Candidate], cache: Path, jobs: int):
    seen, unique = set(), []
    for c in cands:
        key = Path(c.path).resolve()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    print(f"Analyzing {len(unique)} candidate track(s)...", file=sys.stderr)
    work = [(str(c.path), cache / "analysis", c.source) for c in unique]
    if jobs == 1 or len(work) < 2:
        results = map(_analyze_one, work)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            results = list(ex.map(_analyze_one, work))
    return [r for r in results if r is not None]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:60]


def cmd_suggest(a) -> None:
    cache = Path(a.cache).expanduser()
    song_path = a.song
    if re.match(r"https?://", song_path):
        got = fetch_soundcloud([song_path], cache)
        if not got:
            sys.exit(f"Couldn't download {song_path}")
        song_path = got[0]
    song = analyze_cached(song_path, cache / "analysis", "yours")
    print(report.describe(song), file=sys.stderr)

    local = scan_local(a.library)
    cands = [Candidate(p, "local") for p in local]
    cands += [Candidate(p, "soundcloud") for p in fetch_soundcloud(a.soundcloud, cache)]
    spot, missing = resolve_spotify(a.spotify, local, cache, a.soundcloud_fallback)
    cands += spot
    if missing:
        print(f"{len(missing)} Spotify track(s) not found locally"
              + ("" if a.soundcloud_fallback else " (add --soundcloud-fallback to search SoundCloud)")
              + ":\n  " + "\n  ".join(missing[:20]), file=sys.stderr)
    if not cands:
        sys.exit("No candidate songs. Pass --library, --soundcloud or --spotify.")

    library = _analyze_all(cands, cache, a.jobs)
    before, after = rank(song, library, a.bars)
    before, after = before[:a.top], after[:a.top]

    out = Path(a.out).expanduser() / _slug(song.title)
    if a.render:
        print(f"Rendering transitions into {out}/previews ...", file=sys.stderr)
        for label, ms in (("before", before), ("after", after)):
            for i, m in enumerate(ms[:a.render], 1):
                name = f"{label}_{i:02d}_{_slug(m.outgoing.title)}__to__{_slug(m.incoming.title)}"
                m.preview = str(render(m, out / "previews" / name, a.lead, a.tail, a.keylock))

    print()
    print(report.table(f"Play BEFORE {song.title}", before, "outgoing"))
    print()
    print(report.table(f"Play AFTER {song.title}", after, "incoming"))
    report.write(out, song, before, after)
    print(f"\nSaved list + report: {out}/report.html, results.csv, results.json")


def cmd_analyze(a) -> None:
    cache = Path(a.cache).expanduser() / "analysis"
    for p in scan_local(a.files):
        print(report.describe(analyze_cached(p, cache)))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="transitions", description="Find and render smooth DJ transitions for a song.")
    ap.add_argument("--cache", default=str(DEFAULT_CACHE), help="cache for analyses + downloads")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("suggest", help="rank songs to play before/after yours and render previews")
    s.add_argument("song", help="your song: a local file or a SoundCloud URL")
    s.add_argument("--library", "-l", nargs="*", default=[], help="local folders/files of candidate songs")
    s.add_argument("--soundcloud", "-s", nargs="*", default=[], help="SoundCloud track/set/profile URLs")
    s.add_argument("--spotify", "-p", nargs="*", default=[], help="Spotify playlist/album/track URLs")
    s.add_argument("--soundcloud-fallback", action="store_true",
                   help="search SoundCloud for Spotify tracks missing from your library")
    s.add_argument("--top", type=int, default=10, help="how many suggestions per direction")
    s.add_argument("--render", type=int, default=3, help="render previews for the top N each way (0 = none)")
    s.add_argument("--bars", type=int, default=None, help="force blend length in bars (default 8 or 16)")
    s.add_argument("--lead", type=float, default=20.0, help="seconds before the transition in previews")
    s.add_argument("--tail", type=float, default=20.0, help="seconds after the transition in previews")
    s.add_argument("--keylock", choices=["auto", "always", "never"], default="auto",
                   help="keep pitch when stretching (auto: only above 3%%)")
    s.add_argument("--out", "-o", default="transitions_out", help="output folder")
    s.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 1, help="parallel analysis workers")
    s.set_defaults(func=cmd_suggest)

    z = sub.add_parser("analyze", help="print BPM / key / intro / outro for files or folders")
    z.add_argument("files", nargs="+")
    z.set_defaults(func=cmd_analyze)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
