from playwright.sync_api import sync_playwright
import json


URL = "http://127.0.0.1:8787/mmar/apps/debate/debate.html"
SIDE_A = "導入すべき。実務効率と学習補助の改善につながる。"
SIDE_B = "導入は限定的にすべき。依存と品質低下のリスクがある。"


def run_once(page, topic: str) -> dict:
    if page.locator("#reader-back-button").is_visible():
        page.locator("#reader-back-button").click()
        page.wait_for_function(
            """() => {
              const shell = document.querySelector('.page-shell');
              return !!shell && !shell.classList.contains('reading-mode');
            }""",
            timeout=30000,
        )
    page.locator("#topic").fill(topic)
    page.locator("#side-a").fill(SIDE_A)
    page.locator("#side-b").fill(SIDE_B)
    with page.expect_response(lambda response: "/api/debate_v4" in response.url and response.request.method == "POST", timeout=300000):
        page.locator("#run-button").click()
    page.locator("#turn-log .turn-card").first.wait_for(timeout=300000)
    return page.evaluate(
        """() => ({
          status: (document.querySelector('#status')?.textContent || '').trim(),
          turn_cards: document.querySelectorAll('.turn-card').length,
          summary_visible: !!document.querySelector('#public-summary') && !document.querySelector('#public-summary').hidden,
          summary_text: (document.querySelector('#public-summary')?.innerText || '').trim(),
          judge_button_text: (document.querySelector('#judge-button')?.textContent || '').trim(),
          judge_button_enabled: !!document.querySelector('#judge-button') && document.querySelector('#judge-button').disabled === false,
          topic_display: (document.querySelector('#topic-display')?.textContent || '').trim()
        })"""
    )


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1800})
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror:{e}"))
        page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}") if msg.type == "error" else None)
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1000)
        first = run_once(page, "原発を日本で今後も維持すべきか")
        second = run_once(page, "大学教育でレポート課題を全面的にAI補助可にすべきか")
        browser.close()
        print(json.dumps({"first": first, "second": second, "errors": errors}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
