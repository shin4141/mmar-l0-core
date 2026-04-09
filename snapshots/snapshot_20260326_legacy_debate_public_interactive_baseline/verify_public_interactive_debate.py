from playwright.sync_api import sync_playwright
import json


URL = "http://127.0.0.1:8912/mmar/apps/debate/debate.html"
SCREENSHOT = "/Users/sn/workspaces/mmar-l0-core/snapshots/snapshot_20260326_legacy_debate_public_interactive_baseline/public_interactive_debate.png"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1800})
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror:{e}"))
        page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}") if msg.type == "error" else None)
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(800)

        def visible(selector: str) -> bool:
            return page.evaluate(
                """(selector) => {
                  const el = document.querySelector(selector);
                  if (!el) return false;
                  let node = el;
                  while (node && node.nodeType === 1) {
                    const cs = getComputedStyle(node);
                    if (node.hidden || cs.display === 'none' || cs.visibility === 'hidden') return false;
                    node = node.parentElement;
                  }
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                }""",
                selector,
            )

        initial = page.evaluate(
            """() => ({
              topic_editable: !!document.querySelector('#topic') && !document.querySelector('#topic').readOnly,
              side_a_prefilled: (document.querySelector('#side-a')?.value || '').trim().length > 0,
              side_b_prefilled: (document.querySelector('#side-b')?.value || '').trim().length > 0
            })"""
        )

        page.locator("#topic").fill("ベーシックインカムを日本で導入すべきか")
        page.locator("#run-button").click()
        page.wait_for_function(
            """() => {
              const status = (document.querySelector('#status')?.textContent || '').trim();
              return status === 'Debate ready' || status.includes('error') || status.includes('failed');
            }""",
            timeout=120000,
        )
        first_run = page.evaluate(
            """() => ({
              status: document.querySelector('#status')?.textContent?.trim() || '',
              turn_cards: document.querySelectorAll('.turn-card').length,
              winner: document.querySelector('#public-summary-winner')?.textContent?.trim() || '',
              reason: document.querySelector('#public-summary-reason')?.textContent?.trim() || ''
            })"""
        )

        page.locator("#topic").fill("大学教育でレポート課題を全面的にAI補助可にすべきか")
        page.locator("#run-button").click()
        page.wait_for_function(
            """() => {
              const status = (document.querySelector('#status')?.textContent || '').trim();
              return status === 'Debate ready' || status.includes('error') || status.includes('failed');
            }""",
            timeout=120000,
        )
        second_run = page.evaluate(
            """() => ({
              status: document.querySelector('#status')?.textContent?.trim() || '',
              turn_cards: document.querySelectorAll('.turn-card').length,
              winner: document.querySelector('#public-summary-winner')?.textContent?.trim() || '',
              reason: document.querySelector('#public-summary-reason')?.textContent?.trim() || '',
              current_topic: document.querySelector('#topic-display')?.textContent?.trim() || ''
            })"""
        )

        traces = {
            "fixed_demo_traces_gone": not any(
                [
                    visible("#demo-mode-badge"),
                    visible("#public-fixed-demo-note"),
                    visible("#reader-controls"),
                ]
            ),
            "ask_traces_gone": not any(
                [
                    page.locator("[data-ask-reference-add]").count() > 0,
                    visible("#ask-shell"),
                    visible("#ask-match-button"),
                ]
            ),
            "history_traces_gone": not any(
                [
                    visible("#history-button"),
                    visible("#archive-button"),
                    visible("#history-shell"),
                    visible("#archive-shell"),
                ]
            ),
            "provider_api_settings_gone": not any(
                [
                    visible("#model-setup-box"),
                    visible("#api-settings-box"),
                ]
            ),
            "debug_traces_gone": not any(
                [
                    visible("#runtime-fingerprint"),
                    visible("#debug-pipeline-panel"),
                ]
            ),
        }

        page.screenshot(path=SCREENSHOT, full_page=True)
        browser.close()
        print(
            json.dumps(
                {
                    "initial": initial,
                    "first_run": first_run,
                    "second_run": second_run,
                    "traces": traces,
                    "errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
