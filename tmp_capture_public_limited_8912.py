from pathlib import Path
import json

from playwright.sync_api import sync_playwright


OUT = Path("/tmp/mmar_public_limited_8912")
OUT.mkdir(parents=True, exist_ok=True)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1800})
    console_messages = []
    console_errors = []
    page_errors = []
    requests = []
    def on_console(msg):
        console_messages.append({"type": msg.type, "text": msg.text})
        if msg.type == "error":
            console_errors.append({"type": msg.type, "text": msg.text})
    page.on("console", on_console)
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    page.on("request", lambda req: requests.append(req.url))
    page.goto("http://127.0.0.1:8912/mmar/apps/debate/debate.html", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.click("#run-button")
    page.wait_for_function("document.querySelectorAll('#turn-log .turn-copy').length >= 6")
    page.wait_for_timeout(500)
    summary = {
        "runtime": page.locator("#runtime-fingerprint").inner_text(),
        "topic": page.locator("#topic-display").inner_text(),
        "output_meta": page.locator("#output-meta").inner_text(),
        "status": page.locator("#status").inner_text(),
        "run_button": page.locator("#run-button").inner_text(),
        "topic_readonly": page.locator("#topic").evaluate("el => el.readOnly"),
        "side_a_readonly": page.locator("#side-a").evaluate("el => el.readOnly"),
        "side_b_readonly": page.locator("#side-b").evaluate("el => el.readOnly"),
        "turn_count": page.locator("#turn-log .turn-copy").count(),
        "turn1a": page.locator("#turn-log .turn-copy").nth(0).inner_text(),
        "fixture_fetch": any("public_sora_demo.json" in url for url in requests),
        "api_debate_called": any("/api/debate" in url for url in requests),
        "console_messages": console_messages,
        "console_errors": console_errors,
        "page_errors": page_errors,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    page.screenshot(path=str(OUT / "screen.png"), full_page=True)
    browser.close()

print((OUT / "summary.json").read_text())
