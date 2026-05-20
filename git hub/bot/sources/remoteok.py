import requests
from .base import Source
from ..config import Job


class RemoteOK(Source):
    name = "remoteok"
    URL = "https://remoteok.com/api"

    def fetch(self) -> list[Job]:
        r = requests.get(self.URL, headers={"User-Agent": "job-bot/1.0"}, timeout=20)
        r.raise_for_status()
        data = r.json()
        # First element is metadata; rest are jobs.
        jobs = []
        for item in data[1:] if data and isinstance(data[0], dict) and "legal" in data[0] else data:
            jid = str(item.get("id") or item.get("slug") or item.get("url"))
            jobs.append(Job(
                id=f"remoteok:{jid}",
                source=self.name,
                title=item.get("position") or item.get("title", ""),
                company=item.get("company", ""),
                location=item.get("location") or "Remote",
                url=item.get("url", ""),
                description=item.get("description", "") or "",
                apply_url=item.get("apply_url", "") or item.get("url", ""),
            ))
        return jobs
