"""Claude API fit-scorer.

Sends each candidate posting to Claude and returns a 1-10 fit score
plus a one-line reason. Cached per-job in seen_jobs.db so re-runs
don't re-score.

Reads ANTHROPIC_API_KEY from the environment. If missing, `AIScorer`
is a no-op (returns (None, None)) — the bot continues without scoring.
"""
from __future__ import annotations

import json
import os
import re

try:
    import anthropic
    _SDK_OK = True
except ImportError:  # anthropic not installed
    anthropic = None  # type: ignore[assignment]
    _SDK_OK = False

from .config import Job


_MAX_JD_CHARS = 3000  # keep tokens small; Haiku input is cheap but tight

_SYSTEM_PROMPT = (
    "You rate whether a job posting fits a candidate's profile. Return ONLY a "
    "JSON object with fields: score (integer 1-10), reason (short string, at "
    "most 90 characters). No prose, no markdown, no code fences."
)

_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


class AIScorer:
    """Wraps a Claude call that returns (score, one-line reason) per job."""

    def __init__(
        self,
        bio: str,
        model: str = "claude-haiku-4-5",
        api_key: str | None = None,
    ):
        self.bio = bio.strip()
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None
        if _SDK_OK and self.api_key:
            self._client = anthropic.Anthropic(api_key=self.api_key)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def score(self, job: Job) -> tuple[int | None, str | None]:
        if not self._client:
            return (None, None)

        jd = (job.description or "").strip()
        if len(jd) > _MAX_JD_CHARS:
            jd = jd[:_MAX_JD_CHARS] + "\n\n[...truncated]"

        user_text = (
            f"CANDIDATE PROFILE:\n{self.bio}\n\n"
            f"JOB POSTING:\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location or 'unspecified'}\n"
            f"Description:\n{jd}\n\n"
            "Rate 1-10 fit for this candidate."
        )

        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=200,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_text}],
            )
        except Exception as e:
            print(f"[ai_score] {job.id}: {type(e).__name__}: {e}")
            return (None, None)

        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()
        return _parse_score(text)


def _parse_score(text: str) -> tuple[int | None, str | None]:
    """Extract {score, reason} from a Claude response. Tolerates fences."""
    m = _JSON_RE.search(text)
    if not m:
        return (None, None)
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return (None, None)
    score = obj.get("score")
    reason = obj.get("reason")
    if not isinstance(score, int) or not (1 <= score <= 10):
        return (None, None)
    if not isinstance(reason, str):
        reason = None
    return (score, (reason or "")[:200])
