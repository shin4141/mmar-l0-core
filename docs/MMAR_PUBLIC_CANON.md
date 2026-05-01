# MMAR PUBLIC CANON

## Purpose
MMAR public release must preserve the currently verified public behavior while adding only explicitly approved changes.

## Related Docs
- `docs/MMAR_MISTAKES.md`
- `docs/MMAR_RELEASE_LEDGER.md`
- `docs/MMAR_WORK_PROTOCOL.md`

## Current Public
- public_url: https://mmar-l0-core.onrender.com
- public_health_checked_at: 2026-05-01T03:10:53.950385+00:00
- public_build_sha: c7e626c
- public_env_tag: public
- public_history_store_id: public-0b8d5c509485
- public_history_count: 36
- public_gallery_store_id: postgres-40190409948d
- public_gallery_count: 27
- public_published_store_kind: postgres
- public_published_store_id: postgres-40190409948d
- public_published_store_url_present: true
- public_branch: unknown live public; `/api/health` reports build_sha `c7e626c`
- public_branch_sha_local: 5fb1eb92af4a91742c888feefb23b5e12d272633
- public_status: health_checked_only / UI not verified in this turn
- last_verified_at: 2026-05-01T03:10:53.950385+00:00 for `/api/health` only
- verified_urls:
  - `https://mmar-l0-core.onrender.com/api/health`: ok; build_sha `c7e626c`
  - `https://mmar-l0-core.onrender.com/gallery`: not checked
  - `https://mmar-l0-core.onrender.com/battle/fefb70ebe4d1`: not checked
  - `https://mmar-l0-core.onrender.com/battle/ce07d53d3093`: not checked
  - `https://mmar-l0-core.onrender.com/battle/9c5f1615bdc3`: not checked
  - `https://mmar-l0-core.onrender.com/admin/data`: not checked
- known_good_items:
  - Public `/api/health` returned `ok: true` with env_tag `public`.
  - Required behavior is defined by Required Invariants below and must be rechecked on fresh public before completion.
- known_risks:
  - Public build_sha is `c7e626c`; full live UI behavior is not verified in this turn.
  - Gallery and battle detail use different image resolver paths; both must be checked.
  - Fresh public / incognito / same-conditions twice success is required before any completion claim.

## Current Preview
- preview_url: https://mmar-debate-preview.onrender.com
- preview_health_checked_at: 2026-05-01T03:10:54.138265+00:00
- preview_build_sha: c7e626c
- preview_env_tag: preview
- preview_history_store_id: preview-9e016e9dacaa
- preview_history_count: 53
- preview_gallery_store_id: postgres-40190409948d
- preview_gallery_count: 27
- preview_published_store_kind: postgres
- preview_published_store_id: postgres-40190409948d
- preview_published_store_url_present: true
- preview_branch: preview
- preview_branch_sha_local: c31ab66e4f3b5a4969634b0ad2111a7946f2c859
- preview_status: health_checked_only / UI not verified in this turn
- last_verified_at: 2026-05-01T03:10:54.138265+00:00 for `/api/health` only
- verified_urls:
  - `https://mmar-debate-preview.onrender.com/api/health`: ok; build_sha `c7e626c`
  - `https://mmar-debate-preview.onrender.com/gallery`: not checked
  - `https://mmar-debate-preview.onrender.com/battle/fefb70ebe4d1`: not checked
  - `https://mmar-debate-preview.onrender.com/battle/ce07d53d3093`: not checked
  - `https://mmar-debate-preview.onrender.com/battle/9c5f1615bdc3`: not checked
  - `https://mmar-debate-preview.onrender.com/admin/data`: not checked
- known_good_items:
  - Preview `/api/health` returned `ok: true` with env_tag `preview`.
  - Any public promotion must use the exact SHA accepted on preview.
- known_risks:
  - Preview build_sha is `c7e626c`; full live UI behavior is not verified in this turn.
  - Local success is not release completion.
  - Preview-verified SHA must match the public candidate SHA before deploy.

## Candidate
- candidate_branch: none
- candidate_base_sha: not selected
- candidate_head_sha: none
- included_changes:
  - none
- excluded_changes:
  - all implementation changes
- rollback_target: live public `/api/health` reports `c7e626c`; keep previous local rollback reference `codex/public-deploy-05f135d` at 5fb1eb92af4a91742c888feefb23b5e12d272633 until Shin confirms next棚卸し range
- status: blocked / manual_review_pending

## Public UI Route Check
- checked_at: 2026-05-01T12:31:26+0900
- build_sha: c7e626c
- method: read-only headless Chrome DOM check plus read-only curl/API checks; no deploy, DB write, publish, remove, delete, or archive action.
- routes:
  - route: `https://mmar-l0-core.onrender.com/gallery`
    result: pass
    notes: page rendered 25 battle cards with `25 cards`; first viewport had 9 visible images and 0 visible broken images; 17 remote gallery image URLs returned HTTP 200; no iframe/video/twitter blockquote/X widget script observed.
    screenshots: not required
    blocker: no
  - route: `https://mmar-l0-core.onrender.com/battle/fefb70ebe4d1`
    result: partial
    notes: battle detail rendered; left source image loaded as static image `1200x675`; source card includes `元ネタ` and separated `追加情報`; right OUTPUT includes original source text; no iframe/video/twitter blockquote/X widget script observed; Turn2 context cards observed in DOM. Note: context card nodes appear in more than one display area, so Shin review is needed before treating this as full duplicate-free acceptance.
    screenshots: not required
    blocker: no
  - route: `https://mmar-l0-core.onrender.com/battle/ce07d53d3093`
    result: partial
    notes: battle detail rendered; left source image loaded as static image `1200x675`; source card includes `元ネタ` and separated `追加情報`; right OUTPUT includes original source text; no iframe/video/twitter blockquote/X widget script observed; Turn2 context cards observed in DOM. Note: context card nodes appear in more than one display area, so Shin review is needed before treating this as full duplicate-free acceptance.
    screenshots: not required
    blocker: no
  - route: `https://mmar-l0-core.onrender.com/battle/9c5f1615bdc3`
    result: partial
    notes: battle detail rendered; left source image loaded as static image `1200x675`; source card includes `元ネタ` and separated `追加情報`; right OUTPUT includes original source text; no iframe/video/twitter blockquote/X widget script observed; Turn2 context cards observed in DOM. Note: context card nodes appear in more than one display area, so Shin review is needed before treating this as full duplicate-free acceptance.
    screenshots: not required
    blocker: no
  - route: `https://mmar-l0-core.onrender.com/admin/data`
    result: unknown
    notes: route redirected to `/admin/login` for unauthenticated read-only check; admin page itself displayed login UI. Daily Views / 7d / 30d / totals / graph could not be verified without an authenticated admin session.
    screenshots: not required
    blocker: yes for admin/data graph verification

## Preview UI Route Check
- checked_at: 2026-05-01T12:31:26+0900
- build_sha: c7e626c
- method: read-only headless Chrome DOM check plus read-only curl/API checks; no deploy, DB write, publish, remove, delete, or archive action.
- routes:
  - route: `https://mmar-debate-preview.onrender.com/gallery`
    result: pass
    notes: page rendered 25 battle cards with `25 cards`; first viewport had 9 visible images and 0 visible broken images; same gallery store as public; no iframe/video/twitter blockquote/X widget script observed.
    screenshots: not required
    blocker: no
  - route: `https://mmar-debate-preview.onrender.com/battle/fefb70ebe4d1`
    result: partial
    notes: battle detail rendered; left source image loaded as static image `1200x675`; source card includes `元ネタ` and separated `追加情報`; right OUTPUT includes original source text; no iframe/video/twitter blockquote/X widget script observed; Turn2 context cards observed in DOM. Note: context card nodes appear in more than one display area, so Shin review is needed before treating this as full duplicate-free acceptance.
    screenshots: not required
    blocker: no
  - route: `https://mmar-debate-preview.onrender.com/battle/ce07d53d3093`
    result: partial
    notes: battle detail rendered; left source image loaded as static image `1200x675`; source card includes `元ネタ` and separated `追加情報`; right OUTPUT includes original source text; no iframe/video/twitter blockquote/X widget script observed; Turn2 context cards observed in DOM. Note: context card nodes appear in more than one display area, so Shin review is needed before treating this as full duplicate-free acceptance.
    screenshots: not required
    blocker: no
  - route: `https://mmar-debate-preview.onrender.com/battle/9c5f1615bdc3`
    result: partial
    notes: battle detail rendered; left source image loaded as static image `1200x675`; source card includes `元ネタ` and separated `追加情報`; right OUTPUT includes original source text; no iframe/video/twitter blockquote/X widget script observed; Turn2 context cards observed in DOM. Note: context card nodes appear in more than one display area, so Shin review is needed before treating this as full duplicate-free acceptance.
    screenshots: not required
    blocker: no
  - route: `https://mmar-debate-preview.onrender.com/admin/data`
    result: unknown
    notes: route redirected to `/admin/login` for unauthenticated read-only check; admin page itself displayed login UI. Daily Views / 7d / 30d / totals / graph could not be verified without an authenticated admin session.
    screenshots: not required
    blocker: yes for admin/data graph verification

## Next Candidate Readiness
- current_public_build_sha: c7e626c
- current_preview_build_sha: c7e626c
- gallery_public_preview: pass under read-only DOM/API checks
- battle_detail_public_preview: partial; static source images, source/context separation, OUTPUT original source text, and no X embed/iframe/video/twitter blockquote/X widget script observed; Shin review needed for duplicate-free acceptance because context cards are rendered in multiple DOM areas.
- admin_data_public_preview: unknown; unauthenticated checks redirect to `/admin/login`, so Daily Views / 7d / 30d / totals / graph are not verified.
- candidate_ready: no
- next_required_before_candidate: authenticated `/admin/data` read-only verification or Shin decision to exclude admin graph from this棚卸し gate.

## Manual Acceptance Pending
- authenticated_admin_data:
  - public `/admin/data`: pending authenticated read-only check.
  - preview `/admin/data`: pending authenticated read-only check.
  - must verify: Daily Views, 7d, 30d, totals, graph visible, and no major blank page or JS error.
- battle_context_cards_duplicate_free:
  - `/battle/fefb70ebe4d1`: pending Shin acceptance that context cards are visible but not duplicated in a confusing way.
  - `/battle/ce07d53d3093`: pending Shin acceptance that context cards are visible but not duplicated in a confusing way.
  - `/battle/9c5f1615bdc3`: pending Shin acceptance that context cards are visible but not duplicated in a confusing way.
  - must verify: source/additional info separation is acceptable and right OUTPUT full source is acceptable.
- candidate_readiness_rule:
  - Do not create a candidate until authenticated `/admin/data` and battle context card duplicate-free acceptance are complete, or Shin explicitly waives one of these gates.
  - Until acceptance, candidate status remains `blocked / manual_review_pending`.

## Release Checklist
- [ ] `/api/health` build_sha matches candidate_head_sha.
- [ ] `/gallery` checked.
- [ ] `/battle/fefb70ebe4d1` checked.
- [ ] `/battle/ce07d53d3093` checked.
- [ ] `/battle/9c5f1615bdc3` checked.
- [ ] `/admin/data` checked.
- [ ] Incognito checked.
- [ ] Same conditions pass twice.
- [ ] Fresh public succeeds before completion is claimed.
- [ ] X embed/video prohibition checked.
- [ ] Turn2 `context_cards` checked.
- [ ] Image fallback behavior checked.

## Work Start Protocol
Before any public/preview candidate work:
- Read this Canon.
- Create a snapshot under `snapshots/` before implementation.
- Record public / preview / candidate SHA values.
- Write `included_changes` and `excluded_changes`.
- Do not implement if `included_changes`, `excluded_changes`, or `rollback_target` is blank.
- Fix the change purpose in one sentence.
- Write `rollback_target`.
- Public deploy requires explicit Shin approval.
- Do not deploy `main` directly to public.

## Work End Protocol
Before reporting completion:
- Write changed files.
- Write verification results.
- Classify each failed test as pre-existing or introduced by this change.
- State that Render was not operated.
- Stop and wait for Shin approval.

## Required Invariants

### Gallery
- `/gallery` must load.
- Claude image must display from static image URL, not SVG fallback.
- ChatGPT shooting-plan image must display from static image URL, not SVG fallback.
- 9-year-old / NVIDIA images must remain visible.
- Image-less cards must keep fallback without layout collapse.

### Battle Detail Source Panel
- Original source and injected/added context must be displayed as separate sections.
- Original source must remain under label: `元ネタ`.
- Injected/added context must remain under a separate label such as `追加情報` or `補足情報`.
- Injected context must not be merged into the original source text.
- Injected context must not appear as oversized hero text.
- Left source panel must not destroy the battle layout.

### X / Embed Security
- Battle detail must never render `x_embed_html`.
- Battle detail must never render iframe, twitter blockquote, script, or video embed.
- X/Twitter source must be represented by static image thumbnail + source URL link only.
- External embed restoration is BLOCK.

### Turn2 Injection
- `context_cards` created from X URL/source parsing must be preserved.
- `/api/debate_v4` payload must pass `context_cards` and `context_card_mode`.
- Context preface must be injected into Turn2 only.
- Turn1 style change must not be mixed into this fix.
- Turn3 must preserve necessary context after Turn2.

### Publish / Saved Detail
- Publishing must not drop `context_cards`.
- Saved battle detail must preserve source/context fields needed for display.
- Publish must not convert separated original/context cards into one merged text block.

### Admin Data
- `/admin/data` must show Daily Views.
- Daily Views must be aggregate over all published battles, not a single battle.
- 7d / 30d must work.
- totals must show views / opens / shares / saves / published_count.
- Empty data must not crash.

## Verify URLs
- `/api/health`
- `/gallery`
- `/battle/fefb70ebe4d1`
- `/battle/ce07d53d3093`
- `/battle/9c5f1615bdc3`
- `/admin/data`

## Hard Rules
- Do not deploy main directly to public.
- Do not use old base unless explicitly listed with lost changes.
- Do not merge preview-unverified UI changes into public.
- Render deploy is Shin-only.
- Codex must not touch env / DB / publish / remove / delete / archive unless explicitly instructed.
- Every release candidate must list included_changes and excluded_changes.
