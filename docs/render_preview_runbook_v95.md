# Render Preview Runbook v95

This repo ships a Render-equivalent preview lane to avoid "public one-shot" verification.

## Services

- Public service: `mmar-debate`
- Preview service: `mmar-debate-preview`

## Equal To Public

The preview service is intentionally identical to public on:

- runtime: `python`
- build command: `pip install -r requirements.txt`
- start command: `python tools/dev_api.py`
- health route: `/api/health`
- static asset routing
- battle/gallery/admin/history route structure
- environment shape

## Intentionally Separated

Preview is separated from public on:

- persistent disk
- `HISTORY_DB_PATH`
- stored runs/history data
- origin hostname

Configured storage split:

- public: `/var/data/mmar/history.sqlite`
- preview: `/var/preview-data/mmar/history.sqlite`

## Verification Checklist

After Render provisions the preview service, verify:

1. `GET /api/health` returns `ok=true`
2. `build_sha` matches the expected commit
3. `api_base` points at the preview origin
4. battle page loads
5. run/save/history close inside preview only
6. admin/history reflects preview data, not public data

## Promotion Rule

- local success = not complete
- preview success = candidate
- public success = complete
