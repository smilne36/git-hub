# Job Search Bot

A Python bot that hunts C++ / game-dev / engine roles across public
job APIs, has Claude read each posting for fit, and pings Discord with
ranked matches. Runs hourly on GitHub Actions; posts a nightly digest.

## Sources

| Source     | Endpoint                                                        | What it covers                              |
|------------|-----------------------------------------------------------------|---------------------------------------------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/<slug>/jobs`                | Any company hosted on Greenhouse            |
| Lever      | `api.lever.co/v0/postings/<slug>`                               | Any company hosted on Lever                 |
| Ashby      | `api.ashbyhq.com/posting-api/job-board/<slug>`                  | Any company hosted on Ashby                 |
| RemoteOK   | `remoteok.com/api`                                              | Remote jobs aggregator                      |
| HackerNews | `hn.algolia.com` — "Ask HN: Who is hiring?" (monthly, 1st)      | Small studios/engine shops off big-ATS      |
| Adzuna     | `api.adzuna.com` (needs free API key)                           | Indeed-style aggregated listings            |

## What the bot does each run

1. **Fetches** from every enabled source
2. **Keyword-filters** — a job must contain at least one `required_keywords` term
   (c++, opengl, shader, gameplay, game engine, unreal engine …) and no
   `exclude_keywords` term in its title (senior, staff, artist, marketing …)
3. **AI-scores** matches with Claude — each posting gets a 1-10 fit rating
   and a one-line reason, weighted against your `candidate_bio`. Results are
   cached in `seen_jobs.db` so re-runs don't re-score
4. **Posts to Discord** as rich embeds sorted by AI score, color-coded from
   gray (weak) → green (strong)
5. **Dedupes** every job it's already seen

## Setup

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml — discord webhook, keywords, studios, candidate_bio
export ANTHROPIC_API_KEY=sk-ant-...    # optional — enables AI scoring
python -m bot.main
```

## GitHub Actions (hourly)

Two workflows:
- `.github/workflows/jobsearch.yml` — runs `bot.main` hourly at `:07`
- `.github/workflows/digest.yml`   — posts nightly digest at `00:07 UTC`

Required repo secrets:
- `DISCORD_WEBHOOK_URL` — your channel's webhook
- `ANTHROPIC_API_KEY`  — optional; enables AI fit-scoring

Both workflows generate `config.yaml` from `config.example.yaml` +
secrets, then commit `seen_jobs.db` back so dedupe / AI-score cache /
application state persists across runs.

## Application tracker (`bot.applied`)

Discord webhooks can't read reactions, so triage happens via CLI:

```bash
python -m bot.applied apply    https://boards.greenhouse.io/roblox/jobs/12345
python -m bot.applied like     <url_or_id>
python -m bot.applied pass     <url_or_id>
python -m bot.applied list                 # 20 most recent applied
python -m bot.applied pending              # follow-ups due (≥ 14 days)
```

The nightly digest surfaces jobs you applied to ≥ 14 days ago so you
know when to nudge the recruiter.

To have local application state flow into the workflow's digest, pull
before / push after:

```bash
git pull && python -m bot.applied apply <url> \
    && git add seen_jobs.db && git commit -m "applied to X" && git push
```

## Auto-apply (`bot.autoapply`) — local, human-in-the-loop

Runs on your machine, so your resume stays local. Only fires against
strong AI-scored matches and asks you to confirm each one:

```bash
python -m bot.autoapply                       # min AI score 8, confirm each
python -m bot.autoapply --min-score 9         # raise the bar
python -m bot.autoapply --dry-run --yes       # simulate everything
python -m bot.autoapply <url_or_id>           # apply to one specific job
python -m bot.autoapply --yes                 # yolo — skip confirms
```

Requirements:
- `profile.full_name`, `email`, `phone`, `resume_path` set in config.yaml
- The file at `resume_path` exists locally (a PDF)

Only Greenhouse jobs can be submitted this way (Lever/Ashby have
per-form custom fields, so those stay notify-only). Postings with
custom required questions get rejected by the API — the CLI reports
that and moves on.

After submitting, commit `seen_jobs.db` so the hourly workflow
doesn't re-notify or re-consider those roles:

```bash
git add "git hub/seen_jobs.db" && git commit -m "applied" && git push
```

## Discord webhook

1. In your server: channel → **Edit Channel** → **Integrations** →
   **Webhooks** → **New Webhook** → **Copy URL**
2. Paste into `config.yaml` under `discord.webhook_url`, or add as the
   `DISCORD_WEBHOOK_URL` repo secret

> Keep the webhook URL private. `config.yaml` is gitignored.

## Layout

```
bot/
  main.py          # entry: fetch → filter → AI score → post to Discord
  digest.py        # nightly summary (new roles, follow-ups due)
  applied.py       # CLI: mark apply / like / pass / list / pending
  autoapply.py     # CLI: submit resume to strong Greenhouse matches
  ai_score.py      # Claude Haiku fit-scoring
  config.py        # YAML loader + Job dataclass
  storage.py       # SQLite dedupe + AI cache + tracker
  matcher.py       # keyword/location scoring
  notifier.py      # Discord webhook embeds
  ping.py          # webhook smoke test
  preview.py       # dry-run: fetch+score without posting
  sources/         # one file per API
  applier/         # auto-submit logic
```
