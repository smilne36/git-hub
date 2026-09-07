"""HackerNews 'Ask HN: Who is hiring?' source.

Every 1st of the month the `whoishiring` account posts a thread where
companies post one top-level comment per open role. Uses the public
Algolia HN Search API (no key required):

    story lookup:  https://hn.algolia.com/api/v1/search?tags=story,author_whoishiring&query=hiring
    thread items:  https://hn.algolia.com/api/v1/items/<story_id>

Each top-level comment becomes one Job. Comment IDs are stable so
dedupe just works.
"""
import re
from html import unescape

import requests

from .base import Source
from ..config import Job


_BREAK_RE = re.compile(r"<\s*(?:br|/p|/li)\s*/?>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"^Ask HN:\s*Who is hiring\?", re.I)


def _strip_html(s: str) -> str:
    if not s:
        return ""
    # Preserve paragraph and line breaks as \n before nuking tags.
    s = _BREAK_RE.sub("\n", s)
    return unescape(_TAG_RE.sub("", s)).strip()


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _parse_company(header: str) -> str:
    # Common patterns:
    #   "Acme Corp | Senior Rust | Berlin | REMOTE"
    #   "Acme Corp - Senior Rust - Berlin (REMOTE)"
    #   "Acme Corp (YC W22) | ..."
    for sep in (" | ", " — ", " – ", " - ", ": "):
        if sep in header:
            return header.split(sep, 1)[0].strip()
    return header[:80].strip()


class HackerNews(Source):
    """Latest 'Ask HN: Who is hiring?' thread, one Job per top-level comment."""

    name = "hackernews"

    def __init__(self, max_comments: int = 500):
        self.max_comments = max_comments

    def _latest_story_id(self) -> int | None:
        url = "https://hn.algolia.com/api/v1/search"
        params = {
            "tags": "story,author_whoishiring",
            "query": "hiring",
            "hitsPerPage": 10,
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        for hit in r.json().get("hits", []):
            if _TITLE_RE.match(hit.get("title") or ""):
                return int(hit["objectID"])
        return None

    def fetch(self) -> list[Job]:
        story_id = self._latest_story_id()
        if story_id is None:
            print("[hackernews] no 'Who is hiring?' thread found")
            return []

        r = requests.get(
            f"https://hn.algolia.com/api/v1/items/{story_id}", timeout=30
        )
        r.raise_for_status()
        children = r.json().get("children", []) or []

        jobs: list[Job] = []
        for c in children[: self.max_comments]:
            if not c or c.get("author") is None:
                continue  # deleted
            text = _strip_html(c.get("text") or "")
            if not text:
                continue
            header = _first_line(text)
            company = _parse_company(header)
            cid = c.get("id")
            jobs.append(Job(
                id=f"hackernews:{cid}",
                source=self.name,
                title=header[:200],
                company=company or "unknown",
                location="",
                url=f"https://news.ycombinator.com/item?id={cid}",
                description=text,
                apply_url="",
            ))
        return jobs
