import requests
from .base import Source
from ..config import Job


class Adzuna(Source):
    """Adzuna search API (covers Indeed-style listings legally).

    Sign up at https://developer.adzuna.com for app_id + app_key.
    """

    name = "adzuna"

    def __init__(self, app_id: str, app_key: str, country: str = "us"):
        self.app_id = app_id
        self.app_key = app_key
        self.country = country

    def fetch(self, query: str = "software engineer", page: int = 1) -> list[Job]:
        url = f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/{page}"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": 50,
            "what": query,
            "content-type": "application/json",
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[adzuna] failed: {e}")
            return []
        jobs = []
        for j in r.json().get("results", []):
            jid = j.get("id")
            jobs.append(Job(
                id=f"adzuna:{jid}",
                source=self.name,
                title=j.get("title", ""),
                company=(j.get("company") or {}).get("display_name", ""),
                location=(j.get("location") or {}).get("display_name", ""),
                url=j.get("redirect_url", ""),
                description=j.get("description", "") or "",
                apply_url=j.get("redirect_url", ""),
            ))
        return jobs
