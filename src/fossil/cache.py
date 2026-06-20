"""Local SQLite result cache.

Implements §3.5 of the pre-development docs:
- analysis_results table for per-file results
- scan_results table for directory scan results
- pr_cache table for GitHub/GitLab PR lookups
- schema_version for future migration support
- Auto-prune entries older than cache_ttl_hours when cache exceeds 100MB
- Corruption detection and silent rebuild
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

SCHEMA = """\
CREATE TABLE IF NOT EXISTS analysis_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_path TEXT NOT NULL,
  git_head_hash TEXT NOT NULL,
  repo_root TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  fossil_version TEXT NOT NULL,
  UNIQUE(file_path, git_head_hash, repo_root)
);
CREATE TABLE IF NOT EXISTS scan_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_root TEXT NOT NULL,
  scan_target TEXT NOT NULL,
  git_head_hash TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(repo_root, scan_target, git_head_hash)
);
CREATE TABLE IF NOT EXISTS pr_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  remote_url TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  pr_title TEXT,
  pr_body TEXT,
  merged_at TEXT,
  cached_at INTEGER NOT NULL,
  UNIQUE(remote_url, pr_number)
);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER);
"""

MAX_CACHE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_RESULT_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_TTL_HOURS = 24


class CacheStore:
    def __init__(self, repo_root: Path):
        self.path = repo_root / ".fossil" / "cache.db"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(exist_ok=True)
        try:
            conn = sqlite3.connect(self.path)
            conn.executescript(SCHEMA)
            # Set schema version if not yet set
            row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
                conn.commit()
        except sqlite3.DatabaseError:
            # Corruption detected — rebuild
            self.clear()
            conn = sqlite3.connect(self.path)
            conn.executescript(SCHEMA)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            conn.commit()
        return conn

    # ── Analysis result CRUD ──

    def get_analysis(self, file_path: Path, head: str, repo_root: Path) -> dict[str, Any] | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT result_json FROM analysis_results WHERE file_path=? AND git_head_hash=? AND repo_root=?",
                    (str(file_path), head, str(repo_root)),
                ).fetchone()
        except sqlite3.DatabaseError:
            self.clear()
            return None
        return json.loads(row[0]) if row else None

    def put_analysis(
        self, file_path: Path, head: str, repo_root: Path, version: str, result: dict[str, Any]
    ) -> None:
        payload = json.dumps(result, sort_keys=True)
        if len(payload.encode("utf-8")) > MAX_RESULT_BYTES:
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO analysis_results
                    (file_path, git_head_hash, repo_root, result_json, created_at, fossil_version)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(file_path), head, str(repo_root), payload, int(time.time()), version),
                )
        except sqlite3.DatabaseError:
            self.clear()
        self._auto_prune()

    # ── Scan result CRUD ──

    def get_scan(self, scan_target: str, head: str, repo_root: Path) -> list[dict[str, Any]] | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT result_json FROM scan_results WHERE scan_target=? AND git_head_hash=? AND repo_root=?",
                    (scan_target, head, str(repo_root)),
                ).fetchone()
        except sqlite3.DatabaseError:
            self.clear()
            return None
        return json.loads(row[0]) if row else None

    def put_scan(
        self, scan_target: str, head: str, repo_root: Path, result: list[dict[str, Any]]
    ) -> None:
        payload = json.dumps(result, sort_keys=True)
        if len(payload.encode("utf-8")) > MAX_RESULT_BYTES:
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO scan_results
                    (repo_root, scan_target, git_head_hash, result_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(repo_root), scan_target, head, payload, int(time.time())),
                )
        except sqlite3.DatabaseError:
            self.clear()

    # ── PR cache CRUD ──

    def get_pr(self, remote_url: str, pr_number: int) -> dict[str, Any] | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT pr_title, pr_body, merged_at FROM pr_cache WHERE remote_url=? AND pr_number=?",
                    (remote_url, pr_number),
                ).fetchone()
        except sqlite3.DatabaseError:
            return None
        if row is None:
            return None
        return {"pr_title": row[0], "pr_body": row[1], "merged_at": row[2]}

    def put_pr(
        self,
        remote_url: str,
        pr_number: int,
        title: str | None,
        body: str | None,
        merged_at: str | None,
    ) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pr_cache
                    (remote_url, pr_number, pr_title, pr_body, merged_at, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (remote_url, pr_number, title, body, merged_at, int(time.time())),
                )
        except sqlite3.DatabaseError:
            pass

    # ── Cache management ──

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        if not self.path.exists():
            return {"size_bytes": 0, "analysis_count": 0, "scan_count": 0, "pr_count": 0}
        try:
            size = self.path.stat().st_size
            with self._connect() as conn:
                analysis_count = conn.execute("SELECT COUNT(*) FROM analysis_results").fetchone()[0]
                scan_count = conn.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]
                pr_count = conn.execute("SELECT COUNT(*) FROM pr_cache").fetchone()[0]
            return {
                "size_bytes": size,
                "analysis_count": analysis_count,
                "scan_count": scan_count,
                "pr_count": pr_count,
            }
        except (sqlite3.DatabaseError, OSError):
            return {"size_bytes": 0, "analysis_count": 0, "scan_count": 0, "pr_count": 0}

    def _auto_prune(self, ttl_hours: int = DEFAULT_TTL_HOURS) -> None:
        """Prune old entries if cache exceeds MAX_CACHE_BYTES."""
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size < MAX_CACHE_BYTES:
                return
        except OSError:
            return
        cutoff = int(time.time()) - (ttl_hours * 3600)
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM analysis_results WHERE created_at < ?", (cutoff,))
                conn.execute("DELETE FROM scan_results WHERE created_at < ?", (cutoff,))
                conn.execute("DELETE FROM pr_cache WHERE cached_at < ?", (cutoff,))
                conn.execute("VACUUM")
        except sqlite3.DatabaseError:
            self.clear()
