import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

from .config import Job


# ---------- email ----------

def render_html(jobs: list[tuple[Job, int, bool]]) -> str:
    rows = []
    for job, sc, applied in jobs:
        badge = " <b>[auto-applied]</b>" if applied else ""
        rows.append(
            f"<li><a href='{job.url}'>{job.title}</a> — {job.company} "
            f"({job.location}) <i>via {job.source}, score {sc}</i>{badge}</li>"
        )
    return f"<html><body><h3>New job matches</h3><ul>{''.join(rows)}</ul></body></html>"


def send_email(cfg: dict, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = cfg["to_addr"]
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as s:
        s.starttls()
        s.login(cfg["username"], cfg["password"])
        s.send_message(msg)


# ---------- discord ----------

def _job_embed(job: Job, sc: int, applied: bool) -> dict:
    desc = (job.description or "").strip()
    if len(desc) > 300:
        desc = desc[:297] + "..."
    footer = f"via {job.source} · score {sc}"
    if applied:
        footer += " · auto-applied"
    return {
        "title": job.title[:256] or "Untitled role",
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
            "content": f"**{len(chunk)} new job match{'es' if len(chunk) != 1 else ''}**"
            if i == 0 else None,
            "embeds": [_job_embed(job, sc, applied) for job, sc, applied in chunk],
        }
        r = requests.post(webhook_url, json=payload, timeout=15)
        if r.status_code >= 400:
            print(f"[discord] webhook failed {r.status_code}: {r.text[:200]}")
            return
