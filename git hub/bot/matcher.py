from .config import Job


def score(job: Job, keywords: list[str], exclude: list[str], locations: list[str]) -> int:
    """Return a positive score for matching jobs, or 0/negative for non-matches.

    Score = number of keyword hits in title/description.
    Returns 0 if any exclude keyword matches, or if location filter is set
    and the job's location doesn't match any allowed location.
    """
    text = f"{job.title} {job.description} {job.location}".lower()

    for bad in exclude:
        if bad.lower() in text:
            return 0

    if locations:
        loc_text = job.location.lower()
        if not any(loc.lower() in loc_text or loc.lower() in text for loc in locations):
            return 0

    return sum(1 for kw in keywords if kw.lower() in text)
