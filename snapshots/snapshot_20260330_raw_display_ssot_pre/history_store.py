from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO / "data" / "history.sqlite"


def history_db_path() -> Path:
    override = os.getenv("HISTORY_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_DB_PATH


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or history_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history_records (
          id TEXT PRIMARY KEY,
          fingerprint TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL,
          topic TEXT NOT NULL,
          mode TEXT NOT NULL,
          turn_count INTEGER NOT NULL,
          fighter_a_provider TEXT NOT NULL,
          fighter_b_provider TEXT NOT NULL,
          judge_provider TEXT NOT NULL,
          fighter_a_model TEXT NOT NULL,
          fighter_b_model TEXT NOT NULL,
          judge_model TEXT NOT NULL,
          transcript_json TEXT NOT NULL,
          judge_json TEXT NOT NULL,
          output_meta TEXT NOT NULL,
          views INTEGER NOT NULL DEFAULT 0,
          likes INTEGER NOT NULL DEFAULT 0,
          record_json TEXT NOT NULL
        )
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(history_records)").fetchall()}
    if "views" not in columns:
        conn.execute("ALTER TABLE history_records ADD COLUMN views INTEGER NOT NULL DEFAULT 0")
    if "likes" not in columns:
        conn.execute("ALTER TABLE history_records ADD COLUMN likes INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def _normalize_record(record: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    normalized = dict(record or {})
    normalized.setdefault("id", f"match_{int(datetime.now(timezone.utc).timestamp() * 1000)}")
    normalized.setdefault("created_at", now)
    normalized.setdefault("topic", "")
    normalized.setdefault("mode", "casual")
    normalized.setdefault("turn_count", 5)
    normalized.setdefault("fighter_a_provider", "openai")
    normalized.setdefault("fighter_b_provider", "openai")
    normalized.setdefault("judge_provider", "gemini")
    normalized.setdefault("fighter_a_model", "")
    normalized.setdefault("fighter_b_model", "")
    normalized.setdefault("judge_model", "")
    normalized.setdefault("transcript_json", [])
    normalized.setdefault("judge_json", {})
    normalized.setdefault("output_meta", "")
    normalized.setdefault("views", 0)
    normalized.setdefault("likes", 0)
    if not normalized.get("fingerprint"):
      raise ValueError("missing fingerprint")
    return normalized


def _record_from_row(row: sqlite3.Row) -> dict:
    raw = row["record_json"]
    if raw:
        record = json.loads(raw)
        record["views"] = int(row["views"] or 0)
        record["likes"] = int(row["likes"] or 0)
        return record
    return {
        "id": row["id"],
        "fingerprint": row["fingerprint"],
        "created_at": row["created_at"],
        "topic": row["topic"],
        "mode": row["mode"],
        "turn_count": row["turn_count"],
        "fighter_a_provider": row["fighter_a_provider"],
        "fighter_b_provider": row["fighter_b_provider"],
        "judge_provider": row["judge_provider"],
        "fighter_a_model": row["fighter_a_model"],
        "fighter_b_model": row["fighter_b_model"],
        "judge_model": row["judge_model"],
        "transcript_json": json.loads(row["transcript_json"]),
        "judge_json": json.loads(row["judge_json"]),
        "output_meta": row["output_meta"],
        "views": int(row["views"] or 0),
        "likes": int(row["likes"] or 0),
    }


def save_history_record(record: dict, db_path: Path | None = None) -> dict:
    normalized = _normalize_record(record)
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM history_records WHERE fingerprint = ?",
            (normalized["fingerprint"],),
        ).fetchone()
        deduped = existing is not None
        if existing:
            normalized["id"] = existing["id"]
        payload = dict(normalized)
        transcript_json = json.dumps(payload.get("transcript_json", []), ensure_ascii=False)
        judge_json = json.dumps(payload.get("judge_json", {}), ensure_ascii=False)
        record_json = json.dumps(payload, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO history_records (
              id, fingerprint, created_at, topic, mode, turn_count,
              fighter_a_provider, fighter_b_provider, judge_provider,
              fighter_a_model, fighter_b_model, judge_model,
              transcript_json, judge_json, output_meta, views, likes, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              fingerprint=excluded.fingerprint,
              created_at=excluded.created_at,
              topic=excluded.topic,
              mode=excluded.mode,
              turn_count=excluded.turn_count,
              fighter_a_provider=excluded.fighter_a_provider,
              fighter_b_provider=excluded.fighter_b_provider,
              judge_provider=excluded.judge_provider,
              fighter_a_model=excluded.fighter_a_model,
              fighter_b_model=excluded.fighter_b_model,
              judge_model=excluded.judge_model,
              transcript_json=excluded.transcript_json,
              judge_json=excluded.judge_json,
              output_meta=excluded.output_meta,
              views=COALESCE(history_records.views, 0),
              likes=COALESCE(history_records.likes, 0),
              record_json=excluded.record_json
            """,
            (
                payload["id"],
                payload["fingerprint"],
                payload["created_at"],
                payload["topic"],
                payload["mode"],
                payload["turn_count"],
                payload["fighter_a_provider"],
                payload["fighter_b_provider"],
                payload["judge_provider"],
                payload["fighter_a_model"],
                payload["fighter_b_model"],
                payload["judge_model"],
                transcript_json,
                judge_json,
                payload["output_meta"],
                int(payload.get("views", 0) or 0),
                int(payload.get("likes", 0) or 0),
                record_json,
            ),
        )
        conn.commit()
    return {"saved_id": normalized["id"], "deduped": deduped, "record": normalized}


def list_history_records(db_path: Path | None = None, sort: str = "recent") -> list[dict]:
    if sort == "likes":
        order_by = "ORDER BY likes DESC, views DESC, datetime(created_at) DESC, rowid DESC"
    else:
        order_by = "ORDER BY datetime(created_at) DESC, rowid DESC"
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM history_records {order_by}"
        ).fetchall()
    return [_record_from_row(row) for row in rows]


def get_history_record(record_id: str, db_path: Path | None = None) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM history_records WHERE id = ?",
            (record_id,),
        ).fetchone()
    return _record_from_row(row) if row else None


def increment_history_metric(record_id: str, metric: str, db_path: Path | None = None) -> dict | None:
    if metric not in {"views", "likes"}:
        raise ValueError("invalid metric")
    with _connect(db_path) as conn:
        conn.execute(
            f"UPDATE history_records SET {metric} = COALESCE({metric}, 0) + 1 WHERE id = ?",
            (record_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM history_records WHERE id = ?",
            (record_id,),
        ).fetchone()
    return _record_from_row(row) if row else None
