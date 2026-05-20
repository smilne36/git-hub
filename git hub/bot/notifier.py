import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .config import Job


def render_html(jobs: list[tuple[Job, int, bool]]) -> str:
    """jobs is a list of (job, score, applied) tuples."""
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
