from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8912/mmar/apps/debate/debate.html"


def text_or_empty(page, selector: str) -> str:
    loc = page.locator(selector)
    if loc.count() == 0:
        return ""
    try:
        return (loc.first.text_content() or "").strip()
    except Exception:
        return ""


def visible(page, selector: str) -> bool:
    loc = page.locator(selector)
    try:
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:
        return False


def card_count(page) -> int:
    for selector in [
        "#turn-log .turn-card",
        ".turn-card",
        "[data-turn-card]",
    ]:
        loc = page.locator(selector)
        if loc.count():
            return loc.count()
    return 0


def main() -> None:
    out = {
        "first_run": {},
        "second_run": {},
        "reset": {},
        "errors": [],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda msg: out["errors"].append({"type": "console", "text": msg.text}) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: out["errors"].append({"type": "pageerror", "text": str(exc)}))
        page.goto(URL, wait_until="domcontentloaded")

        page.locator("#topic").fill("生成AIは初等教育に常時導入すべきか")
        page.locator("#side-a").fill("導入すべき。個別最適化と反復学習の補助になる。")
        page.locator("#side-b").fill("導入は限定的にすべき。依存と評価の歪みが大きい。")
        page.get_by_role("button", name="Run Debate").click()
        page.locator(".turn-card").first.wait_for(timeout=240000)
        out["first_run"] = {
            "topic": page.locator("#topic").input_value(),
            "turn_cards": card_count(page),
            "status": text_or_empty(page, "#status"),
            "back_visible": visible(page, "#reader-back-button"),
            "next_visible": visible(page, "#reader-next-button"),
        }

        if visible(page, "#reader-next-button"):
            page.locator("#reader-next-button").click()

        page.locator("#topic").fill("金より銀の方が長期保有に向いているか")
        page.locator("#side-a").fill("はい")
        page.locator("#side-b").fill("いいえ")
        page.get_by_role("button", name="Run Debate").click()
        page.locator(".turn-card").first.wait_for(timeout=240000)
        out["second_run"] = {
            "topic": page.locator("#topic").input_value(),
            "turn_cards": card_count(page),
            "status": text_or_empty(page, "#status"),
        }

        if visible(page, "#reader-next-button"):
            page.locator("#reader-next-button").click()
        out["reset"] = {
            "topic_editable": page.locator("#topic").is_editable(),
            "turn_cards": card_count(page),
            "status": text_or_empty(page, "#status"),
        }
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
