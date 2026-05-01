# MMAR Battle UI Smoke Checklist

## Purpose
`node --check` is necessary but not sufficient. Battle detail can fail at render time even when JavaScript syntax passes. Any battle UI or render-path change must use this checklist before and after preview deploy.

## When This Checklist Is Required
Use this checklist when touching:
- `mmar/apps/debate/debate.js`
- `mmar/apps/debate/debate.css`
- `mmar/apps/debate/debate.html`
- battle detail layout
- source image rendering
- OUTPUT rendering
- Judge Notes rendering
- Turn Log rendering
- `context_cards` rendering
- English spectator display, if it changes battle UI rendering path

## Required Smoke IDs
- `/battle/fefb70ebe4d1`
- `/battle/ce07d53d3093`
- `/battle/9c5f1615bdc3`

## Pre-Deploy Checks
- Confirm branch.
- Confirm rollback_target.
- Confirm included_changes and excluded_changes.
- Run `node --check mmar/apps/debate/debate.js`.
- Record the expected build SHA.
- Do not UI-check preview until `/api/health` build_sha matches the expected SHA.

## Post-Deploy Health Gate
- `/api/health` returns `ok=true`.
- `env_tag=preview`.
- `build_sha` equals the expected commit.
- If build_sha mismatches, stop.
- Do not perform visible UI checks before the match.

## Battle Route Checklist
For each required battle ID, verify:
- page loads
- not header-only
- source image visible
- source image is static image
- no X embed
- no iframe
- no video
- no twitter blockquote
- no script-based embed
- OUTPUT visible
- full source text visible where expected
- Turn Log visible
- Turn 1/2/3 content visible if present
- Judge Notes visible
- Verdict / Takeaway / Quote visible if present
- `context_cards` visible
- `context_cards` not duplicated in a confusing way
- source/additional info separation acceptable
- no massive blank layout regression
- no obvious JS blank state

## Gallery Quick Check
- `/gallery` loads.
- Visible cards have images.
- No obvious broken image regression.

## Admin/Data Quick Check
If authenticated:
- `/admin/data` loads.
- Daily Views visible.
- 7d / 30d / totals visible.
- graph visible.

If unauthenticated:
- record as auth-gated / not checked.
- do not treat as pass.

## Failure Response
If any battle smoke fails:
- stop implementation.
- do not public deploy.
- prefer rollback over continued patching.
- record failure in `docs/MMAR_MISTAKES.md`.
- update `docs/MMAR_RELEASE_LEDGER.md` with broken SHA and rollback SHA.
- one render path at a time.

## Output Template
```text
[BATTLE_UI_SMOKE_REPORT]
branch:
expected build_sha:
live build_sha:
health gate: pass/fail
checked routes:
- /battle/fefb70ebe4d1:
- /battle/ce07d53d3093:
- /battle/9c5f1615bdc3:
gallery:
admin/data:
embed/script observed:
context_cards:
judge notes:
blockers:
public deploy allowed: yes/no
next action:
```

## Final Canon
`node --check` is syntax validation, not proof of UI safety. Battle UI changes are not accepted until existing battle ID smoke checks pass.

