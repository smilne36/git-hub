import requests

from .config import Job


def _color_for(ai_score, applied: bool) -> int:
    if applied:
        return 0x57F287  # green
    if ai_score is None:
        return 0x5865F2  # blurple (no AI score)
    if ai_score >= 8:
        return 0x2ECC71  # bright green — strong fit
    if ai_score >= 6:
        return 0x3498DB  # blue — decent fit
    if ai_score >= 4:
        return 0xF1C40F  # yellow — marginal
    return 0x95A5A6  # gray — weak


def _job_embed(job: Job, sc: int, applied: bool, ai_score, ai_reason) -> dict:
    desc = (job.description or "").strip()
    if len(desc) > 300:
        desc = desc[:297] + "..."

    prefix = f"[AI {ai_score}/10] " if ai_score is not None else ""
    title = (prefix + (job.title or "Untitled role"))[:256]

    footer_parts = [f"via {job.source}", f"kw {sc}"]
    if ai_score is not None:
        footer_parts.append(f"ai {ai_score}")
    if applied:
        footer_parts.append("auto-applied")
    footer = " · ".join(footer_parts)

    fields = [
        {"name": "Company", "value": (job.company or "?")[:60], "inline": True},
        {"name": "Location", "value": (job.location or "?")[:60], "inline": True},
    ]
    if ai_reason:
        fields.append({"name": "AI take", "value": ai_reason[:150], "inline": False})

    return {
        "title": title,
        "url": job.url,
        "description": desc,
        "color": _color_for(ai_score, applied),
        "fields": fields,
        "footer": {"text": footer},
    }


def send_discord(webhook_url: str, jobs) -> None:
    """Post matches to a Discord webhook. Splits into chunks of 10 embeds.

    Each entry is (job, keyword_score, applied, ai_score, ai_reason).
    Legacy 3-tuple entries still work (AI fields default to None).
    """
    normalized = []
    for entry in jobs:
        if len(entry) == 3:
            job, sc, applied = entry
            normalized.append((job, sc, applied, None, None))
        else:
            normalized.append(entry)

    for i in range(0, len(normalized), 10):
        chunk = normalized[i:i + 10]
        payload = {
            "embeds": [_job_embed(j, s, a, ai, r) for j, s, a, ai, r in chunk],
        }
        if i == 0:
            n = len(normalized)
            payload["content"] = f"**{n} new job match{'es' if n != 1 else ''}**"
        r = requests.post(webhook_url, json=payload, timeout=15)
        if r.status_code >= 400:
            print(f"[discord] webhook failed {r.status_code}: {r.text[:200]}")
            return
