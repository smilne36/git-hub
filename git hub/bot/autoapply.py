"""Human-in-the-loop auto-apply CLI.

Runs LOCALLY on your machine (so your resume file stays local, not in
the repo). Loads jobs from seen_jobs.db, filters to strong AI-scored
Greenhouse matches you haven't applied to yet, shows each one, and
asks you to confirm before submitting.

Usage:
    python -m bot.autoapply                       # list & confirm each (min score 8)
    python -m bot.autoapply --min-score 9         # raise the bar
    python -m bot.autoapply --min-score 8 --yes   # skip confirms (yolo)
    python -m bot.autoapply <url_or_id>           # apply to just this one
    python -m bot.autoapply --dry-run             # simulate — never submits

Only Greenhouse jobs can be submitted programmatically (Lever/Ashby
have per-form custom fields). Postings with custom required questions
will get rejected by the API — the CLI reports that and moves on.

Requirements:
    - config.yaml has profile.full_name, email, phone, resume_path filled
    - The file at resume_path exists (usually a PDF)
    - ANTHROPIC_API_KEY has been set at least once so AI scores exist

After a run, commit seen_jobs.db so the workflow doesn't re-notify you:
    git add "git hub/seen_jobs.db" && git commit -m "applied" && git push
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .applier import build_applier
from .config import Config, Job
from .storage import SeenStore


def _confirm(prompt: str) -> bool:
    try:
        r = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return r in ("y", "yes")


def _row_to_job(row: dict) -> Job:
    return Job(
        id=row["id"],
        source=row["source"] or "",
        title=row.get("title") or "",
        company=row.get("company") or "",
        location=row.get("location") or "",
        url=row.get("url") or "",
        description="",
        apply_url=row.get("url") or "",
    )


def _print_match(row: dict) -> None:
    ai = f"[AI {row['ai_score']}]" if row.get("ai_score") is not None else "[AI ?]"
    print()
    print(f"{ai} {row.get('title') or '(no title)'}")
    print(f"      {row.get('company') or '?'} | {row.get('location') or '?'}")
    if row.get("ai_reason"):
        print(f"      {row['ai_reason']}")
    print(f"      {row.get('url') or row['id']}")


def _pick_candidates(store: SeenStore, min_score: int) -> list[dict]:
    return store._rows_where(
        "source = 'greenhouse' AND ai_score >= ? AND (interest IS NULL OR interest != 2)"
        " ORDER BY ai_score DESC, first_seen DESC",
        (min_score,),
    )


def _apply_one(row: dict, profile: dict, dry_run: bool, store: SeenStore) -> bool:
    job = _row_to_job(row)
    applier = build_applier(row["source"], profile, dry_run=dry_run)
    if applier is None:
        print(f"  skip: no applier for source={row['source']}")
        return False
    ok, msg = applier.apply(job)
    print(f"  -> {msg}")
    if ok and not dry_run:
        store.set_interest(job.id, 2)
    return ok


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("target", nargs="?", help="optional url or job id")
    p.add_argument("--min-score", type=int, default=8, help="min AI score (default 8)")
    p.add_argument("--yes", action="store_true", help="skip confirms (yolo)")
    p.add_argument("--dry-run", action="store_true", help="simulate, don't submit")
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args(argv)

    if not Path(args.config).exists():
        print(f"config not found: {args.config}")
        return 1

    cfg = Config.load(args.config)
    profile = cfg.get("profile", default={}) or {}

    missing = [k for k in ("full_name", "email", "resume_path") if not profile.get(k)]
    if missing:
        print(f"profile missing fields: {missing} — edit config.yaml")
        return 1
    resume = Path(profile["resume_path"])
    if not args.dry_run and not resume.exists():
        print(f"resume not found at {resume}")
        return 1

    store = SeenStore()

    if args.target:
        job_id = store.find_by_ref(args.target)
        if job_id is None:
            print(f"no job matching {args.target!r}")
            return 2
        row = store.get_row(job_id)
        if row["source"] != "greenhouse":
            print(f"can't auto-apply — source is {row['source']!r} (only greenhouse supported)")
            return 2
        _print_match(row)
        if args.yes or _confirm("Apply? [y/N] "):
            _apply_one(row, profile, args.dry_run, store)
        return 0

    candidates = _pick_candidates(store, args.min_score)
    if not candidates:
        print(f"no unapplied greenhouse matches with AI score >= {args.min_score}")
        return 0

    print(f"{len(candidates)} candidate(s) at AI >= {args.min_score}"
          + (" (DRY RUN)" if args.dry_run else ""))
    submitted = failed = skipped = 0
    for row in candidates:
        _print_match(row)
        if args.yes or _confirm("Apply? [y/N] "):
            ok = _apply_one(row, profile, args.dry_run, store)
            if ok:
                submitted += 1
            else:
                failed += 1
        else:
            skipped += 1

    print()
    print(f"done: {submitted} submitted, {failed} rejected, {skipped} skipped")
    if submitted and not args.dry_run:
        print("commit seen_jobs.db to persist:")
        print('  git add "git hub/seen_jobs.db" && git commit -m "applied" && git push')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
