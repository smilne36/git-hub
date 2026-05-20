"""Submit applications to Greenhouse-hosted job boards.

Greenhouse exposes a public job-board endpoint that accepts multipart/form-data
POSTs. The exact field names vary per posting (companies can add custom
questions), so this submits only the universally-required fields: first_name,
last_name, email, phone, and resume. Postings with extra required questions
will reject the submission and the bot will fall back to email-notify-only
for that one — you'll get the URL and can fill the rest yourself.
"""
from pathlib import Path
import requests

from ..config import Job


class GreenhouseApplier:
    name = "greenhouse"

    def __init__(self, profile: dict, dry_run: bool = True):
        self.profile = profile
        self.dry_run = dry_run

    def _parse_ids(self, job: Job) -> tuple[str, str] | None:
        # job.id looks like "greenhouse:<board>:<job_id>"
        parts = job.id.split(":")
        if len(parts) != 3:
            return None
        return parts[1], parts[2]

    def apply(self, job: Job) -> tuple[bool, str]:
        ids = self._parse_ids(job)
        if not ids:
            return False, "could not parse greenhouse ids from job"
        board, gh_job_id = ids

        first, _, last = self.profile["full_name"].partition(" ")
        resume_path = Path(self.profile["resume_path"])
        if not resume_path.exists():
            return False, f"resume not found at {resume_path}"

        url = f"https://boards.greenhouse.io/{board}/jobs/{gh_job_id}/apply"
        data = {
            "first_name": first,
            "last_name": last or first,
            "email": self.profile["email"],
            "phone": self.profile.get("phone", ""),
        }

        if self.dry_run:
            return True, f"DRY RUN — would POST to {url} with {list(data)} + resume"

        with open(resume_path, "rb") as fh:
            files = {"resume": (resume_path.name, fh, "application/pdf")}
            try:
                r = requests.post(url, data=data, files=files, timeout=30)
            except requests.RequestException as e:
                return False, f"request failed: {e}"

        if 200 <= r.status_code < 300:
            return True, f"submitted ({r.status_code})"
        return False, f"rejected ({r.status_code}): likely has custom required questions"
