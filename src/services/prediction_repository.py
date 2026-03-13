from __future__ import annotations

import base64
import os
import sqlite3
from typing import Any


class PredictionRepository:
    def __init__(self, db_path: str = "data/intel.db"):
        self.db_path = db_path
        self._db: sqlite3.Connection | None = None

        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self) -> None:
        if self._db is not None:
            return
        self._db = sqlite3.connect(self.db_path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id TEXT PRIMARY KEY,
                asset_symbol TEXT,
                prediction_type TEXT,
                reasoning TEXT,
                base_price REAL,
                base_timestamp DATETIME,
                status TEXT DEFAULT 'pending',
                score REAL,
                actual_price REAL,
                scored_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._db.commit()

    async def close(self) -> None:
        if self._db is None:
            return
        self._db.close()
        self._db = None

    async def save_prediction(self, data: dict[str, Any]) -> str:
        db = await self._require_db()
        prediction_id = base64.b64encode(
            f"{data['asset']}-{data['timestamp']}".encode()
        ).decode()
        db.execute(
            """INSERT OR REPLACE INTO predictions
               (id, asset_symbol, prediction_type, reasoning, base_price, base_timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                prediction_id,
                data["asset"],
                data["type"],
                data["reasoning"],
                data["price"],
                data["timestamp"],
            ),
        )
        db.commit()
        return prediction_id

    async def get_pending_predictions(self) -> list[dict[str, Any]]:
        return await self._fetch_all(
            "SELECT * FROM predictions WHERE status = 'pending' ORDER BY created_at ASC"
        )

    async def update_prediction_score(
        self, prediction_id: str, score: float, actual_price: float
    ) -> None:
        db = await self._require_db()
        db.execute(
            """UPDATE predictions
               SET score = ?, actual_price = ?, status = 'scored', scored_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (score, actual_price, prediction_id),
        )
        db.commit()

    async def list_predictions(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self._fetch_all(
            "SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    async def get_prediction(self, prediction_id: str) -> dict[str, Any] | None:
        db = await self._require_db()
        cursor = db.execute(
            "SELECT * FROM predictions WHERE id = ?",
            (prediction_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return dict(row) if row is not None else None

    async def _fetch_all(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        db = await self._require_db()
        cursor = db.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        return [dict(row) for row in rows]

    async def _require_db(self) -> sqlite3.Connection:
        if self._db is None:
            await self.connect()
        assert self._db is not None
        return self._db


__all__ = ["PredictionRepository"]
