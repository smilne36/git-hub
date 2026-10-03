"""Where candidate songs come from: local folders, SoundCloud, Spotify."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

AUDIO_EXT = {".mp3", ".wav", ".flac", ".aif", ".aiff", ".m4a", ".ogg", ".opus", ".aac"}


@dataclass
class Candidate:
    path: Path
    source: str  # "local" | "soundcloud" | "spotify->local" | "spotify->soundcloud"


def scan_local(paths: list[str]) -> list[Path]:
    found = []
    for p in map(Path, paths):
        p = p.expanduser()
        if p.is_file() and p.suffix.lower() in AUDIO_EXT:
            found.append(p)
        elif p.is_dir():
            found += sorted(f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXT)
    return found


# --- SoundCloud -------------------------------------------------------------

def _ydl(cache_dir: Path):
    import yt_dlp

    return yt_dlp.YoutubeDL({
        "format": "bestaudio/best",
        "outtmpl": str(cache_dir / "soundcloud" / "%(uploader)s - %(title)s [%(id)s].%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "noplaylist": False,
    })


def _downloaded_paths(info) -> list[Path]:
    if not info:
        return []
    if info.get("entries") is not None:
        return [p for e in info["entries"] for p in _downloaded_paths(e)]
    out = [Path(d["filepath"]) for d in info.get("requested_downloads", []) if d.get("filepath")]
    return [p for p in out if p.exists()]


def fetch_soundcloud(urls: list[str], cache_dir: Path) -> list[Path]:
    """Download tracks / sets / profile pages from SoundCloud for analysis.

    Only fetch tracks you have the right to use (your own uploads, free downloads,
    or tracks the artist allows). Go+-only tracks come through as 30 s previews.
    """
    if not urls:
        return []
    with _ydl(cache_dir) as ydl:
        paths = []
        for url in urls:
            paths += _downloaded_paths(ydl.extract_info(url, download=True))
    return paths


def search_soundcloud(query: str, cache_dir: Path) -> Path | None:
    with _ydl(cache_dir) as ydl:
        paths = _downloaded_paths(ydl.extract_info(f"scsearch1:{query}", download=True))
    return paths[0] if paths else None


# --- Spotify ----------------------------------------------------------------

def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\b(original mix|extended mix|radio edit|feat\.?|ft\.?)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _local_label(path: Path) -> str:
    try:
        from mutagen import File as MFile

        tags = MFile(path, easy=True)
        if tags and tags.get("title"):
            artist = (tags.get("artist") or [""])[0]
            return f"{artist} {tags['title'][0]}"
    except Exception:
        pass
    return path.stem


def spotify_tracks(url: str) -> list[str]:
    """Return 'Artist - Title' strings for a Spotify playlist, album or track URL.

    Needs SPOTIPY_CLIENT_ID / SPOTIPY_CLIENT_SECRET (free app at developer.spotify.com).
    Spotify doesn't expose audio, so these names are matched to local files or SoundCloud.
    """
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    if not (os.environ.get("SPOTIPY_CLIENT_ID") and os.environ.get("SPOTIPY_CLIENT_SECRET")):
        raise SystemExit("Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET to read Spotify links.")
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials())
    m = re.search(r"(playlist|album|track)[/:]([A-Za-z0-9]+)", url)
    if not m:
        raise SystemExit(f"Not a Spotify playlist/album/track link: {url}")
    kind, sid = m.groups()

    def label(t):
        return f"{', '.join(a['name'] for a in t['artists'])} - {t['name']}"

    if kind == "track":
        return [label(sp.track(sid))]
    if kind == "album":
        page = sp.album_tracks(sid)
        items = lambda p: p["items"]  # noqa: E731
    else:
        page = sp.playlist_items(sid, additional_types=("track",))
        items = lambda p: [i["track"] for i in p["items"] if i.get("track")]  # noqa: E731
    names = []
    while page:
        names += [label(t) for t in items(page) if t and t.get("name")]
        page = sp.next(page) if page.get("next") else None
    return names


def resolve_spotify(urls: list[str], local: list[Path], cache_dir: Path,
                    soundcloud_fallback: bool) -> tuple[list[Candidate], list[str]]:
    if not urls:
        return [], []
    index = [(_norm(_local_label(p)), p) for p in local]
    found, missing = [], []
    for url in urls:
        for name in spotify_tracks(url):
            target = _norm(name)
            best = max(index, key=lambda e: SequenceMatcher(None, target, e[0]).ratio(), default=None)
            if best and SequenceMatcher(None, target, best[0]).ratio() >= 0.8:
                found.append(Candidate(best[1], "spotify->local"))
                continue
            hit = search_soundcloud(name, cache_dir) if soundcloud_fallback else None
            if hit:
                found.append(Candidate(hit, "spotify->soundcloud"))
            else:
                missing.append(name)
    return found, missing
