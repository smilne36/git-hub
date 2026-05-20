# Job Search Bot

A Python bot that searches for jobs across public APIs, emails you when
matches are found, and can auto-submit applications on Greenhouse using a
stored resume.

## Sources (all public APIs — no scraping)

| Source     | Endpoint                                                | What it covers                                |
|------------|---------------------------------------------------------|-----------------------------------------------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/<slug>/jobs`        | Any company hosted on Greenhouse              |
| Lever      | `api.lever.co/v0/postings/<slug>`                       | Any company hosted on Lever                   |
| Ashby      | `api.ashbyhq.com/posting-api/job-board/<slug>`          | Any company hosted on Ashby                   |
| RemoteOK   | `remoteok.com/api`                                      | Remote jobs aggregator                        |
| Adzuna     | `api.adzuna.com` (needs free API key)                   | Indeed-style aggregated listings              |

You give it a list of company board slugs (e.g. `airbnb`, `stripe`, `figma`)
and it pulls every open role from each.

> A note on LinkedIn and Indeed: neither offers a usable public API for job
> search, and both actively block scrapers. Adzuna covers the same listings
> Indeed does, the legal way. So the bot just uses APIs.

## Setup

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml — keywords, email creds, board slugs, resume path
python -m bot.main
```

Run it on a schedule (cron, systemd timer, or GitHub Actions) every few
hours. It uses a local SQLite DB to dedupe, so you only get pinged once per
job.

## Auto-apply

Set `auto_apply.enabled: true` in `config.yaml` and the bot will POST your
resume + basic info (name, email, phone) to Greenhouse postings that match.

**Start with `dry_run: true`** — it logs what it would submit without
actually sending. Once you're happy with the matches, flip it off.

Greenhouse postings with custom required questions (work auth dropdowns,
"why this role?" text fields, etc.) will reject the bare submission; the bot
falls back to just emailing you the link for those. Lever and Ashby
applications go through their own forms with custom fields per posting, so
those are notify-only.

## Configuration

See `config.example.yaml`. Important fields:

- `search.keywords` / `exclude_keywords` — phrases that must (or must not)
  appear in title or description.
- `search.locations` — filter by location string (e.g. "remote", "nyc").
- `sources.<name>.boards` / `companies` — board slugs to pull from.
- `profile.resume_path` — path to your PDF resume.
- `auto_apply.enabled` / `dry_run` — off by default.

## Layout

```
bot/
  main.py          # entry point
  config.py        # YAML loader + Job dataclass
  storage.py       # SQLite dedupe
  matcher.py       # keyword/location scoring
  notifier.py      # SMTP email
  sources/         # one file per API
  applier/         # auto-submit logic
```

Each source is a class with a `fetch() -> list[Job]` method. Add a new file
under `bot/sources/`, register it in `bot/sources/__init__.py`, and the main
loop picks it up.
