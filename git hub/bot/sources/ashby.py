import requests
from .base import Source
from ..config import Job


class Ashby(Source):
    """Public Ashby job board API.

    Endpoint: GET https://api.ashbyhq.com/posting-api/job-board/{slug}
    """

    name = "ashby"

    def __init__(self, companies: list[str]):
        self.companies = companies

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for slug in self.companies:
            url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
            try:
                r = requests.get(url, timeout=20)
                r.raise_for_status()
            except requests.RequestException as e:
                print(f"[ashby] {slug} failed: {e}")
                continue
            for j in r.json().get("jobs", []):
                jid = j.get("id")
                jobs.append(Job(
                    id=f"ashby:{slug}:{jid}",
                    source=self.name,
                    title=j.get("title", ""),
                    company=slug,
                    location=j.get("location", "") or "",
                    url=j.get("jobUrl", ""),
                    description=j.get("descriptionPlain", "") or "",
                    apply_url=j.get("applyUrl", "") or j.get("jobUrl", ""),
                ))
        return jobs
