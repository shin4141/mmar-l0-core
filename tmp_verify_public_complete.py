from __future__ import annotations

import json
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright


BASE = "https://mmar-l0-core.onrender.com"
TOPIC1 = "GPTは動画サービスに手を出すべきではなかった"
TOPIC2 = "外国人観光客による女性への乱暴が多発し、警察が機能していない地域では、地元住民による一定の実力行使は部分的に正当化されるのか"


def admin_session() -> requests.Session:
    session = requests.Session()
    response = session.post(
        f"{BASE}/api/admin/login",
        json={"password": "shin-admin"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    assert payload.get("ok") and payload.get("authenticated"), payload
    return session


def get_json(session: requests.Session, path: str) -> dict:
    response = session.get(f"{BASE}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def post_json(session: requests.Session, path: str, payload: dict) -> dict:
    response = session.post(f"{BASE}{path}", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def wait_for(page, predicate, timeout=240):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = {
            "status": page.locator("#status").inner_text().strip(),
            "runMeta": page.locator("#run-meta").inner_text().strip(),
            "outputMeta": page.locator("#output-meta").inner_text().strip(),
            "turns": page.locator(".turn-card").count(),
        }
        if predicate(last):
            return last
        page.wait_for_timeout(500)
    raise TimeoutError(last)


def run_debate(page, topic: str, side_a: str, side_b: str, run_judge: bool):
    responses: list[tuple[str, int]] = []

    def on_response(response):
        url = response.url
        if any(path in url for path in ["/api/debate_v4", "/api/judge", "/api/runs/save", "/api/history/list"]):
            responses.append((url, response.status))

    page.on("response", on_response)
    page.goto(f"{BASE}/mmar/apps/debate/debate.html?cb=public_complete", wait_until="networkidle")
    page.locator("#topic").fill(topic)
    page.locator("#side-a").fill(side_a)
    page.locator("#side-b").fill(side_b)
    page.locator("#run-button").click()

    debate = wait_for(
        page,
        lambda s: s["status"] == "Debate complete" and "3 turns" in s["outputMeta"] and s["turns"] == 3,
    )
    result = {
        "topicDisplay": page.locator("#topic-display").inner_text().strip(),
        **debate,
        "failed": "Failed after 0s · Failed" in page.content(),
        "responses": responses[:],
    }
    if run_judge:
        page.locator("#judge-button").click()
        result["judge"] = wait_for(page, lambda s: s["status"] == "Judge complete")
    page.remove_listener("response", on_response)
    return result


def latest_run_for_topic(session: requests.Session, topic: str) -> dict | None:
    items = get_json(session, "/api/admin/runs").get("items", [])
    for item in items:
        if item.get("topic") == topic:
            return item
    return None


def main():
    session = admin_session()
    result = {
        "health": get_json(session, "/api/health"),
        "publicHistoryBefore": get_json(session, "/api/history/list"),
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE}/mmar/apps/debate/debate.html?cb=public_front", wait_until="networkidle")
        result["front"] = {
            "h1": page.locator("h1").inner_text().strip(),
            "has_structure_detector": "Structure Detector" in page.content(),
            "has_demo_read_only": "Demo mode / read-only" in page.content(),
            "has_model_setup": "Model Setup" in page.content(),
        }
        result["topic1"] = run_debate(page, TOPIC1, "手を出すべきではなかった", "手を出すべきだった", True)
        result["topic2"] = run_debate(page, TOPIC2, "部分的に正当化される", "正当化されない", False)
        browser.close()

    topic1_run = latest_run_for_topic(session, TOPIC1)
    assert topic1_run, "topic1 run missing"
    detail = get_json(session, f"/api/admin/runs/{topic1_run['session_id']}")["item"]
    result["adminDetail"] = {
        "session_id": detail.get("session_id"),
        "turn_count": detail.get("turn_count"),
        "excerpt": detail.get("excerpt", "")[:160],
        "turn1_a": ((detail.get("display_turns") or [{}])[0]).get("a", "")[:160],
        "judge_winner": (detail.get("judge_json") or {}).get("winner", {}),
    }

    add_payload = post_json(session, "/api/admin/history/add", {"session_id": topic1_run["session_id"]})
    history_after_add = get_json(session, "/api/history/list")["items"]
    remove_payload = post_json(session, "/api/admin/history/remove", {"session_id": topic1_run["session_id"]})
    history_after_remove = get_json(session, "/api/history/list")["items"]
    add_again_payload = post_json(session, "/api/admin/history/add", {"session_id": topic1_run["session_id"]})
    history_after_readd = get_json(session, "/api/history/list")["items"]
    result["curate"] = {
        "add": {"ok": add_payload.get("ok"), "curated": add_payload.get("item", {}).get("curated")},
        "after_add_count": len(history_after_add),
        "remove": remove_payload,
        "after_remove_count": len(history_after_remove),
        "add_again": {"ok": add_again_payload.get("ok"), "curated": add_again_payload.get("item", {}).get("curated")},
        "after_readd_count": len(history_after_readd),
    }
    result["publicHistory"] = {
        "count": len(history_after_readd),
        "turn_count": history_after_readd[0].get("turn_count") if history_after_readd else None,
        "excerpt": history_after_readd[0].get("excerpt", "")[:160] if history_after_readd else "",
        "topic": history_after_readd[0].get("topic") if history_after_readd else "",
    }

    Path("/tmp/mmar_public_complete_verify.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
