"""Nightly digest: one Discord summary of today's activity.

Reads seen_jobs.db and posts a single message per run with:
  - new job count in the last 24h
  - strong-match count (AI score >= 8)
  - top matches with their AI takes
  - follow-ups due (applied >= 14 days ago, no reminder yet)

After posting, marks each surfaced follow-up so it's not resurfaced.

Run:  python -m bot.digest [config.yaml]
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .config import Config
from .storage import SeenStore


_HOURS = 24
_TOP_N = 5
_FOLLOW_UP_DAYS = 14


def _iso_hours_ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(
        timespec="seconds"
    )


def _match_line(row: dict) -> str:
    ai = f"**AI {row['ai_score']}** " if row.get("ai_score") is not None else ""
    reason = f" — {row['ai_reason']}" if row.get("ai_reason") else ""
    title = (row.get("title") or "(no title)")[:80]
    url = row.get("url") or ""
    company = row.get("company") or "?"
    return f"{ai}[{title}]({url}) @ {company}{reason}"


def _followup_line(row: dict) -> str:
    title = (row.get("title") or "(no title)")[:80]
    url = row.get("url") or ""
    company = row.get("company") or "?"
    return f"• [{title}]({url}) @ {company} — applied {row['applied_at'][:10]}"


def build_digest(store: SeenStore) -> dict | None:
    since = _iso_hours_ago(_HOURS)
    counts = store.counts_since(since)
    top = store.top_matches_since(since, _TOP_N)
    followups = store.list_pending_follow_up(_FOLLOW_UP_DAYS)

    if not counts["new_jobs"] and not top and not followups:
        return None  # nothing worth posting

    lines = [
        f"**Daily digest** — last {_HOURS}h",
        f"• {counts['new_jobs']} new jobs across sources",
        f"• {counts['strong_matches']} strong matches (AI ≥ 8)",
        f"• {counts['applied']} applications logged",
    ]

    if top:
        lines.append("")
        lines.append("__Top matches from today__")
        for row in top:
            lines.append(_match_line(row))

    if followups:
        lines.append("")
        lines.append(f"__Follow-ups due (≥ {_FOLLOW_UP_DAYS} days since applied)__")
        for row in followups:
            lines.append(_followup_line(row))

    return {
        "content": "\n".join(lines)[:1900],  # discord msg limit is 2000
        "_followup_ids": [r["id"] for r in followups],
    }


def main(config_path: str = "config.yaml") -> int:
    if not Path(config_path).exists():
        print(f"config not found: {config_path}")
        return 1

    cfg = Config.load(config_path)
    webhook = (cfg.get("discord", default={}) or {}).get("webhook_url", "").strip()
    if not webhook:
        print("discord.webhook_url not set")
        return 1

    store = SeenStore()
    digest = build_digest(store)
    if digest is None:
        print("no activity in the digest window")
        return 0

    payload = {"content": digest["content"]}
    r = requests.post(webhook, json=payload, timeout=15)
    if r.status_code >= 400:
        print(f"[digest] webhook failed {r.status_code}: {r.text[:200]}")
        return 1

    for job_id in digest["_followup_ids"]:
        store.mark_follow_up_sent(job_id)

    print(f"posted digest ({len(digest['content'])} chars,"
          f" {len(digest['_followup_ids'])} follow-ups marked)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml"))
