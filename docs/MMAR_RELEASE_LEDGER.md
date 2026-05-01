# MMAR Release Ledger

## Purpose
This ledger gives a quick view of current public, preview, candidate, and rollback points for MMAR / VerdAIct.

## How to update
- Update this after health checks, preview deploys, public deploys, rollbacks, and candidate decisions.
- Record SHA, branch, verification scope, and known risks.
- Do not mark a release complete until fresh public succeeds under the required acceptance conditions.

## Current Public
- public_build_sha: `c7e626c`
- public_env_tag: `public`
- known_public_url: `https://mmar-l0-core.onrender.com`
- gallery_store_id: `postgres-40190409948d`
- gallery_count: `27`
- status: current public canon baseline unless a newer public health value is recorded in `docs/MMAR_PUBLIC_CANON.md`.

## Current Preview
- preview_branch: `preview`
- current_preview_rollback_sha: `672c83f`
- rollback_full_sha: `672c83fd21e5e7dccdcd74d26f50822f1b9261da`
- previous_preview_before_ui_canon_fix: `0e34b4a025f8609513fabb0aaec592db43bd63b4`
- broken_preview_sha: `b3c1e98fd45dc8690d35f07afdc29062810d0e0d`
- status: rollback applied after broken battle detail rendering.
- deploy_note: Shin manually controls Render preview deploy.

## Current Candidate
- english_candidate_branch: `candidate/english-spectator-copy-v0`
- english_candidate_implementation_commit: `b0d655c00f516396f40378933fc576bef05c5cb5`
- english_candidate_known_risk_note_commit: `6f36124cc048df33e7e8f8ef336516f3339e5413`
- ui_canon_freeze_branch: `candidate/ui-canon-freeze-v1`
- ui_canon_freeze_commit: `4012168fdffb5850d595764989d43a41203659a8`
- memory_ops_candidate_branch: `candidate/memory-ops-docs-v1`
- status: candidates remain separate; do not mix English spectator, UI canon alignment, and memory ops docs.

## Rollback Points
- public_canon_reference: `c7e626c`
- hotfix_fixed_point_before_memory_ops: `0bc006c5fea921b6ef365f83d200ee69f34e1b73`
- preview_previous_working_sha: `0e34b4a025f8609513fabb0aaec592db43bd63b4`
- preview_rollback_sha: `672c83fd21e5e7dccdcd74d26f50822f1b9261da`

## Past Release Attempts
- English spectator copy v0:
  - branch: `candidate/english-spectator-copy-v0`
  - implementation: `b0d655c00f516396f40378933fc576bef05c5cb5`
  - known risk note: `6f36124cc048df33e7e8f8ef336516f3339e5413`
  - preview connection lesson: preview service deploys from branch `preview`, not directly from the candidate branch.
- Preview UI canon battle align:
  - broken preview SHA: `b3c1e98fd45dc8690d35f07afdc29062810d0e0d`
  - rollback SHA: `672c83fd21e5e7dccdcd74d26f50822f1b9261da`
  - lesson: syntax checks passed but battle detail render failed; battle UI changes require existing battle-id smoke checks.
  - smoke checklist: `docs/MMAR_BATTLE_UI_SMOKE.md` is required before future battle UI preview deploys.

## Verified URLs
- `/api/health`
- `/gallery`
- `/battle/fefb70ebe4d1`
- `/battle/ce07d53d3093`
- `/battle/9c5f1615bdc3`
- `/admin/data`

## Known Existing Test Failures
- `tests/test_debate_api.py`: `8 failed, 77 passed, 28 skipped`
- status: known backend normalization risk outside touched files.
- policy: do not fix unless it is the mission.

## Next Candidate Rule
- Do not treat `main` as a public candidate.
- Public candidate must be explicitly named.
- Do not perform UI verification before build_sha matches.
- Confirm the preview service connected branch before deploy.
- Only the exact SHA accepted on preview may move toward public.
- Battle UI changes require existing battle ID smoke checks.
- Patch one render path at a time.

## Current State Reload 2026-05-01
- checked_at: 2026-05-01T06:32:52Z
- public_health:
  - ok: true
  - build_sha: `c7e626c`
  - env_tag: `public`
  - history_store_id: `public-0b8d5c509485`
  - history_count: 36
  - gallery_store_id: `postgres-40190409948d`
  - gallery_count: 27
  - published_store_kind: `postgres`
  - published_store_id: `postgres-40190409948d`
  - published_store_url_present: true
- preview_health:
  - ok: true
  - build_sha: `672c83f`
  - env_tag: `preview`
  - history_store_id: `preview-9e016e9dacaa`
  - history_count: 53
  - gallery_store_id: `postgres-40190409948d`
  - gallery_count: 27
  - published_store_kind: `postgres`
  - published_store_id: `postgres-40190409948d`
  - published_store_url_present: true
- preview_battle_smoke:
  - route: `/battle/fefb70ebe4d1`
  - result: pass
  - notes: headless DOM smoke found source, OUTPUT/judge, turn content, and one source image; iframe/video/twitter blockquote/platform script counts were zero.
- memory_ops_candidate:
  - branch: `candidate/memory-ops-docs-v1`
  - commit: `c95c3a957a916d6ac386eed65f4b44a18727cd15`
- rollback_status:
  - broken_preview_sha: `b3c1e98fd45dc8690d35f07afdc29062810d0e0d`
  - reverted_by: `672c83fd21e5e7dccdcd74d26f50822f1b9261da`
  - status: live preview rollback confirmed.
