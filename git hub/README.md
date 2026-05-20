# Job Search Bot

A Python bot that searches for jobs across public APIs, pings a Discord
channel when matches are found, and can auto-submit applications on
Greenhouse using a stored resume.

## Sources (all public APIs)

| Source     | Endpoint                                                | What it covers                                |
|------------|---------------------------------------------------------|-----------------------------------------------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/<slug>/jobs`        | Any company hosted on Greenhouse              |
| Lever      | `api.lever.co/v0/postings/<slug>`                       | Any company hosted on Lever                   |
| Ashby      | `api.ashbyhq.com/posting-api/job-board/<slug>`          | Any company hosted on Ashby                   |
| RemoteOK   | `remoteok.com/api`                                      | Remote jobs aggregator                        |
| Adzuna     | `api.adzuna.com` (needs free API key)                   | Indeed-style aggregated listings              |

You give it a list of company board slugs (e.g. `airbnb`, `stripe`, `figma`)
and it pulls every open role from each.

## Setup

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml — discord webhook, keywords, board slugs, resume path
python -m bot.main
```

Run it on a schedule (cron, Windows Task Scheduler, GitHub Actions). It
dedupes via SQLite so you only get pinged once per job.

## Discord setup

1. In your server: right-click the channel you want pings in → **Edit
   Channel** → **Integrations** → **Webhooks** → **New Webhook**
2. Click **Copy Webhook URL**
3. Paste it into `config.yaml`:
   ```yaml
   discord:
     webhook_url: "https://discord.com/api/webhooks/..."
   ```
4. Run `python -m bot.main`. Matches show up as rich embeds with title,
   company, location, score, and a clickable link.

> **Keep the webhook URL private.** Anyone who has it can post messages to
> your channel. `config.yaml` is gitignored so it won't be committed.

## Auto-apply

Set `auto_apply.enabled: true` in `config.yaml` and the bot will POST your
resume + basic info to Greenhouse postings that match.

**Start with `dry_run: true`** (the default) — it logs what it *would*
submit without actually sending. Once you're happy, flip it off.

Greenhouse postings with custom required questions will reject the bare
submission and fall back to notify-only. Lever and Ashby applications go
through their own forms with custom fields, so those are notify-only too.

## Layout

```
bot/
  main.py          # entry point
  config.py        # YAML loader + Job dataclass
  storage.py       # SQLite dedupe
  matcher.py       # keyword/location scoring
  notifier.py      # Discord webhook
  sources/         # one file per API
  applier/         # auto-submit logic
```
