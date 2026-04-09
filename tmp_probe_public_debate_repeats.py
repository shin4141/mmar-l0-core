from __future__ import annotations
import json, time
from playwright.sync_api import sync_playwright

BASE = 'https://mmar-l0-core.onrender.com/mmar/apps/debate/debate.html?cb=public_repeat_probe'
TOPIC = 'GPTは動画サービスに手を出すべきではなかった'
SIDE_A = '手を出すべきではなかった'
SIDE_B = '手を出すべきだった'

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for i in range(3):
        page = browser.new_page()
        responses = []
        page.on('response', lambda res: responses.append({'url': res.url, 'status': res.status, 'ok': res.ok}))
        page.goto(BASE + f'&run={i}', wait_until='networkidle')
        page.locator('#topic').fill(TOPIC)
        page.locator('#side-a').fill(SIDE_A)
        page.locator('#side-b').fill(SIDE_B)
        page.locator('#run-button').click()
        page.wait_for_timeout(5000)
        state_5s = {
            'status': page.locator('#status').inner_text().strip(),
            'runMeta': page.locator('#run-meta').inner_text().strip(),
            'outputMeta': page.locator('#output-meta').inner_text().strip(),
            'turns': page.locator('.turn-card').count(),
            'failed': 'Failed after 0s · Failed' in page.content(),
        }
        deadline = time.time() + 150
        final = None
        while time.time() < deadline:
            status = page.locator('#status').inner_text().strip()
            run_meta = page.locator('#run-meta').inner_text().strip()
            output_meta = page.locator('#output-meta').inner_text().strip()
            turns = page.locator('.turn-card').count()
            failed = 'Failed after 0s · Failed' in page.content()
            if status in ('Debate complete', 'Debate failed') or failed:
                final = {
                    'status': status,
                    'runMeta': run_meta,
                    'outputMeta': output_meta,
                    'turns': turns,
                    'failed': failed,
                }
                break
            page.wait_for_timeout(1000)
        if final is None:
            final = {
                'status': page.locator('#status').inner_text().strip(),
                'runMeta': page.locator('#run-meta').inner_text().strip(),
                'outputMeta': page.locator('#output-meta').inner_text().strip(),
                'turns': page.locator('.turn-card').count(),
                'failed': 'Failed after 0s · Failed' in page.content(),
            }
        results.append({
            'run': i + 1,
            'state_5s': state_5s,
            'final': final,
            'debate_statuses': [r['status'] for r in responses if '/api/debate_v4' in r['url']],
            'save_statuses': [r['status'] for r in responses if '/api/runs/save' in r['url']],
        })
        page.close()
    browser.close()

print(json.dumps(results, ensure_ascii=False))
