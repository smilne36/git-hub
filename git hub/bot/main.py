import sys
from pathlib import Path

from .config import Config
from .storage import SeenStore
from .matcher import score
from .notifier import send_email, render_html, send_discord
from .sources import build_sources
from .applier import build_applier


def main(config_path: str = "config.yaml") -> int:
    if not Path(config_path).exists():
        print(f"config not found: {config_path} (copy config.example.yaml)")
        return 1

    cfg = Config.load(config_path)
    search = cfg.get("search", default={})
    keywords = search.get("keywords", [])
    excludes = search.get("exclude_keywords", [])
    locations = search.get("locations", [])
    min_score = search.get("min_match_score", 1)

    seen = SeenStore()
    sources = build_sources(cfg.raw)

    auto = cfg.get("auto_apply", default={}) or {}
    auto_enabled = auto.get("enabled", False)
    auto_sources = set(auto.get("only_sources", []))
    dry_run = auto.get("dry_run", True)
    profile = cfg.get("profile", default={}) or {}

    matches: list[tuple] = []  # (job, score, applied)

    for src in sources:
        print(f"[fetch] {src.name}")
        try:
            jobs = src.fetch()
        except Exception as e:
            print(f"  failed: {e}")
            continue
        print(f"  got {len(jobs)} jobs")

        for job in jobs:
            if seen.has(job.id):
                continue
            sc = score(job, keywords, excludes, locations)
            if sc < min_score:
                seen.add(job.id, src.name)  # mark seen even if not matched, so we don't re-score
                continue

            applied = False
            if auto_enabled and src.name in auto_sources:
                applier = build_applier(src.name, profile, dry_run=dry_run)
                if applier:
                    ok, msg = applier.apply(job)
                    print(f"  apply {job.id}: {msg}")
                    if ok and not dry_run:
                        seen.mark_applied(job.id)
                        applied = True

            matches.append((job, sc, applied))
            seen.add(job.id, src.name)

    if not matches:
        print("no new matches")
        return 0

    matches.sort(key=lambda t: -t[1])

    notified = False
    email_cfg = cfg.get("email", default={}) or {}
    if email_cfg.get("username"):
        send_email(email_cfg, f"{len(matches)} new job matches", render_html(matches))
        print(f"emailed {len(matches)} matches")
        notified = True

    discord_cfg = cfg.get("discord", default={}) or {}
    if discord_cfg.get("webhook_url"):
        send_discord(discord_cfg["webhook_url"], matches)
        print(f"posted {len(matches)} matches to discord")
        notified = True

    if not notified:
        print("no notifier configured; printing matches:")
        for job, sc, applied in matches:
            print(f"  [{sc}{'*' if applied else ''}] {job.title} @ {job.company} — {job.url}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml"))
