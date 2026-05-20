"""Dry-run: fetch from all sources, score, print top N matches.

Does NOT touch seen_jobs.db and does NOT post to Discord. Safe to run
repeatedly while tuning keywords.

Usage:  python -m bot.preview [N] [config.yaml]
        N defaults to 10, config defaults to config.yaml.
"""
import sys
from pathlib import Path

from .config import Config
from .matcher import score
from .sources import build_sources


def main(limit: int = 10, config_path: str = "config.yaml") -> int:
    if not Path(config_path).exists():
        print(f"config not found: {config_path} (copy config.example.yaml)")
        return 1

    cfg = Config.load(config_path)
    search = cfg.get("search", default={})
    keywords = search.get("keywords", [])
    excludes = search.get("exclude_keywords", [])
    locations = search.get("locations", [])
    min_score = search.get("min_match_score", 1)

    matches: list[tuple] = []
    for src in build_sources(cfg.raw):
        print(f"[fetch] {src.name}")
        try:
            jobs = src.fetch()
        except Exception as e:
            print(f"  failed: {e}")
            continue
        print(f"  got {len(jobs)} jobs")
        for job in jobs:
            sc = score(job, keywords, excludes, locations)
            if sc >= min_score:
                matches.append((job, sc))

    matches.sort(key=lambda t: -t[1])
    print(f"\n=== {len(matches)} total matches, showing top {min(limit, len(matches))} ===\n")
    for job, sc in matches[:limit]:
        print(f"[{sc}] {job.title}")
        print(f"     {job.company} | {job.location or '?'} | {job.source}")
        print(f"     {job.url}\n")
    return 0


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    cfg_path = sys.argv[2] if len(sys.argv) > 2 else "config.yaml"
    sys.exit(main(n, cfg_path))
