import contextlib
import http.server
import os
import socketserver
import threading
from pathlib import Path

import pytest

if os.getenv("E2E_SMOKE", "0") != "1":
    pytest.skip("E2E smoke is disabled unless E2E_SMOKE=1", allow_module_level=True)

playwright_sync = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync.sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "examples" / "demo"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "screenshots"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return


@contextlib.contextmanager
def _serve_demo_dir():
    handler = lambda *args, **kwargs: _QuietHandler(*args, directory=str(DEMO_DIR), **kwargs)
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield port
        finally:
            httpd.shutdown()
            t.join(timeout=2)


def _screenshot_on_fail(page, name: str):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACT_DIR / f"{name}.png"), full_page=True)


def _set_checkbox(page, selector: str, checked: bool):
    page.eval_on_selector(
        selector,
        """(el, wantChecked) => {
            if (!el) return;
            el.checked = !!wantChecked;
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        checked,
    )


@contextlib.contextmanager
def _open_demo_page(page, quickstart_on: bool = True):
    dg_url = os.getenv("DG_URL", "http://127.0.0.1:8787").rstrip("/")
    with _serve_demo_dir() as port:
        qs = "1" if quickstart_on else "0"
        page.add_init_script(
            f"""() => {{
                try {{ localStorage.setItem("DG_QUICKSTART", "{qs}"); }} catch (_) {{}}
            }}"""
        )
        page.goto(f"http://127.0.0.1:{port}/index.html?api={dg_url}", wait_until="domcontentloaded")
        page.wait_for_selector("#run-live", timeout=20000)
        page.wait_for_timeout(600)
        yield


def test_no_beforeunload_fired_during_core_run():
    console_logs = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda m: console_logs.append(m.text))
        try:
            with _open_demo_page(page):
                page.fill("#q", "犬と猫どちらが賢いか？")
                page.wait_for_selector("#run-live:not([disabled])", timeout=20000)
                page.click("#run-live")
                page.wait_for_selector("#out", timeout=20000)
                page.wait_for_timeout(1500)
                hit = [x for x in console_logs if "beforeunload fired" in x]
                assert not hit, f"unexpected beforeunload log: {hit[:3]}"
        except Exception:
            _screenshot_on_fail(page, "test_no_beforeunload_fired_during_core_run")
            raise
        finally:
            context.close()
            browser.close()


def test_compare_draft_lock_then_core_compare_v1_sections():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            with _open_demo_page(page, quickstart_on=False):
                page.fill("#q", "犬と猫どちらが賢いか？")
                page.wait_for_selector("#cmpA", timeout=15000)
                page.fill("#cmpA", "犬")
                page.fill("#cmpB", "猫")
                page.wait_for_selector("#cmp-status-line", timeout=10000)
                assert "draft" in page.locator("#cmp-status-line").inner_text()

                if not page.is_checked("#compare-lock"):
                    _set_checkbox(page, "#compare-lock", True)
                page.wait_for_timeout(300)
                assert "locked" in page.locator("#cmp-status-line").inner_text()

                page.wait_for_selector("#run-live:not([disabled])", timeout=20000)
                page.click("#run-live")
                page.wait_for_timeout(2000)
                out_text = page.locator("#out").inner_text(timeout=20000)
                assert "AXES:" in out_text, out_text[:600]
                assert "SCORE_TABLE:" in out_text, out_text[:600]
        except Exception:
            _screenshot_on_fail(page, "test_compare_draft_lock_then_core_compare_v1_sections")
            raise
        finally:
            context.close()
            browser.close()
