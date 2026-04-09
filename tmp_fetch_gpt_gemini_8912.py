from pathlib import Path
import json

from playwright.sync_api import sync_playwright


OUT = Path("/tmp/mmar_fetch_gpt_gemini_8912")
OUT.mkdir(parents=True, exist_ok=True)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1800})
    page.goto("http://127.0.0.1:8912/mmar/apps/debate/debate.html", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    result = page.evaluate(
        """async () => {
          const payload = {
            topic: "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。",
            side_a: "手を出すべきでなかった",
            side_b: "手を出すべきだった",
            turn_count: 3,
            fighter_a_provider: "openai",
            fighter_b_provider: "gemini",
          };
          const response = await fetch("/api/debate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await response.json();
          return { status: response.status, ok: response.ok, data };
        }"""
    )
    (OUT / "fetch-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    browser.close()

print((OUT / "fetch-result.json").read_text())
