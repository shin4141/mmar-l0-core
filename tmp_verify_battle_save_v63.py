import json
import sqlite3
import urllib.request
from pathlib import Path


API_BASE = "http://127.0.0.1:8787"
DB_PATH = Path("/Users/sn/workspaces/mmar-l0-core/data/history.sqlite")
SESSION_ID = "battle_save_v63_seed"


def post(path: str, payload: dict):
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def get(path: str):
    with urllib.request.urlopen(API_BASE + path, timeout=60) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def db_counts():
    conn = sqlite3.connect(DB_PATH)
    try:
        runs = conn.execute("select count(*) from runs").fetchone()[0]
        items = conn.execute("select count(*) from history_items where hidden = 0").fetchone()[0]
        run_row = conn.execute("select session_id, topic from runs where session_id = ?", (SESSION_ID,)).fetchone()
        item_row = conn.execute("select session_id from history_items where session_id = ? and hidden = 0", (SESSION_ID,)).fetchone()
        return {
            "runs": runs,
            "history_items": items,
            "run_exists": bool(run_row),
            "history_exists": bool(item_row),
        }
    finally:
        conn.close()


payload = {
    "session_id": SESSION_ID,
    "run_id": SESSION_ID,
    "topic": "地元住民が迷惑観光客に暴力的制裁を加えるのは許されるか",
    "stance_a": "地元女性を守るためならこの対応は正当だ",
    "stance_b": "自力救済は行き過ぎで法的に問題だ",
    "status": "debate_complete",
    "debate_result": {
        "topic": "地元住民が迷惑観光客に暴力的制裁を加えるのは許されるか",
        "stance_a": "地元女性を守るためならこの対応は正当だ",
        "stance_b": "自力救済は行き過ぎで法的に問題だ",
        "turn_count": 3,
        "transcript_json": [],
        "raw_turns": [],
        "display_turns": [],
        "provider_statuses": {},
        "output_meta": "3 turns · completed",
        "elapsed_seconds": 12,
        "source_mode": "live",
        "experience_mode": "battle",
        "source_type": "x_post",
        "source_url": "https://x.com/majan_saitou/status/2039145221930598745?s=20",
        "source_summary": "バリ島MMAファイターが酔ったロシア人観光客を絞め落とした動画",
    },
    "judge_result": {
        "winner": {"side": "Draw", "reason": "今回は片側を勝ちにするより、保留の方が妥当"},
        "reason_one_liner": "今回は片側を勝ちにするより、保留の方が妥当",
    },
    "run_json": {
        "experience_mode": "battle",
        "source_url": "https://x.com/majan_saitou/status/2039145221930598745?s=20",
        "source_summary": "バリ島MMAファイターが酔ったロシア人観光客を絞め落とした動画",
    },
}


before = db_counts()
save_status, save_data = post("/api/runs/save", payload)
after = db_counts()
history_status, history_data = get("/api/history/list")

print(
    json.dumps(
        {
            "before": before,
            "save_status": save_status,
            "save_ok": save_data.get("ok"),
            "save_history_item_present": bool(save_data.get("history_item")),
            "saved_id": save_data.get("saved_id"),
            "after": after,
            "history_status": history_status,
            "history_ok": history_data.get("ok"),
            "history_contains_seed": any((item.get("id") or item.get("run_id")) == SESSION_ID for item in history_data.get("items", [])),
        },
        ensure_ascii=False,
    )
)
