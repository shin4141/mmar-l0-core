from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8912/mmar/apps/debate/debate.html"
TOPIC = "生成AIは初等教育に常時導入すべきか"
SIDE_A = "導入すべき。個別最適化と反復学習の補助になる。"
SIDE_B = "導入は限定的にすべき。依存と評価の歪みが大きい。"


def main() -> None:
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []

        page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        page.goto(URL, wait_until="networkidle")
        page.locator("#topic").fill(TOPIC)
        page.locator("#side-a").fill(SIDE_A)
        page.locator("#side-b").fill(SIDE_B)
        with page.expect_response(lambda r: "/api/debate" in r.url and r.request.method == "POST", timeout=180000) as debate_info:
            page.get_by_role("button", name="Run Debate").click()
        debate_response = debate_info.value
        out["debate_status"] = debate_response.status
        out["turn_cards"] = page.locator("#turn-log .turn-card").count()

        with page.expect_response(lambda r: "/api/judge" in r.url and r.request.method == "POST", timeout=120000) as judge_info:
            page.get_by_role("button", name="Judge Debate").click()
        judge_response = judge_info.value
        out["judge_status_code"] = judge_response.status

        page.wait_for_timeout(1500)
        out["status_text"] = page.locator("#status").inner_text()
        out["verdict_visible"] = page.locator("#verdict-strip").is_visible()
        out["verdict_excerpt"] = page.locator("#verdict-strip").inner_text()[:400] if out["verdict_visible"] else ""
        out["errors"] = errors
        browser.close()
    print(out)


if __name__ == "__main__":
    main()
