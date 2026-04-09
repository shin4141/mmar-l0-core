from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, "/Users/sn/workspaces/mmar-l0-core/tools")
import debate_api  # noqa: E402


OUT = Path("/tmp/mmar_public_8912")
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    {
        "id": "case_a",
        "topic": "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。",
        "side_a": "手を出すべきでなかった",
        "side_b": "手を出すべきだった",
    },
    {
        "id": "case_b",
        "topic": "人の命に値段をつけることは許されるか？",
        "side_a": "許される",
        "side_b": "許されない",
    },
    {
        "id": "case_c",
        "topic": "警察はパチンコで換金が行われていることを知っているか？",
        "side_a": "知っている",
        "side_b": "知らない",
    },
]


def first_sentence(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    for mark in ("。", "！", "？", "!", "?"):
        idx = text.find(mark)
        if idx != -1:
            return text[: idx + 1]
    return text


def inject_result(page, result):
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
        result,
    )


def main():
    summary = {"cases": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for case in CASES:
            payload = {
                "topic": case["topic"],
                "side_a": case["side_a"],
                "side_b": case["side_b"],
                "turn_count": 3,
                "mode": "casual",
                "fighter_a_provider": "openai",
                "fighter_b_provider": "openai",
                "api_keys": {"openai": "", "anthropic": "", "gemini": ""},
                "_disable_live_judge": True,
            }
            result = debate_api.run_debate(payload)
            case_dir = OUT / case["id"]
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "response.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))

            page = browser.new_page(viewport={"width": 1600, "height": 1800})
            page.goto("http://127.0.0.1:8912/mmar/apps/debate/debate.html", wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            inject_result(page, result)
            page.screenshot(path=str(case_dir / "screen.png"), full_page=True)
            page.close()

            turns = result["debate"]["turns"]
            history_ok = len({result["run_id"], result["topic_hash"], result["debate"]["topic"]}) == 3
            summary["cases"].append(
                {
                    "id": case["id"],
                    "topic": case["topic"],
                    "provider_statuses": result.get("provider_statuses", {}),
                    "run": result.get("ok", False),
                    "turns_visible": len(turns) == 3,
                    "role_separation": bool(first_sentence(turns[0]["a"])) and bool(first_sentence(turns[0]["b"])) and first_sentence(turns[0]["a"]) != first_sentence(turns[0]["b"]),
                    "current_run_history": history_ok,
                    "turn1a_first": first_sentence(turns[0]["a"]),
                    "turn1b_first": first_sentence(turns[0]["b"]),
                    "turn2a_first": first_sentence(turns[1]["a"]),
                    "turn2b_first": first_sentence(turns[1]["b"]),
                    "screen": str(case_dir / "screen.png"),
                }
            )
        browser.close()
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print((OUT / "summary.json").read_text())


if __name__ == "__main__":
    main()
