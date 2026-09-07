"""Application tracker CLI.

Discord webhooks can't read message reactions, so triage happens via
this CLI. Grab the job URL from a Discord embed and run:

    python -m bot.applied apply    https://boards.greenhouse.io/roblox/jobs/12345
    python -m bot.applied like     https://boards.greenhouse.io/roblox/jobs/12345
    python -m bot.applied pass     https://boards.greenhouse.io/roblox/jobs/12345
    python -m bot.applied list                # 20 most recent applied
    python -m bot.applied pending             # follow-ups due (>= 14 days)

The URL is looked up in seen_jobs.db. Substrings work too, so you can
paste just the ID portion.

Note: seen_jobs.db is committed back to the repo by the workflow, so
to have your applications visible to the nightly digest (which runs
in GitHub Actions), pull before / commit after:

    git pull && python -m bot.applied apply <url> \\
        && git add seen_jobs.db \\
        && git commit -m "applied to X" && git push
"""
from __future__ import annotations

import sys

from .storage import SeenStore


_LEVELS = {"apply": 2, "like": 1, "pass": -1}
_LABELS = {2: "APPLIED", 1: "interested", 0: "-", -1: "passed"}


def _fmt(row: dict) -> str:
    ai = f"[AI {row['ai_score']}] " if row.get("ai_score") is not None else ""
    return (
        f"{ai}{(row.get('title') or '(no title)')[:70]}\n"
        f"    {(row.get('company') or '?')} | {(row.get('location') or '?')}"
        f" | {_LABELS.get(row.get('interest') or 0, '?')}"
        f" | applied {row.get('applied_at') or '-'}\n"
        f"    {row.get('url') or row['id']}"
    )


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1

    cmd = argv[0]
    store = SeenStore()

    if cmd in _LEVELS:
        if len(argv) < 2:
            print(f"usage: bot.applied {cmd} <url_or_id>")
            return 1
        ref = argv[1]
        job_id = store.find_by_ref(ref)
        if job_id is None:
            print(f"no job found matching {ref!r}")
            print("(has the bot pinged it yet? seen_jobs.db only knows what it's fetched)")
            return 2
        store.set_interest(job_id, _LEVELS[cmd])
        row = store.get_row(job_id)
        print(f"marked {_LABELS[_LEVELS[cmd]]}:")
        print(_fmt(row))
        return 0

    if cmd == "list":
        limit = int(argv[1]) if len(argv) > 1 else 20
        rows = store.list_applied(limit)
        if not rows:
            print("no applications yet")
            return 0
        for r in rows:
            print(_fmt(r))
            print()
        return 0

    if cmd == "pending":
        days = int(argv[1]) if len(argv) > 1 else 14
        rows = store.list_pending_follow_up(days)
        if not rows:
            print(f"no follow-ups pending (threshold: {days} days)")
            return 0
        print(f"{len(rows)} follow-up(s) due:")
        for r in rows:
            print(_fmt(r))
            print()
        return 0

    print(f"unknown command: {cmd}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
