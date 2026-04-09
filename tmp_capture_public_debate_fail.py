from __future__ import annotations

import json
import time
from playwright.sync_api import sync_playwright

BASE = 'https://mmar-l0-core.onrender.com/mmar/apps/debate/debate.html?cb=public_fail_probe'
TOPIC = 'GPTは動画サービスに手を出すべきではなかった'
SIDE_A = '手を出すべきではなかった'
SIDE_B = '手を出すべきだった'

out = {
    'requests': [],
    'responses': [],
    'console': [],
    'page_errors': [],
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.on('console', lambda msg: out['console'].append({'type': msg.type, 'text': msg.text}))
    page.on('pageerror', lambda exc: out['page_errors'].append(str(exc)))
    page.on('request', lambda req: out['requests'].append({'url': req.url, 'method': req.method, 'post_data': req.post_data if '/api/debate_v4' in req.url else None}))
    page.on('response', lambda res: out['responses'].append({'url': res.url, 'status': res.status, 'ok': res.ok, 'body': (res.text()[:2000] if '/api/debate_v4' in res.url or '/api/provider_preflight' in res.url else None)}))

    page.goto(BASE, wait_until='networkidle')
    out['front'] = {
        'h1': page.locator('h1').inner_text().strip(),
        'run_button_text': page.locator('#run-button').inner_text().strip(),
        'status_before': page.locator('#status').inner_text().strip(),
        'runMeta_before': page.locator('#run-meta').inner_text().strip(),
        'outputMeta_before': page.locator('#output-meta').inner_text().strip(),
    }
    page.locator('#topic').fill(TOPIC)
    page.locator('#side-a').fill(SIDE_A)
    page.locator('#side-b').fill(SIDE_B)
    page.locator('#run-button').click()
    page.wait_for_timeout(5000)
    out['after_5s'] = {
        'status': page.locator('#status').inner_text().strip(),
        'runMeta': page.locator('#run-meta').inner_text().strip(),
        'outputMeta': page.locator('#output-meta').inner_text().strip(),
        'topicDisplay': page.locator('#topic-display').inner_text().strip(),
        'turnCount': page.locator('.turn-card').count(),
        'failed_text_present': 'Failed after 0s · Failed' in page.content(),
        'body_excerpt': page.locator('body').inner_text()[:1500],
    }
    browser.close()

print(json.dumps(out, ensure_ascii=False))
