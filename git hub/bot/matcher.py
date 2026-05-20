from .config import Job


def score(job: Job, keywords: list[str], exclude: list[str], locations: list[str]) -> int:
    """Return a positive score for matching jobs, or 0 for non-matches.

    Score = number of keyword hits across title + description.
    Excludes are matched against the TITLE only, so a junior posting that
    mentions "work alongside senior engineers" in the body still passes.
    """
    title = (job.title or "").lower()
    text = f"{job.title} {job.description} {job.location}".lower()

    for bad in exclude:
        if bad.lower() in title:
            return 0

    if locations:
        loc_text = job.location.lower()
        if not any(loc.lower() in loc_text or loc.lower() in text for loc in locations):
            return 0

    return sum(1 for kw in keywords if kw.lower() in text)
