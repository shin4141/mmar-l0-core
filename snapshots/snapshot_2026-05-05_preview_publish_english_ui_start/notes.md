# Preview Publish English UI Start

- Date: 2026-05-05T20:36:03+0900
- Base branch: candidate/publish-time-english-payload-v1
- Base SHA: 8b0f5136f4c919c3f5d61d644bef12663b41dff6
- Remote preview health: build_sha 8b0f513, env_tag preview
- Local preview-equivalent health: build_sha 8b0f513, env_tag local

## Files Snapshotted Before Edit

- debate.js.before
- debate.css.before

## Local Screenshots

Stored under:

- snapshots/snapshot_2026-05-05_preview_publish_english_ui_start/local_preview_equivalent/

Battle IDs:

- 5ca312b19cba: top / right_output / lower_judge
- b18e79220ef2: top / right_output / lower_judge
- 7b0ddb5850e3: top / right_output / lower_judge
- gallery_overview.png

## Verification

- `python -m py_compile tools/debate_api.py tools/dev_api.py`: PASS
- Targeted pytest:
  - `PYTHONPATH=/Users/sn/workspaces/mmar-l0-core pytest tests/test_public_canon_static.py tests/test_debate_api.py::test_localize_battle_record_reuses_persisted_en_derivative_when_hash_matches tests/test_debate_api.py::test_localize_battle_record_regenerates_when_source_hash_or_version_is_stale tests/test_debate_api.py::test_localize_battle_record_generates_english_context_cards tests/test_debate_api.py::test_localize_battle_record_sanitizes_partial_english_payload tests/test_debate_api.py::test_admin_publish_generates_localized_payload_before_publication -q`
  - Result: 12 passed
- `tests/test_public_canon_static.py` is included because it locks the updated viewer-shell fallback copy expected from `debate.js`.
- Full `tests/test_debate_api.py` still has existing `_normalize_summary` contract failures unrelated to the localization/UI patch.
- Localized English payload spot checks:
  - 5ca312b19cba: ready, battle-en-v5, no Japanese chars inside `localized_view`
  - b18e79220ef2: ready, battle-en-v5, no Japanese chars inside `localized_view`
  - 7b0ddb5850e3: ready, battle-en-v5, no Japanese chars inside `localized_view`
- Gate smoke:
  - PASS -> NONE
  - DELAY -> SUBTRACT
  - BLOCK -> SUBTRACT

## Preview Note

Render Preview is still serving SHA 8b0f513. No deploy was triggered from this task. Browser automation against the remote Preview domain was blocked in the in-app browser, so post-change Preview screenshots must be captured after the candidate diff is deployed to Preview.
