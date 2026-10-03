"""Write the ranked list as a terminal table, CSV, JSON and an HTML page with players."""
from __future__ import annotations

import csv
import html
import json
import os
from pathlib import Path

from .analyze import TrackAnalysis
from .match import Match


def describe(t: TrackAnalysis) -> str:
    return (f"{t.title}\n  {t.bpm:.1f} BPM | key {t.key} ({t.camelot}) | "
            f"intro: {t.intro_type} | outro: {t.outro_type} | {t.duration / 60:.1f} min")


def table(title: str, matches: list[Match], other: str) -> str:
    lines = [title, "-" * len(title)]
    for i, m in enumerate(matches, 1):
        t = getattr(m, other)
        lines.append(f"{i:>2}. {m.score:5.1f}  {t.title}  [{t.source}]")
        lines += [f"           {r}" for r in m.reasons]
        if m.preview:
            lines.append(f"           preview: {m.preview}")
    return "\n".join(lines) if matches else f"{title}\n  (no candidates)"


def _row(direction: str, rank: int, m: Match, other: str) -> dict:
    t = getattr(m, other)
    p = m.plan
    return {
        "direction": direction, "rank": rank, "score": m.score, "title": t.title,
        "source": t.source, "path": t.path, "bpm": round(t.bpm, 1), "key": t.key,
        "camelot": t.camelot, "style": p.style, "bars": p.bars,
        "stretch_pct": round(100 * (p.rate - 1), 2),
        "mix_out_at": round(p.out_start, 2), "mix_in_at": round(p.in_start, 2),
        **{f"score_{k}": v for k, v in m.parts.items()},
        "reasons": " | ".join(m.reasons), "preview": m.preview or "",
    }


def write(out: Path, song: TrackAnalysis, before: list[Match], after: list[Match]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = ([_row("before", i, m, "outgoing") for i, m in enumerate(before, 1)]
            + [_row("after", i, m, "incoming") for i, m in enumerate(after, 1)])
    (out / "results.json").write_text(json.dumps({"song": song.to_dict(), "matches": rows}, indent=2))
    if rows:
        with open(out / "results.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    (out / "report.html").write_text(_html(out, song, rows))


def _html(out: Path, song: TrackAnalysis, rows: list[dict]) -> str:
    def section(direction: str, heading: str) -> str:
        items = []
        for r in (r for r in rows if r["direction"] == direction):
            audio = ""
            if r["preview"]:
                rel = os.path.relpath(r["preview"], out)
                audio = f'<audio controls preload="none" src="{html.escape(rel)}"></audio>'
            reasons = "".join(f"<li>{html.escape(x)}</li>" for x in r["reasons"].split(" | "))
            items.append(
                f'<div class="card"><div class="top"><span class="score">{r["score"]:.0f}</span>'
                f'<div><b>{html.escape(r["title"])}</b><div class="meta">{r["bpm"]} BPM · '
                f'{html.escape(r["key"])} ({r["camelot"]}) · {r["source"]}</div></div></div>'
                f"<ul>{reasons}</ul>{audio}</div>")
        return f"<h2>{heading}</h2>" + ("".join(items) or "<p>No candidates.</p>")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Transitions: {html.escape(song.title)}</title>
<style>
:root{{--bg:#fafafa;--fg:#111;--card:#fff;--muted:#666;--accent:#6b4ce6;--line:#e4e4e4}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--card:#1b1b1b;--muted:#999;--accent:#a08bff;--line:#2a2a2a}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:760px;margin:0 auto;padding:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}}
.top{{display:flex;gap:12px;align-items:center}}.score{{font-size:22px;font-weight:700;color:var(--accent);min-width:2.2em}}
.meta{{color:var(--muted);font-size:13px}}ul{{margin:8px 0;padding-left:20px;font-size:13px}}audio{{width:100%}}
</style></head><body>
<h1>{html.escape(song.title)}</h1>
<p class="meta">{song.bpm:.1f} BPM · {html.escape(song.key)} ({song.camelot}) · intro {song.intro_type} · outro {song.outro_type}</p>
{section("before", "Play before (mixes into your song)")}
{section("after", "Play after (your song mixes into it)")}
</body></html>"""
