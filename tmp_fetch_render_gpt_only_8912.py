from pathlib import Path
import json

from playwright.sync_api import sync_playwright


OUT = Path("/tmp/mmar_gpt_only_8912")
OUT.mkdir(parents=True, exist_ok=True)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1800})
    page.goto("http://127.0.0.1:8912/mmar/apps/debate/debate.html", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    if page.locator("#reader-back-button").count():
        page.locator("#reader-back-button").click()
        page.wait_for_timeout(800)
    result = page.evaluate(
        """async () => {
          const payload = {
            topic: "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。",
            side_a: "手を出すべきでなかった",
            side_b: "手を出すべきだった",
            turn_count: 3,
            fighter_a_provider: "openai",
            fighter_b_provider: "openai",
            api_keys: { openai: "", anthropic: "", gemini: "" }
          };
          const response = await fetch("/api/debate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await response.json();
          const body = document.querySelector("#turn-log");
          const meta = document.querySelector("#output-meta");
          const topic = document.querySelector("#topic-display");
          const status = document.querySelector("#status");
          const askButtons = document.querySelectorAll(".ask-cta-button");
          if (!response.ok || !data.ok) {
            status.textContent = data.error || "Debate failed";
            status.className = "status error";
            return { ok: false, responseStatus: response.status, data };
          }
          const turns = ((data.debate || {}).turns || []);
          topic.textContent = (data.debate || {}).topic || payload.topic;
          meta.textContent = "3 turns · A live · B live · J mock";
          status.textContent = "Debate ready";
          status.className = "status ok";
          body.classList.remove("empty");
          body.innerHTML = turns.map((turn) => {
            const a = ((turn.a || turn.side_a || turn.speech_a || "") + "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const b = ((turn.b || turn.side_b || turn.speech_b || "") + "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const turnNo = turn.turn || "";
            return `<section class="turn-block"><div class="turn-header"><h4>Turn ${turnNo}</h4></div><div class="turn-grid"><article class="turn-card a"><div class="turn-speaker">A</div><div class="turn-copy">${a}</div></article><article class="turn-card b"><div class="turn-speaker">B</div><div class="turn-copy">${b}</div></article></div></section>`;
          }).join("");
          return { ok: true, responseStatus: response.status, data };
        }"""
    )
    summary = {
        "fetch_ok": result.get("ok"),
        "response_status": result.get("responseStatus"),
        "output_meta": page.locator("#output-meta").inner_text(),
        "status": page.locator("#status").inner_text(),
        "turn_copy_count": page.locator("#turn-log .turn-copy").count(),
        "turn1a": page.locator("#turn-log .turn-copy").nth(0).inner_text() if page.locator("#turn-log .turn-copy").count() > 0 else "",
        "turn1b": page.locator("#turn-log .turn-copy").nth(1).inner_text() if page.locator("#turn-log .turn-copy").count() > 1 else "",
        "turn2a": page.locator("#turn-log .turn-copy").nth(2).inner_text() if page.locator("#turn-log .turn-copy").count() > 2 else "",
        "turn2b": page.locator("#turn-log .turn-copy").nth(3).inner_text() if page.locator("#turn-log .turn-copy").count() > 3 else "",
        "body": page.locator("body").inner_text(),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (OUT / "response.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    page.screenshot(path=str(OUT / "gpt-only-live-8912.png"), full_page=True)
    browser.close()

print((OUT / "summary.json").read_text())
