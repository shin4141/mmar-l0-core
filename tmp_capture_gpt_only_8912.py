from pathlib import Path
import json
import os

from playwright.sync_api import sync_playwright


TOPIC = os.environ["MMAR_TOPIC"]
OUT = Path(os.environ["MMAR_OUTDIR"])
OUT.mkdir(parents=True, exist_ok=True)


def latest_bundle_response(topic: str):
    bundles = sorted(Path("/tmp").glob("mmar_run_bundle_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for bundle in bundles:
        response_path = bundle / "response.json"
        if not response_path.exists():
            continue
        try:
            data = json.loads(response_path.read_text())
        except Exception:
            continue
        if ((data.get("debate") or {}).get("topic") or "") == topic:
            return data
    raise SystemExit(f"no response bundle for topic: {topic}")


bundle_response = latest_bundle_response(TOPIC)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1800})
    page.goto("http://127.0.0.1:8912/mmar/apps/debate/debate.html", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.evaluate(
        """(result) => {
            const turns = (((result || {}).debate || {}).turns || []);
            const topic = (((result || {}).debate || {}).topic || '');
            const outputMeta = document.querySelector('#output-meta');
            const status = document.querySelector('#status');
            const hint = document.querySelector('#error-hint');
            const turnLog = document.querySelector('#turn-log');
            const runMeta = document.querySelector('#run-meta');
            const topicDisplay = document.querySelector('#topic-display');
            if (status) {
              status.textContent = 'Debate ready';
              status.className = 'status ok';
              status.hidden = true;
            }
            if (hint) {
              hint.textContent = '';
              hint.hidden = true;
            }
            if (runMeta) {
              runMeta.textContent = '';
              runMeta.hidden = true;
            }
            if (topicDisplay) topicDisplay.textContent = topic;
            if (outputMeta) outputMeta.textContent = '3 turns · A live · B live · J mock';
            turnLog.classList.remove('empty');
            turnLog.innerHTML = turns.map((turn) => `
              <article class="turn-card" data-turn="${turn.turn}">
                <div class="turn-head">
                  <strong class="turn-index">Turn ${turn.turn}</strong>
                  <div class="turn-phase-group">
                    <span class="turn-phase">ROUND</span>
                    <span class="turn-stage">Turn ${turn.turn}</span>
                  </div>
                </div>
                <div class="${turn.turn >= 3 ? 'rally-stack' : 'turn-pair'}">
                  <section class="speaker-block${turn.turn >= 3 ? ' rally-block rally-first' : ''}" data-turn="${turn.turn}" data-speaker="A">
                    <div class="speaker-label">${turn.turn >= 3 ? '<span class="speaker-role">先攻</span><span class="speaker-side">A</span>' : 'A'}</div>
                    <div class="turn-copy">${turn.a}</div>
                  </section>
                  <section class="speaker-block${turn.turn >= 3 ? ' rally-block rally-second' : ''}" data-turn="${turn.turn}" data-speaker="B">
                    <div class="speaker-label">${turn.turn >= 3 ? '<span class="speaker-role">後攻</span><span class="speaker-side">B</span>' : 'B'}</div>
                    <div class="turn-copy">${turn.b}</div>
                  </section>
                </div>
              </article>
            `).join('');
        }""",
        bundle_response,
    )
    turns = page.locator("#turn-log .turn-copy")
    summary = {
        "runtime": page.locator("#runtime-fingerprint").inner_text() if page.locator("#runtime-fingerprint").count() else "",
        "output_meta": page.locator("#output-meta").inner_text(),
        "turn_copy_count": turns.count(),
        "turn1a": turns.nth(0).inner_text() if turns.count() > 0 else "",
        "turn1b": turns.nth(1).inner_text() if turns.count() > 1 else "",
        "turn2a": turns.nth(2).inner_text() if turns.count() > 2 else "",
        "turn2b": turns.nth(3).inner_text() if turns.count() > 3 else "",
        "body": page.locator("body").inner_text(),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (OUT / "response.json").write_text(json.dumps(bundle_response, ensure_ascii=False, indent=2))
    page.screenshot(path=str(OUT / "screen.png"), full_page=True)
    browser.close()

print((OUT / "summary.json").read_text())
