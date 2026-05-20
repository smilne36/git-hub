import requests

from .config import Job


def _job_embed(job: Job, sc: int, applied: bool) -> dict:
    desc = (job.description or "").strip()
    if len(desc) > 300:
        desc = desc[:297] + "..."
    footer = f"via {job.source} · score {sc}"
    if applied:
        footer += " · auto-applied"
    return {
        "title": (job.title or "Untitled role")[:256],
        "url": job.url,
        "description": desc,
        "color": 0x57F287 if applied else 0x5865F2,
        "fields": [
            {"name": "Company", "value": job.company or "?", "inline": True},
            {"name": "Location", "value": job.location or "?", "inline": True},
        ],
        "footer": {"text": footer},
    }


def send_discord(webhook_url: str, jobs: list[tuple[Job, int, bool]]) -> None:
    """Post matches to a Discord webhook. Splits into chunks of 10 embeds."""
    for i in range(0, len(jobs), 10):
        chunk = jobs[i:i + 10]
        payload = {
            "embeds": [_job_embed(job, sc, applied) for job, sc, applied in chunk],
        }
        if i == 0:
            payload["content"] = f"**{len(jobs)} new job match{'es' if len(jobs) != 1 else ''}**"
        r = requests.post(webhook_url, json=payload, timeout=15)
        if r.status_code >= 400:
            print(f"[discord] webhook failed {r.status_code}: {r.text[:200]}")
            return
