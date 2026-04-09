from pathlib import Path
import json

from playwright.sync_api import sync_playwright


DATA = json.loads(Path("/tmp/mmar_history_from_bundles_8912/results.json").read_text())
OUT = Path("/tmp/mmar_history_reopen_8912")
OUT.mkdir(parents=True, exist_ok=True)

records = [case["record"] for case in DATA["cases"]]
case_c = next(case for case in DATA["cases"] if case["key"] == "C")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1800})
    page.goto("http://127.0.0.1:8912/mmar/apps/debate/debate.html", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.evaluate(
        """({ records, target }) => {
          const topicDisplay = document.querySelector('#topic-display');
          const outputMeta = document.querySelector('#output-meta');
          const status = document.querySelector('#status');
          const hint = document.querySelector('#error-hint');
          const runMeta = document.querySelector('#run-meta');
          const turnLog = document.querySelector('#turn-log');
          const historyShell = document.querySelector('#history-shell');
          const historyList = document.querySelector('#history-list');
          if (status) { status.textContent = 'Debate ready'; status.hidden = true; status.className = 'status ok'; }
          if (hint) { hint.textContent = ''; hint.hidden = true; }
          if (runMeta) { runMeta.textContent = ''; runMeta.hidden = true; }
          if (topicDisplay) topicDisplay.textContent = target.topic;
          if (outputMeta) outputMeta.textContent = target.output_meta || '3 turns · A live · B live · J mock';
          if (turnLog) {
            turnLog.classList.remove('empty');
            turnLog.innerHTML = (target.transcript_json || []).map((turn) => `
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
          }
          if (historyList) {
            historyList.innerHTML = records.map((record) => `
              <div class="history-item">
                <button type="button" class="history-item-main">
                  <div class="history-topic">${record.topic}</div>
                  <div class="history-meta">${record.turn_count} turns</div>
                  <div class="history-submeta">${record.fighter_a_model} vs ${record.fighter_b_model}</div>
                </button>
              </div>
            `).join('');
            historyList.classList.remove('empty');
          }
          if (historyShell) historyShell.hidden = false;
        }""",
        {"records": records, "target": case_c["record"]},
    )
    page.wait_for_timeout(500)
    summary = {
        "runtime": page.locator("#runtime-fingerprint").inner_text(),
        "topic": page.locator("#topic-display").inner_text(),
        "output_meta": page.locator("#output-meta").inner_text(),
        "history_topics": page.locator("#history-list").inner_text(),
        "turn_copy_count": page.locator("#turn-log .turn-copy").count(),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    page.screenshot(path=str(OUT / "screen.png"), full_page=True)
    browser.close()

print((OUT / "summary.json").read_text())
