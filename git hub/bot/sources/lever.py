import requests
from .base import Source
from ..config import Job


class Lever(Source):
    """Public Lever postings API.

    Endpoint: GET https://api.lever.co/v0/postings/{slug}?mode=json
    """

    name = "lever"

    def __init__(self, companies: list[str]):
        self.companies = companies

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for slug in self.companies:
            url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
            try:
                r = requests.get(url, timeout=20)
                r.raise_for_status()
            except requests.RequestException as e:
                print(f"[lever] {slug} failed: {e}")
                continue
            for j in r.json():
                jid = j.get("id")
                cats = j.get("categories", {}) or {}
                jobs.append(Job(
                    id=f"lever:{slug}:{jid}",
                    source=self.name,
                    title=j.get("text", ""),
                    company=slug,
                    location=cats.get("location", ""),
                    url=j.get("hostedUrl", ""),
                    description=j.get("descriptionPlain", "") or "",
                    apply_url=j.get("applyUrl", "") or j.get("hostedUrl", ""),
                ))
        return jobs
