from playwright.sync_api import sync_playwright
import json


URL = "http://127.0.0.1:8787/mmar/apps/debate/debate.html"
SIDE_A = "維持すべき。供給安定と脱炭素に必要。"
SIDE_B = "維持は限定的にすべき。コストと事故リスクが重い。"


def visible(page, selector: str) -> bool:
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


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2000})
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror:{e}"))
        page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}") if msg.type == "error" else None)
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1000)

        before = {
            "summary_visible": visible(page, "#public-summary"),
        }

        page.locator("#topic").fill("原発を日本で今後も維持すべきか")
        page.locator("#side-a").fill(SIDE_A)
        page.locator("#side-b").fill(SIDE_B)
        with page.expect_response(lambda response: "/api/debate_v4" in response.url and response.request.method == "POST", timeout=300000):
            page.locator("#run-button").click()
        page.locator("#turn-log .turn-card").first.wait_for(timeout=300000)

        after_run = {
            "summary_visible": visible(page, "#public-summary"),
            "summary_text": page.locator("#public-summary").inner_text().strip(),
            "judge_button_text": page.locator("#judge-button").inner_text().strip(),
            "judge_button_enabled": page.locator("#judge-button").is_enabled(),
        }

        with page.expect_response(lambda response: "/api/judge" in response.url and response.request.method == "POST", timeout=240000):
            page.locator("#judge-button").click()
        page.locator("#verdict-strip").wait_for(timeout=120000)

        after_judge = page.evaluate(
            """() => {
              const visible = (selector) => {
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
              };
              const bodyText = Array.from(document.querySelectorAll('body *'))
                .filter((el) => {
                  let node = el;
                  while (node && node.nodeType === 1) {
                    const cs = getComputedStyle(node);
                    if (node.hidden || cs.display === 'none' || cs.visibility === 'hidden') return false;
                    node = node.parentElement;
                  }
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                })
                .map((el) => (el.innerText || el.textContent || '').trim())
                .filter(Boolean)
                .join('\\n');
              return {
                summary_visible: visible('#public-summary'),
                duplicate_winner_visible: visible('#public-summary-winner'),
                duplicate_one_line_visible: visible('#public-summary-reason'),
                judge_button_disabled: !!document.querySelector('#judge-button') && document.querySelector('#judge-button').disabled === true,
                verdict_visible: visible('#verdict-strip'),
                gemini_judge_present: bodyText.includes('WINNER') || bodyText.includes('GEMINI TAKEAWAY') || bodyText.includes('FLIP CONDITION'),
              };
            }"""
        )

        browser.close()
        print(json.dumps({"before": before, "after_run": after_run, "after_judge": after_judge, "errors": errors}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
