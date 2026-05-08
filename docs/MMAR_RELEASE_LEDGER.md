# MMAR Release Ledger

Read first: docs/APPROVAL_POLICY.md, then docs/MMAR_PUBLIC_CANON.md, docs/MMAR_MISTAKES.md, docs/MMAR_RELEASE_LEDGER.md, and docs/MMAR_WORK_PROTOCOL.md before any MMAR public/preview/candidate work.

This ledger records durable release fixed points for future MMAR work. Keep entries concise. Do not paste raw chat logs, secrets, tokens, webhooks, or provider keys.

## 2026-05-08 Public-Accepted Fixed Point

- Fixed SHA: `89b6202440f2b612640b6454477a341394d4cbd3`
- Status: preview and public acceptance passed after new-topic verification.
- Preview/public result:
  - New battles generate real `summary.verdict_conditions`.
  - Japanese condition cards render from real data.
  - English condition cards render with English body text.
  - Old battles without `verdict_conditions` fall back by design.
  - SOURCE/OUTPUT and Turn Log remained intact.
  - No `[object Object]`.
  - No iframe/video/twitter/script embeds.
  - No oversized confidence card.

## Included Changes At Fixed Point

- Restored compact battle Judge hierarchy.
- Added condition-card UI:
  - Row 1: decisive hit / A condition / B condition.
  - Row 2: deciding line.
  - Row 3: Gemini Takeaway.
- Added real structured Judge output support:
  - `verdict_conditions.a_win_condition`
  - `verdict_conditions.b_win_condition`
  - `verdict_conditions.deciding_line`
- Aligned English condition-card labels.
- Added English localized payload support for `verdict_conditions`.
- Hardened Gemini model resolution so `models:list` failure does not force full Judge fallback when a usable default or explicit model exists.

## Excluded From This Fixed Point

- No DB migration.
- No admin/gallery/history redesign.
- No SOURCE/OUTPUT structural rewrite.
- No Turn Log structural rewrite.
- No public reliance on mock condition text.
