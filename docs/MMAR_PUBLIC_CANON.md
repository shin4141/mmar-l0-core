# MMAR PUBLIC CANON

## Purpose
MMAR public release must preserve the currently verified public behavior while adding only explicitly approved changes.

## Current Public
public_build_sha:
public_branch:
public_status:
last_verified_at:

## Current Preview
preview_build_sha:
preview_branch:
preview_status:
last_verified_at:

## Candidate
candidate_branch:
candidate_base_sha:
candidate_head_sha:
included_changes:
excluded_changes:

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
