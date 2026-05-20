import sqlite3
from pathlib import Path


class SeenStore:
    """SQLite-backed set of job IDs we've already notified the user about."""

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
        self.conn.commit()

    def has(self, job_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM seen WHERE id = ?", (job_id,)).fetchone()
        return row is not None

    def add(self, job_id: str, source: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen (id, source) VALUES (?, ?)", (job_id, source)
        )
        self.conn.commit()

    def mark_applied(self, job_id: str) -> None:
        self.conn.execute("UPDATE seen SET applied = 1 WHERE id = ?", (job_id,))
        self.conn.commit()
