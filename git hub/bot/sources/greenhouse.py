import requests
from .base import Source
from ..config import Job


class Greenhouse(Source):
    """Public Greenhouse Job Board API.

    Docs: https://developers.greenhouse.io/job-board.html
    Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
    """

    name = "greenhouse"

    def __init__(self, boards: list[str]):
        self.boards = boards

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for slug in self.boards:
            url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
            try:
                r = requests.get(url, timeout=20)
                r.raise_for_status()
            except requests.RequestException as e:
                print(f"[greenhouse] {slug} failed: {e}")
                continue
            for j in r.json().get("jobs", []):
                jid = j.get("id")
                jobs.append(Job(
                    id=f"greenhouse:{slug}:{jid}",
                    source=self.name,
                    title=j.get("title", ""),
                    company=slug,
                    location=(j.get("location") or {}).get("name", ""),
                    url=j.get("absolute_url", ""),
                    description=j.get("content", "") or "",
                    apply_url=j.get("absolute_url", ""),
                ))
        return jobs
