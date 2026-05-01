# MMAR PUBLIC CANON

## Purpose
MMAR public release must preserve the currently verified public behavior while adding only explicitly approved changes.

## Current Public
- public_url: https://mmar-l0-core.onrender.com
- public_build_sha: unknown
- public_branch: unknown live public; local public-deploy branch candidate is `codex/public-deploy-05f135d`
- public_branch_sha_local: 5fb1eb92af4a91742c888feefb23b5e12d272633
- public_status: snapshot_only / live not verified in this turn
- last_verified_at: unknown; not checked in this snapshot turn
- verified_urls:
  - `https://mmar-l0-core.onrender.com/api/health`: not checked; build_sha unknown
  - `https://mmar-l0-core.onrender.com/gallery`: not checked
  - `https://mmar-l0-core.onrender.com/battle/fefb70ebe4d1`: not checked
  - `https://mmar-l0-core.onrender.com/battle/ce07d53d3093`: not checked
  - `https://mmar-l0-core.onrender.com/battle/9c5f1615bdc3`: not checked
  - `https://mmar-l0-core.onrender.com/admin/data`: not checked
- known_good_items:
  - Unknown for live public in this turn because browser/public verification is intentionally out of scope.
  - Required behavior is defined by Required Invariants below and must be rechecked on fresh public before completion.
- known_risks:
  - Live public SHA is unknown until `/api/health` is checked.
  - Gallery and battle detail use different image resolver paths; both must be checked.
  - Fresh public / incognito / same-conditions twice success is required before any completion claim.

## Current Preview
- preview_url: https://mmar-debate-preview.onrender.com
- preview_build_sha: unknown
- preview_branch: preview
- preview_branch_sha_local: c31ab66e4f3b5a4969634b0ad2111a7946f2c859
- preview_status: snapshot_only / live not verified in this turn
- last_verified_at: unknown; not checked in this snapshot turn
- verified_urls:
  - `https://mmar-debate-preview.onrender.com/api/health`: not checked; build_sha unknown
  - `https://mmar-debate-preview.onrender.com/gallery`: not checked
  - `https://mmar-debate-preview.onrender.com/battle/fefb70ebe4d1`: not checked
  - `https://mmar-debate-preview.onrender.com/battle/ce07d53d3093`: not checked
  - `https://mmar-debate-preview.onrender.com/battle/9c5f1615bdc3`: not checked
  - `https://mmar-debate-preview.onrender.com/admin/data`: not checked
- known_good_items:
  - Unknown for live preview in this turn because browser/preview verification is intentionally out of scope.
  - Any public promotion must use the exact SHA accepted on preview.
- known_risks:
  - Live preview SHA is unknown until `/api/health` is checked.
  - Local success is not release completion.
  - Preview-verified SHA must match the public candidate SHA before deploy.

## Candidate
- candidate_branch: none designated for this restart snapshot
- candidate_base_sha: 5fb1eb92af4a91742c888feefb23b5e12d272633 local public-deploy branch pointer; live public SHA unknown
- candidate_head_sha: none
- included_changes:
  - none
- excluded_changes:
  - all implementation changes
- rollback_target: current public SHA unknown from live public; local rollback reference is `codex/public-deploy-05f135d` at 5fb1eb92af4a91742c888feefb23b5e12d272633
- status: snapshot_only / not_started

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
