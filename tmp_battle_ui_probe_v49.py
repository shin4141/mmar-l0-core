import json
from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8787/mmar/apps/debate/debate.html"
X_URL = "https://x.com/majan_saitou/status/2039145221930598745?s=20"


def text_or_empty(page, selector: str) -> str:
    node = page.locator(selector)
    return node.inner_text().strip() if node.count() else ""


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1200})
    page.goto(URL, wait_until="domcontentloaded")

    initial_hidden = page.locator("#battle-x-source").evaluate("el => el.hidden")
    page.click('[data-experience-mode="battle"]')
    page.wait_for_timeout(250)
    battle_hidden = page.locator("#battle-x-source").evaluate("el => el.hidden")

    page.fill("#battle-x-url", X_URL)
    page.click("#battle-x-build-button")
    page.wait_for_function(
        "() => document.querySelector('#topic')?.value?.trim()?.length > 0 && document.querySelector('#side-a')?.value?.trim()?.length > 0 && document.querySelector('#side-b')?.value?.trim()?.length > 0",
        timeout=120000,
    )
    page.wait_for_timeout(500)

    result = {
        "battle_x_hidden_in_debate": initial_hidden,
        "battle_x_hidden_in_battle": battle_hidden,
        "topic": page.input_value("#topic").strip(),
        "side_a": page.input_value("#side-a").strip(),
        "side_b": page.input_value("#side-b").strip(),
        "source_card_hidden": page.locator("#battle-source-card").evaluate("el => el.hidden"),
        "source_summary": text_or_empty(page, "#battle-source-summary"),
        "status": text_or_empty(page, "#status"),
        "hint": text_or_empty(page, "#error-hint"),
        "run_label": text_or_empty(page, "#run-button"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    browser.close()
