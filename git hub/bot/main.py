import sys
from pathlib import Path

from .config import Config
from .storage import SeenStore
from .matcher import score
from .notifier import send_discord
from .sources import build_sources
from .applier import build_applier
from .ai_score import AIScorer


def main(config_path: str = "config.yaml") -> int:
    if not Path(config_path).exists():
        print(f"config not found: {config_path} (copy config.example.yaml)")
        return 1

    cfg = Config.load(config_path)
    search = cfg.get("search", default={})
    keywords = search.get("keywords", [])
    excludes = search.get("exclude_keywords", [])
    required = search.get("required_keywords", [])
    locations = search.get("locations", [])
    min_score = search.get("min_match_score", 1)

    seen = SeenStore()
    sources = build_sources(cfg.raw)

    ai_cfg = cfg.get("ai_scoring", default={}) or {}
    scorer: AIScorer | None = None
    if ai_cfg.get("enabled", False):
        scorer = AIScorer(
            bio=ai_cfg.get("candidate_bio", ""),
            model=ai_cfg.get("model", "claude-haiku-4-5"),
        )
        if not scorer.enabled:
            print("[ai_score] disabled (ANTHROPIC_API_KEY not set or SDK missing)")
            scorer = None
    ai_min_kw = ai_cfg.get("min_keyword_score", 1)

    auto = cfg.get("auto_apply", default={}) or {}
    auto_enabled = auto.get("enabled", False)
    auto_sources = set(auto.get("only_sources", []))
    dry_run = auto.get("dry_run", True)
    profile = cfg.get("profile", default={}) or {}

    matches: list[tuple] = []  # (job, keyword_score, applied, ai_score, ai_reason)

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
            sc = score(job, keywords, excludes, locations, required)
            if sc < min_score:
                seen.add(job.id, src.name, url=job.url, title=job.title, company=job.company, location=job.location)
                continue

            ai_sc: int | None = None
            ai_rz: str | None = None
            if scorer and sc >= ai_min_kw:
                ai_sc, ai_rz = seen.get_ai_score(job.id)
                if ai_sc is None:
                    ai_sc, ai_rz = scorer.score(job)
                    if ai_sc is not None:
                        seen.set_ai_score(job.id, ai_sc, ai_rz)

            applied = False
            if auto_enabled and src.name in auto_sources:
                applier = build_applier(src.name, profile, dry_run=dry_run)
                if applier:
                    ok, msg = applier.apply(job)
                    print(f"  apply {job.id}: {msg}")
                    if ok and not dry_run:
                        seen.mark_applied(job.id)
                        applied = True

            matches.append((job, sc, applied, ai_sc, ai_rz))
            seen.add(job.id, src.name, url=job.url, title=job.title, company=job.company, location=job.location)

    if not matches:
        print("no new matches")
        return 0

    # Sort by AI score first (None sorts last), keyword score as tiebreaker.
    matches.sort(key=lambda t: (-(t[3] or 0), -t[1]))

    webhook = (cfg.get("discord", default={}) or {}).get("webhook_url", "").strip()
    if webhook:
        send_discord(webhook, matches)
        print(f"posted {len(matches)} matches to discord")
    else:
        print("discord.webhook_url not set; printing matches:")
        for job, sc, applied, ai_sc, ai_rz in matches:
            ai = f" ai={ai_sc}" if ai_sc is not None else ""
            print(f"  [{sc}{ai}{'*' if applied else ''}] {job.title} @ {job.company} — {job.url}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml"))
