"""
SQLite-backed store for prompt snapshots and golden outputs.
Everything lives in .prompt-sentinel/ — zero external infra.
"""

import sqlite3
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class GoldenRecord:
    id: int
    name: str
    prompt_sha: str
    prompt_text: str
    input_text: str
    golden_output: str
    model: str
    recorded_at: str
    meta: dict


@dataclass
class RunRecord:
    id: int
    name: str
    prompt_sha: str
    prompt_text: str
    input_text: str
    actual_output: str
    model: str
    passed: bool
    score: float
    failure_reasons: list[str]
    ran_at: str
    meta: dict


class Store:
    def __init__(self, root: str = "."):
        self.dir = Path(root) / ".prompt-sentinel"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "db.sqlite"
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS goldens (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    name          TEXT NOT NULL,
                    prompt_sha    TEXT NOT NULL,
                    prompt_text   TEXT NOT NULL,
                    input_text    TEXT NOT NULL,
                    golden_output TEXT NOT NULL,
                    model         TEXT NOT NULL,
                    recorded_at   TEXT NOT NULL,
                    meta          TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT NOT NULL,
                    prompt_sha      TEXT NOT NULL,
                    prompt_text     TEXT NOT NULL,
                    input_text      TEXT NOT NULL,
                    actual_output   TEXT NOT NULL,
                    model           TEXT NOT NULL,
                    passed          INTEGER NOT NULL,
                    score           REAL NOT NULL,
                    failure_reasons TEXT NOT NULL,
                    ran_at          TEXT NOT NULL,
                    meta            TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_goldens_name ON goldens(name);
                CREATE INDEX IF NOT EXISTS idx_runs_name    ON runs(name);
            """)

    # ── Goldens ──────────────────────────────────────────────────────────────

    def save_golden(
        self,
        name: str,
        prompt_text: str,
        input_text: str,
        golden_output: str,
        model: str,
        meta: Optional[dict] = None,
    ) -> str:
        sha = _sha256(prompt_text)
        with self._conn() as conn:
            # Replace existing golden for same name + input
            conn.execute(
                """DELETE FROM goldens WHERE name = ? AND input_text = ?""",
                (name, input_text),
            )
            conn.execute(
                """INSERT INTO goldens
                   (name, prompt_sha, prompt_text, input_text, golden_output, model, recorded_at, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, sha, prompt_text, input_text, golden_output, model,
                 _now(), json.dumps(meta or {})),
            )
        return sha

    def get_goldens(self, name: str) -> list[GoldenRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM goldens WHERE name = ? ORDER BY recorded_at DESC",
                (name,)
            ).fetchall()
        return [self._row_to_golden(r) for r in rows]

    def get_golden(self, name: str, input_text: str) -> Optional[GoldenRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM goldens WHERE name = ? AND input_text = ? ORDER BY recorded_at DESC LIMIT 1",
                (name, input_text)
            ).fetchone()
        return self._row_to_golden(row) if row else None

    def list_names(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT name FROM goldens ORDER BY name"
            ).fetchall()
        return [r["name"] for r in rows]

    # ── Runs ─────────────────────────────────────────────────────────────────

    def save_run(
        self,
        name: str,
        prompt_text: str,
        input_text: str,
        actual_output: str,
        model: str,
        passed: bool,
        score: float,
        failure_reasons: list[str],
        meta: Optional[dict] = None,
    ):
        sha = _sha256(prompt_text)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO runs
                   (name, prompt_sha, prompt_text, input_text, actual_output,
                    model, passed, score, failure_reasons, ran_at, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, sha, prompt_text, input_text, actual_output, model,
                 int(passed), score, json.dumps(failure_reasons),
                 _now(), json.dumps(meta or {})),
            )

    def get_last_run(self, name: str, input_text: str) -> Optional[RunRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE name = ? AND input_text = ? ORDER BY ran_at DESC LIMIT 1",
                (name, input_text)
            ).fetchone()
        return self._row_to_run(row) if row else None

    def get_runs(self, name: str, limit: int = 20) -> list[RunRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE name = ? ORDER BY ran_at DESC LIMIT ?",
                (name, limit)
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _row_to_golden(self, row) -> GoldenRecord:
        return GoldenRecord(
            id=row["id"], name=row["name"], prompt_sha=row["prompt_sha"],
            prompt_text=row["prompt_text"], input_text=row["input_text"],
            golden_output=row["golden_output"], model=row["model"],
            recorded_at=row["recorded_at"], meta=json.loads(row["meta"]),
        )

    def _row_to_run(self, row) -> RunRecord:
        return RunRecord(
            id=row["id"], name=row["name"], prompt_sha=row["prompt_sha"],
            prompt_text=row["prompt_text"], input_text=row["input_text"],
            actual_output=row["actual_output"], model=row["model"],
            passed=bool(row["passed"]), score=row["score"],
            failure_reasons=json.loads(row["failure_reasons"]),
            ran_at=row["ran_at"], meta=json.loads(row["meta"]),
        )
