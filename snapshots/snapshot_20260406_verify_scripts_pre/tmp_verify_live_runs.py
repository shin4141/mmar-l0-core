from playwright.sync_api import sync_playwright
import json


URL = "http://127.0.0.1:8912/mmar/apps/debate/debate.html"


def run_once(page, topic: str) -> dict:
    page.locator("#topic").fill(topic)
    with page.expect_response(lambda response: "/api/debate" in response.url and response.request.method == "POST", timeout=240000):
        page.locator("#run-button").click()
    page.wait_for_timeout(1500)
    return page.evaluate(
        """() => ({
          status: (document.querySelector('#status')?.textContent || '').trim(),
          turn_cards: document.querySelectorAll('.turn-card').length,
          winner: (document.querySelector('#public-summary-winner')?.textContent || '').trim(),
          reason: (document.querySelector('#public-summary-reason')?.textContent || '').trim(),
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
