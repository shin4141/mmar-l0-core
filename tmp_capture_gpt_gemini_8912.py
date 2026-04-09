from pathlib import Path
import json

from playwright.sync_api import sync_playwright


OUT = Path("/tmp/mmar_live_gpt_gemini_8912")
OUT.mkdir(parents=True, exist_ok=True)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1800})
    logs = []
    page.on("console", lambda m: logs.append({"type": m.type, "text": m.text}))
    page.goto("http://127.0.0.1:8912/mmar/apps/debate/debate.html", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    if page.locator("#reader-back-button").count():
        page.locator("#reader-back-button").click()
        page.wait_for_timeout(1000)
    page.eval_on_selector("#fighter-a-provider", "el => el.value = 'openai'")
    page.eval_on_selector("#fighter-b-provider", "el => el.value = 'gemini'")
    page.eval_on_selector("#api-base", "el => el.value = ''")
    page.fill("#topic", "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。")
    page.fill("#side-a", "手を出すべきでなかった")
    page.fill("#side-b", "手を出すべきだった")
    page.eval_on_selector("#debate-form", "form => form.requestSubmit()")
    page.wait_for_timeout(45000)
    summary = {
        "status": page.locator("#status").inner_text(),
        "output_meta": page.locator("#output-meta").inner_text(),
        "turn_copy_count": page.locator("#turn-log .turn-copy").count(),
        "hint": page.locator("#hint").inner_text() if page.locator("#hint").count() else "",
        "body": page.locator("body").inner_text(),
        "logs": logs,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    page.screenshot(path=str(OUT / "live-8912.png"), full_page=True)
    browser.close()

print((OUT / "summary.json").read_text())
