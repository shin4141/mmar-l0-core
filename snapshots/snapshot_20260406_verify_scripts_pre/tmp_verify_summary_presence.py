from playwright.sync_api import sync_playwright
import json


URL = "http://127.0.0.1:8912/mmar/apps/debate/debate.html"


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
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1000)

        before = {
            "summary_visible": visible(page, "#public-summary"),
        }

        page.locator("#topic").fill("原発を日本で今後も維持すべきか")
        with page.expect_response(lambda response: "/api/debate" in response.url and response.request.method == "POST", timeout=240000):
            page.locator("#run-button").click()
        page.wait_for_function("""() => (document.querySelector('#status')?.textContent || '').trim() === 'Debate ready'""", timeout=240000)
        page.wait_for_timeout(1000)

        after_run = {
            "summary_visible": visible(page, "#public-summary"),
        }

        page.locator("#judge-button").click()
        page.wait_for_function("""() => {
          const btn = document.querySelector('#judge-button');
          return !!btn && btn.disabled === true && (document.querySelector('#status')?.textContent || '').trim() === 'Structure revealed';
        }""", timeout=120000)
        page.wait_for_timeout(1000)

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
                gemini_judge_present: bodyText.includes('Winner') || bodyText.includes('Gemini Takeaway') || bodyText.includes('Verdict'),
              };
            }"""
        )

        browser.close()
        print(json.dumps({"before": before, "after_run": after_run, "after_judge": after_judge}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
