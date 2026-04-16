from __future__ import annotations

import json
import os
import sqlite3
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO / "data" / "history.sqlite"


def history_db_path() -> Path:
    override = os.getenv("HISTORY_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_DB_PATH


def history_env_tag(db_path: Path | None = None) -> str:
    override = str(os.getenv("MMAR_ENV_TAG") or "").strip().lower()
    if override:
        return override
    resolved = str((db_path or history_db_path()).expanduser())
    if "/preview-data/" in resolved:
        return "preview"
    if "/var/data/" in resolved:
        return "public"
    return "local"


def history_store_id(db_path: Path | None = None) -> str:
    override = str(os.getenv("MMAR_HISTORY_STORE_ID") or "").strip()
    if override:
        return override
    resolved = str((db_path or history_db_path()).expanduser().resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]
    return f"{history_env_tag(db_path)}-{digest}"


def history_store_meta(db_path: Path | None = None) -> dict[str, str]:
    path = (db_path or history_db_path()).expanduser()
    return {
        "env_tag": history_env_tag(path),
        "history_store_id": history_store_id(path),
        "history_db_path": str(path),
    }


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
          session_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          topic TEXT NOT NULL,
          side_a TEXT NOT NULL,
          side_b TEXT NOT NULL,
          status TEXT NOT NULL,
          debate_result_json TEXT NOT NULL,
          judge_result_json TEXT NOT NULL,
          run_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history_items (
          session_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          promoted_at TEXT NOT NULL,
          hidden INTEGER NOT NULL DEFAULT 0,
          views INTEGER NOT NULL DEFAULT 0,
          likes INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(session_id) REFERENCES runs(session_id)
        )
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(history_records)").fetchall()}
    if "views" not in columns:
        conn.execute("ALTER TABLE history_records ADD COLUMN views INTEGER NOT NULL DEFAULT 0")
    if "likes" not in columns:
        conn.execute("ALTER TABLE history_records ADD COLUMN likes INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def _normalize_run_record(record: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    normalized = dict(record or {})
    session_id = str(normalized.get("session_id") or normalized.get("run_id") or "").strip()
    if not session_id:
        session_id = f"run_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    normalized["session_id"] = session_id
    normalized.setdefault("run_id", session_id)
    normalized.setdefault("created_at", now)
    normalized.setdefault("updated_at", now)
    normalized.setdefault("topic", "")
    normalized.setdefault("stance_a", normalized.get("side_a", ""))
    normalized.setdefault("stance_b", normalized.get("side_b", ""))
    normalized.setdefault("status", "debate_complete")
    normalized.setdefault("debate_result", {})
    normalized.setdefault("judge_result", {})
    normalized.setdefault("deleted_at", "")
    normalized.setdefault("deleted_by", "")
    normalized.setdefault("archived_at", "")
    normalized.setdefault("archived_by", "")
    return normalized


def _run_record_from_row(row: sqlite3.Row) -> dict:
    raw = row["run_json"]
    if raw:
        record = json.loads(raw)
    else:
        record = {}
    record["session_id"] = row["session_id"]
    record["run_id"] = record.get("run_id") or row["session_id"]
    record["created_at"] = record.get("created_at") or row["created_at"]
    record["updated_at"] = row["updated_at"]
    record["topic"] = record.get("topic") or row["topic"]
    record["stance_a"] = record.get("stance_a") or row["side_a"]
    record["stance_b"] = record.get("stance_b") or row["side_b"]
    record["status"] = row["status"]
    record["debate_result"] = json.loads(row["debate_result_json"] or "{}")
    record["judge_result"] = json.loads(row["judge_result_json"] or "{}")
    return record


def save_run_record(record: dict, db_path: Path | None = None) -> dict:
    raw_keys = set(record.keys()) if isinstance(record, dict) else set()
    normalized = _normalize_run_record(record)
    now = datetime.now(timezone.utc).isoformat()
    normalized["updated_at"] = now
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM runs WHERE session_id = ?",
            (normalized["session_id"],),
        ).fetchone()
        if existing:
            previous = _run_record_from_row(existing)
            if not normalized.get("debate_result"):
                normalized["debate_result"] = previous.get("debate_result") or {}
            if not normalized.get("judge_result"):
                normalized["judge_result"] = previous.get("judge_result") or {}
            if not normalized.get("status"):
                normalized["status"] = previous.get("status") or "debate_complete"
            for key in ("deleted_at", "deleted_by", "archived_at", "archived_by"):
                if key not in raw_keys:
                    normalized[key] = previous.get(key) or ""
            normalized["created_at"] = previous.get("created_at") or normalized["created_at"]
        payload = dict(normalized)
        conn.execute(
            """
            INSERT INTO runs (
              session_id, created_at, updated_at, topic, side_a, side_b, status,
              debate_result_json, judge_result_json, run_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              updated_at=excluded.updated_at,
              topic=excluded.topic,
              side_a=excluded.side_a,
              side_b=excluded.side_b,
              status=excluded.status,
              debate_result_json=excluded.debate_result_json,
              judge_result_json=excluded.judge_result_json,
              run_json=excluded.run_json
            """,
            (
                payload["session_id"],
                payload["created_at"],
                payload["updated_at"],
                payload.get("topic", ""),
                payload.get("stance_a", ""),
                payload.get("stance_b", ""),
                payload.get("status", "debate_complete"),
                json.dumps(payload.get("debate_result", {}), ensure_ascii=False),
                json.dumps(payload.get("judge_result", {}), ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        conn.commit()
    return {"saved_id": normalized["session_id"], "record": normalized}


def list_run_records(db_path: Path | None = None, limit: int = 200) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY datetime(created_at) DESC, rowid DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [_run_record_from_row(row) for row in rows]


def get_run_record(session_id: str, db_path: Path | None = None) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return _run_record_from_row(row) if row else None


def run_lifecycle_state(record: dict | None, *, published: bool = False) -> str:
    if not isinstance(record, dict):
        return "candidate"
    if str(record.get("deleted_at") or "").strip():
        return "deleted"
    if str(record.get("archived_at") or "").strip():
        return "archived"
    if published:
        return "published"
    status = str(record.get("status") or "").strip().lower()
    if "fail" in status or "error" in status:
        return "failed"
    return "candidate"


def soft_delete_run(session_id: str, *, deleted_by: str = "", db_path: Path | None = None) -> dict | None:
    record = get_run_record(session_id, db_path=db_path)
    if not record:
        return None
    record["deleted_at"] = datetime.now(timezone.utc).isoformat()
    record["deleted_by"] = str(deleted_by or "").strip()
    record["archived_at"] = ""
    record["archived_by"] = ""
    return save_run_record(record, db_path=db_path).get("record")


def archive_run(session_id: str, *, archived_by: str = "", db_path: Path | None = None) -> dict | None:
    record = get_run_record(session_id, db_path=db_path)
    if not record:
        return None
    record["archived_at"] = datetime.now(timezone.utc).isoformat()
    record["archived_by"] = str(archived_by or "").strip()
    record["deleted_at"] = ""
    record["deleted_by"] = ""
    return save_run_record(record, db_path=db_path).get("record")


def restore_run(session_id: str, db_path: Path | None = None) -> dict | None:
    record = get_run_record(session_id, db_path=db_path)
    if not record:
        return None
    record["deleted_at"] = ""
    record["deleted_by"] = ""
    record["archived_at"] = ""
    record["archived_by"] = ""
    return save_run_record(record, db_path=db_path).get("record")


def promote_run_to_history(session_id: str, db_path: Path | None = None) -> dict | None:
    with _connect(db_path) as conn:
        run_row = conn.execute(
            "SELECT * FROM runs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not run_row:
            return None
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO history_items (session_id, created_at, promoted_at, hidden, views, likes)
            VALUES (?, ?, ?, 0, 0, 0)
            ON CONFLICT(session_id) DO UPDATE SET
              hidden=0,
              promoted_at=excluded.promoted_at
            """,
            (session_id, run_row["created_at"], now),
        )
        conn.commit()
    return get_history_record(session_id, db_path=db_path)


def remove_run_from_history(session_id: str, db_path: Path | None = None) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT session_id FROM history_items WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE history_items SET hidden = 1 WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
    return {"session_id": session_id, "removed": True}


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
    normalized.setdefault("transcript_role", "display")
    normalized.setdefault("raw_turns", normalized.get("transcript_json", []))
    normalized.setdefault("display_turns", normalized.get("transcript_json", []))
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
    with _connect(db_path) as conn:
        item_rows = conn.execute(
            """
            SELECT
              hi.session_id,
              hi.created_at AS item_created_at,
              hi.promoted_at,
              hi.hidden,
              hi.views,
              hi.likes,
              r.*
            FROM history_items hi
            JOIN runs r ON r.session_id = hi.session_id
            WHERE hi.hidden = 0
            """
            + (
                " ORDER BY hi.likes DESC, hi.views DESC, datetime(hi.promoted_at) DESC, r.rowid DESC"
                if sort == "likes"
                else " ORDER BY datetime(hi.promoted_at) DESC, r.rowid DESC"
            )
        ).fetchall()
    records: list[dict] = []
    for row in item_rows:
        run_record = _run_record_from_row(row)
        run_record["id"] = row["session_id"]
        run_record["item_created_at"] = row["item_created_at"]
        run_record["promoted_at"] = row["promoted_at"]
        run_record["hidden"] = bool(row["hidden"])
        run_record["views"] = int(row["views"] or 0)
        run_record["likes"] = int(row["likes"] or 0)
        records.append(run_record)
    return records


def list_published_run_ids(db_path: Path | None = None) -> set[str]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT session_id
            FROM history_items
            WHERE hidden = 0
            """
        ).fetchall()
    return {str(row["session_id"]) for row in rows if row["session_id"]}


def get_history_record(record_id: str, db_path: Path | None = None) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
              hi.session_id,
              hi.created_at AS item_created_at,
              hi.promoted_at,
              hi.hidden,
              hi.views,
              hi.likes,
              r.*
            FROM history_items hi
            JOIN runs r ON r.session_id = hi.session_id
            WHERE hi.session_id = ? AND hi.hidden = 0
            """,
            (record_id,),
        ).fetchone()
    if not row:
        return None
    record = _run_record_from_row(row)
    record["id"] = row["session_id"]
    record["item_created_at"] = row["item_created_at"]
    record["promoted_at"] = row["promoted_at"]
    record["hidden"] = bool(row["hidden"])
    record["views"] = int(row["views"] or 0)
    record["likes"] = int(row["likes"] or 0)
    return record


def increment_history_metric(record_id: str, metric: str, db_path: Path | None = None) -> dict | None:
    if metric not in {"views", "likes"}:
        raise ValueError("invalid metric")
    with _connect(db_path) as conn:
        conn.execute(
            f"UPDATE history_items SET {metric} = COALESCE({metric}, 0) + 1 WHERE session_id = ?",
            (record_id,),
        )
        conn.commit()
    return get_history_record(record_id, db_path=db_path)


def backup_history_store_file(target_path: str | Path, db_path: Path | None = None) -> dict[str, object]:
    source = (db_path or history_db_path()).expanduser()
    target = Path(target_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        raise FileNotFoundError(f"history db not found: {source}")
    shutil.copy2(source, target)
    return {
        "ok": True,
        "source_path": str(source),
        "target_path": str(target),
        **history_store_meta(source),
    }


def export_history_snapshot(db_path: Path | None = None) -> dict[str, object]:
    path = (db_path or history_db_path()).expanduser()
    records = list_history_records(db_path=path)
    exported_at = datetime.now(timezone.utc).isoformat()
    index = [
        {
            "id": str(item.get("id") or item.get("session_id") or ""),
            "title": str(item.get("topic") or ""),
            "topic": str(item.get("topic") or ""),
            "created_at": str(item.get("created_at") or ""),
            "status": str(item.get("status") or ""),
            "record_state": "published",
        }
        for item in records
    ]
    return {
        "snapshot_name": f"{history_env_tag(path)}_history_{len(records)}_snapshot",
        "exported_at": exported_at,
        "count": len(records),
        "index": index,
        "items": records,
        **history_store_meta(path),
    }


def write_history_snapshot(target_path: str | Path, db_path: Path | None = None) -> dict[str, object]:
    snapshot = export_history_snapshot(db_path=db_path)
    target = Path(target_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "snapshot_path": str(target),
        "count": int(snapshot.get("count") or 0),
        "snapshot_name": str(snapshot.get("snapshot_name") or ""),
    }


def _replace_history_items(conn: sqlite3.Connection, session_id: str, record: dict) -> None:
    conn.execute(
        """
        INSERT INTO history_items (session_id, created_at, promoted_at, hidden, views, likes)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
          created_at=excluded.created_at,
          promoted_at=excluded.promoted_at,
          hidden=excluded.hidden,
          views=excluded.views,
          likes=excluded.likes
        """,
        (
            session_id,
            str(record.get("item_created_at") or record.get("created_at") or datetime.now(timezone.utc).isoformat()),
            str(record.get("promoted_at") or datetime.now(timezone.utc).isoformat()),
            1 if bool(record.get("hidden")) else 0,
            int(record.get("views") or 0),
            int(record.get("likes") or 0),
        ),
    )


def import_history_snapshot(
    snapshot: dict[str, object],
    *,
    db_path: Path | None = None,
    clear_existing: bool = False,
) -> dict[str, object]:
    path = (db_path or history_db_path()).expanduser()
    items = snapshot.get("items")
    if not isinstance(items, list):
        raise ValueError("invalid snapshot items")
    imported = 0
    with _connect(path) as conn:
        if clear_existing:
            conn.execute("DELETE FROM history_items")
            conn.execute("DELETE FROM runs")
        conn.commit()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        session_id = str(raw.get("session_id") or raw.get("id") or raw.get("run_id") or "").strip()
        if not session_id:
            continue
        record = dict(raw)
        record["session_id"] = session_id
        record.setdefault("run_id", session_id)
        save_run_record(record, db_path=path)
        with _connect(path) as conn:
            _replace_history_items(conn, session_id, record)
            conn.commit()
        imported += 1
    return {
        "ok": True,
        "imported": imported,
        "count": len(items),
        "clear_existing": bool(clear_existing),
        "snapshot_name": str(snapshot.get("snapshot_name") or ""),
        **history_store_meta(path),
    }


def load_history_snapshot(source_path: str | Path) -> dict[str, object]:
    source = Path(source_path).expanduser()
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid snapshot payload")
    return data
