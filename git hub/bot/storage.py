import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SeenStore:
    """SQLite-backed job store: dedupe + AI score cache + application tracker."""

    def __init__(self, path: str | Path = "seen_jobs.db"):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            " id TEXT PRIMARY KEY,"
            " source TEXT,"
            " applied INTEGER DEFAULT 0,"
            " first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        # additive columns — safe on existing DBs
        self._add_column_if_missing("seen", "ai_score", "INTEGER")
        self._add_column_if_missing("seen", "ai_reason", "TEXT")
        self._add_column_if_missing("seen", "url", "TEXT")
        self._add_column_if_missing("seen", "title", "TEXT")
        self._add_column_if_missing("seen", "company", "TEXT")
        self._add_column_if_missing("seen", "location", "TEXT")
        # interest: -1 = passed, 0 = untriaged, 1 = interested, 2 = applied
        self._add_column_if_missing("seen", "interest", "INTEGER DEFAULT 0")
        self._add_column_if_missing("seen", "applied_at", "TIMESTAMP")
        self._add_column_if_missing("seen", "follow_up_sent_at", "TIMESTAMP")
        self.conn.commit()

    def _add_column_if_missing(self, table: str, col: str, decl: str) -> None:
        cols = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    # ------- dedupe -------
    def has(self, job_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM seen WHERE id = ?", (job_id,)).fetchone()
        return row is not None

    def add(
        self,
        job_id: str,
        source: str,
        url: str | None = None,
        title: str | None = None,
        company: str | None = None,
        location: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen (id, source, url, title, company, location)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, source, url, title, company, location),
        )
        # Fill columns for rows added before we tracked them.
        self.conn.execute(
            "UPDATE seen SET url = COALESCE(url, ?), title = COALESCE(title, ?),"
            " company = COALESCE(company, ?), location = COALESCE(location, ?)"
            " WHERE id = ?",
            (url, title, company, location, job_id),
        )
        self.conn.commit()

    def mark_applied(self, job_id: str) -> None:
        # legacy auto-apply path
        self.set_interest(job_id, 2)

    # ------- AI score cache -------
    def get_ai_score(self, job_id: str) -> tuple[int | None, str | None]:
        row = self.conn.execute(
            "SELECT ai_score, ai_reason FROM seen WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return (None, None)
        return (row[0], row[1])

    def set_ai_score(self, job_id: str, score: int | None, reason: str | None) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen (id, source) VALUES (?, '')", (job_id,)
        )
        self.conn.execute(
            "UPDATE seen SET ai_score = ?, ai_reason = ? WHERE id = ?",
            (score, reason, job_id),
        )
        self.conn.commit()

    # ------- application tracker -------
    def find_by_ref(self, ref: str) -> str | None:
        """Return job id given a URL, URL substring, or exact id."""
        if not ref:
            return None
        row = self.conn.execute("SELECT id FROM seen WHERE id = ?", (ref,)).fetchone()
        if row:
            return row[0]
        row = self.conn.execute(
            "SELECT id FROM seen WHERE url = ? LIMIT 1", (ref,)
        ).fetchone()
        if row:
            return row[0]
        row = self.conn.execute(
            "SELECT id FROM seen WHERE url LIKE ? LIMIT 1", (f"%{ref}%",)
        ).fetchone()
        return row[0] if row else None

    def set_interest(self, job_id: str, level: int) -> None:
        # Applied stamps applied_at; re-applying does not overwrite an existing stamp.
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if level == 2:
            self.conn.execute(
                "UPDATE seen SET interest = 2, applied = 1,"
                " applied_at = COALESCE(applied_at, ?) WHERE id = ?",
                (now, job_id),
            )
        else:
            self.conn.execute(
                "UPDATE seen SET interest = ? WHERE id = ?", (level, job_id)
            )
        self.conn.commit()

    def get_row(self, job_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, source, url, title, company, location, interest,"
            " applied_at, follow_up_sent_at, ai_score, ai_reason"
            " FROM seen WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        keys = [
            "id", "source", "url", "title", "company", "location",
            "interest", "applied_at", "follow_up_sent_at", "ai_score", "ai_reason",
        ]
        return dict(zip(keys, row))

    def list_applied(self, limit: int = 50) -> list[dict]:
        return self._rows_where(
            "interest = 2 ORDER BY applied_at DESC LIMIT ?", (limit,)
        )

    def list_pending_follow_up(self, days: int = 14) -> list[dict]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat(timespec="seconds")
        return self._rows_where(
            "interest = 2 AND applied_at IS NOT NULL AND applied_at <= ?"
            " AND follow_up_sent_at IS NULL ORDER BY applied_at ASC",
            (cutoff,),
        )

    def mark_follow_up_sent(self, job_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE seen SET follow_up_sent_at = ? WHERE id = ?", (now, job_id)
        )
        self.conn.commit()

    def counts_since(self, since_iso: str) -> dict[str, int]:
        row = self.conn.execute(
            "SELECT"
            "  SUM(CASE WHEN first_seen >= ? THEN 1 ELSE 0 END),"
            "  SUM(CASE WHEN applied_at >= ? THEN 1 ELSE 0 END),"
            "  SUM(CASE WHEN first_seen >= ? AND ai_score >= 8 THEN 1 ELSE 0 END)"
            " FROM seen",
            (since_iso, since_iso, since_iso),
        ).fetchone()
        return {
            "new_jobs": row[0] or 0,
            "applied": row[1] or 0,
            "strong_matches": row[2] or 0,
        }

    def top_matches_since(self, since_iso: str, limit: int = 5) -> list[dict]:
        return self._rows_where(
            "first_seen >= ? AND (ai_score IS NOT NULL OR interest > 0)"
            " ORDER BY COALESCE(ai_score, 0) DESC, first_seen DESC LIMIT ?",
            (since_iso, limit),
        )

    def _rows_where(self, where: str, params: tuple) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, source, url, title, company, location, interest,"
            " applied_at, follow_up_sent_at, ai_score, ai_reason"
            f" FROM seen WHERE {where}",
            params,
        ).fetchall()
        keys = [
            "id", "source", "url", "title", "company", "location",
            "interest", "applied_at", "follow_up_sent_at", "ai_score", "ai_reason",
        ]
        return [dict(zip(keys, r)) for r in rows]
