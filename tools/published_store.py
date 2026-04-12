from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = REPO / "data" / "published_gallery.sqlite"


def published_store_url() -> str:
    return str(os.getenv("PUBLISHED_STORE_URL") or "").strip()


def _sqlite_path_from_url(url: str) -> Path:
    if not url:
        return DEFAULT_SQLITE_PATH
    parsed = urlparse(url)
    if parsed.scheme != "sqlite":
        raise ValueError("not_sqlite_url")
    raw_path = unquote(parsed.path or "")
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        raw_path = f"/{parsed.netloc}{raw_path}"
    if not raw_path:
        return DEFAULT_SQLITE_PATH
    return Path(raw_path).expanduser()


def published_store_kind() -> str:
    url = published_store_url()
    if not url:
        return "sqlite"
    if urlparse(url).scheme == "sqlite":
        return "sqlite"
    return "postgres"


def published_store_id() -> str:
    url = published_store_url()
    basis = url or str(DEFAULT_SQLITE_PATH.resolve())
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
    return f"{published_store_kind()}-{digest}"


def published_store_meta() -> dict[str, str]:
    url = published_store_url()
    return {
        "published_store_kind": published_store_kind(),
        "published_store_id": published_store_id(),
        "published_store_url_present": "true" if bool(url) else "false",
    }


def _connect_sqlite() -> sqlite3.Connection:
    path = _sqlite_path_from_url(published_store_url())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS published_cards (
          id TEXT PRIMARY KEY,
          promoted_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          hidden INTEGER NOT NULL DEFAULT 0,
          views INTEGER NOT NULL DEFAULT 0,
          likes INTEGER NOT NULL DEFAULT 0,
          record_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_published_cards_visible ON published_cards(hidden, promoted_at DESC)"
    )
    return conn


@contextmanager
def _postgres_conn():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg_missing") from exc
    try:
        conn = psycopg.connect(
            published_store_url(),
            connect_timeout=5,
        )
    except Exception as exc:
        print("[publish-error] connect", exc)
        raise
    try:
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS published_cards (
                  id TEXT PRIMARY KEY,
                  promoted_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  hidden BOOLEAN NOT NULL DEFAULT FALSE,
                  views BIGINT NOT NULL DEFAULT 0,
                  likes BIGINT NOT NULL DEFAULT 0,
                  record_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_published_cards_visible ON published_cards(hidden, promoted_at DESC)"
            )
        except Exception as exc:
            print("[publish-error] schema", exc)
            raise
        conn.commit()
        yield conn
        conn.commit()
    except Exception as exc:
        print("[publish-error] query", exc)
        raise
    finally:
        try:
            conn.close()
        except Exception as exc:
            print("[publish-error] close", exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_record(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("invalid_record")
    normalized = dict(record)
    record_id = str(
        normalized.get("id")
        or normalized.get("session_id")
        or normalized.get("run_id")
        or ""
    ).strip()
    if not record_id:
        raise ValueError("missing_record_id")
    normalized["id"] = record_id
    normalized.setdefault("session_id", record_id)
    normalized.setdefault("run_id", record_id)
    normalized.setdefault("created_at", _now_iso())
    normalized["promoted_at"] = str(normalized.get("promoted_at") or _now_iso())
    normalized["views"] = int(normalized.get("views", 0) or 0)
    normalized["likes"] = int(normalized.get("likes", 0) or 0)
    return normalized


def _record_from_row(row) -> dict:
    record = json.loads(row["record_json"])
    record["id"] = str(record.get("id") or row["id"] or "")
    record["session_id"] = str(record.get("session_id") or record["id"])
    record["run_id"] = str(record.get("run_id") or record["id"])
    record["promoted_at"] = row["promoted_at"]
    record["views"] = int(row["views"] or 0)
    record["likes"] = int(row["likes"] or 0)
    return record


def publish_record(record: dict) -> dict:
    normalized = _normalize_record(record)
    payload = json.dumps(normalized, ensure_ascii=False)
    now = _now_iso()
    if published_store_kind() == "sqlite":
        with _connect_sqlite() as conn:
            conn.execute(
                """
                INSERT INTO published_cards (id, promoted_at, updated_at, hidden, views, likes, record_json)
                VALUES (?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  promoted_at=excluded.promoted_at,
                  updated_at=excluded.updated_at,
                  hidden=0,
                  record_json=excluded.record_json
                """,
                (
                    normalized["id"],
                    normalized["promoted_at"],
                    now,
                    normalized["views"],
                    normalized["likes"],
                    payload,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM published_cards WHERE id = ?",
                (normalized["id"],),
            ).fetchone()
            return _record_from_row(row)
    with _postgres_conn() as conn:
        conn.execute(
            """
            INSERT INTO published_cards (id, promoted_at, updated_at, hidden, views, likes, record_json)
            VALUES (%s, %s, %s, FALSE, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              promoted_at=EXCLUDED.promoted_at,
              updated_at=EXCLUDED.updated_at,
              hidden=FALSE,
              record_json=EXCLUDED.record_json
            """,
            (
                normalized["id"],
                normalized["promoted_at"],
                now,
                normalized["views"],
                normalized["likes"],
                payload,
            ),
        )
        row = conn.execute(
            "SELECT id, promoted_at, views, likes, record_json FROM published_cards WHERE id = %s",
            (normalized["id"],),
        ).fetchone()
        return _record_from_row(row)


def unpublish_record(record_id: str) -> dict | None:
    record_id = str(record_id or "").strip()
    if not record_id:
        return None
    if published_store_kind() == "sqlite":
        with _connect_sqlite() as conn:
            row = conn.execute("SELECT id FROM published_cards WHERE id = ?", (record_id,)).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE published_cards SET hidden = 1, updated_at = ? WHERE id = ?",
                (_now_iso(), record_id),
            )
            conn.commit()
            return {"id": record_id, "removed": True}
    with _postgres_conn() as conn:
        row = conn.execute("SELECT id FROM published_cards WHERE id = %s", (record_id,)).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE published_cards SET hidden = TRUE, updated_at = %s WHERE id = %s",
            (_now_iso(), record_id),
        )
        return {"id": record_id, "removed": True}


def get_published_card(record_id: str) -> dict | None:
    record_id = str(record_id or "").strip()
    if not record_id:
        return None
    if published_store_kind() == "sqlite":
        with _connect_sqlite() as conn:
            row = conn.execute(
                "SELECT * FROM published_cards WHERE id = ? AND hidden = 0",
                (record_id,),
            ).fetchone()
            return _record_from_row(row) if row else None
    with _postgres_conn() as conn:
        row = conn.execute(
            "SELECT id, promoted_at, views, likes, record_json FROM published_cards WHERE id = %s AND hidden = FALSE",
            (record_id,),
        ).fetchone()
        return _record_from_row(row) if row else None


def list_published_cards(sort: str = "recent") -> list[dict]:
    order = (
        "ORDER BY likes DESC, views DESC, promoted_at DESC, id DESC"
        if sort == "likes"
        else "ORDER BY promoted_at DESC, id DESC"
    )
    if published_store_kind() == "sqlite":
        with _connect_sqlite() as conn:
            rows = conn.execute(
                f"SELECT * FROM published_cards WHERE hidden = 0 {order}"
            ).fetchall()
            return [_record_from_row(row) for row in rows]
    with _postgres_conn() as conn:
        rows = conn.execute(
            f"SELECT id, promoted_at, views, likes, record_json FROM published_cards WHERE hidden = FALSE {order}"
        ).fetchall()
        return [_record_from_row(row) for row in rows]


def count_published_cards() -> int:
    if published_store_kind() == "sqlite":
        with _connect_sqlite() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM published_cards WHERE hidden = 0"
            ).fetchone()
            return int(row["count"] or 0)
    with _postgres_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM published_cards WHERE hidden = FALSE"
        ).fetchone()
        if isinstance(row, dict):
            return int(row.get("count") or 0)
        return int(row[0] or 0)


def list_published_card_ids() -> set[str]:
    return {str(item.get("id") or "") for item in list_published_cards()}


def increment_published_metric(record_id: str, metric: str) -> dict | None:
    record_id = str(record_id or "").strip()
    if not record_id or metric not in {"views", "likes"}:
        return None
    if published_store_kind() == "sqlite":
        with _connect_sqlite() as conn:
            row = conn.execute(
                "SELECT * FROM published_cards WHERE id = ? AND hidden = 0",
                (record_id,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                f"UPDATE published_cards SET {metric} = {metric} + 1, updated_at = ? WHERE id = ?",
                (_now_iso(), record_id),
            )
            conn.commit()
            refreshed = conn.execute(
                "SELECT * FROM published_cards WHERE id = ? AND hidden = 0",
                (record_id,),
            ).fetchone()
            return _record_from_row(refreshed)
    with _postgres_conn() as conn:
        row = conn.execute(
            f"""
            UPDATE published_cards
            SET {metric} = {metric} + 1, updated_at = %s
            WHERE id = %s AND hidden = FALSE
            RETURNING id, promoted_at, views, likes, record_json
            """,
            (_now_iso(), record_id),
        ).fetchone()
        return _record_from_row(row) if row else None
