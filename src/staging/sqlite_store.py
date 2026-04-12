"""SQLite-backed staging queue for pending approval updates."""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List

from src.models.ontology import ProposedUpdate

DB_PATH = Path(__file__).parent.parent.parent / "data" / "staging.db"


class StagingStore:
    def __init__(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proposals (
                batch_id TEXT PRIMARY KEY,
                payload  TEXT NOT NULL,
                status   TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            )
            """
        )
        self._conn.commit()

    def enqueue(self, update: ProposedUpdate) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO proposals (batch_id, payload, status, created_at) VALUES (?, ?, 'pending', ?)",
            (update.batch_id, update.model_dump_json(), datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def get_pending(self) -> List[ProposedUpdate]:
        rows = self._conn.execute(
            "SELECT payload FROM proposals WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [ProposedUpdate.model_validate_json(row[0]) for row in rows]

    def mark_approved(self, batch_id: str) -> None:
        self._conn.execute(
            "UPDATE proposals SET status='approved', reviewed_at=? WHERE batch_id=?",
            (datetime.utcnow().isoformat(), batch_id),
        )
        self._conn.commit()

    def mark_rejected(self, batch_id: str) -> None:
        self._conn.execute(
            "UPDATE proposals SET status='rejected', reviewed_at=? WHERE batch_id=?",
            (datetime.utcnow().isoformat(), batch_id),
        )
        self._conn.commit()

    def count_pending(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM proposals WHERE status='pending'"
        ).fetchone()[0]
