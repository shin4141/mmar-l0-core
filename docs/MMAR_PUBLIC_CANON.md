# MMAR Public Canon

Read first: docs/APPROVAL_POLICY.md, then docs/MMAR_PUBLIC_CANON.md, docs/MMAR_MISTAKES.md, docs/MMAR_RELEASE_LEDGER.md, and docs/MMAR_WORK_PROTOCOL.md before any MMAR public/preview/candidate work.

This file records public-facing invariants and acceptance rules for MMAR.

## Current Public-Accepted Fixed Point

- SHA: `89b6202440f2b612640b6454477a341394d4cbd3`
- Acceptance: preview and public acceptance passed after new-topic verification.
- New battles generate real `summary.verdict_conditions`.
- Old battles without `verdict_conditions` fall back by design.

## Public Candidate Rule

- A public candidate must come from a preview-accepted SHA.
- Public deploy requires Shin approval.
- `public`, `main`, env, DB, publish, remove, delete, and archive operations require Shin approval.
- Public normal flow must use real `verdict_conditions`, not mock data.
- Mock flags are preview/dev only.

## UI Invariants

- SOURCE/OUTPUT remain intact.
- Turn Log remains intact.
- No iframe/video/twitter/script embeds.
- No `[object Object]`.
- No oversized confidence card.
- Condition cards render only when required real fields exist:
  - `a_win_condition`
  - `b_win_condition`
  - `deciding_line`
- Missing condition fields use the safe fallback layout.

## Language Invariants

- Japanese condition-card path uses Japanese labels and body text.
- English condition-card path uses English labels and English body text.
- English fallback may keep fallback-specific labels such as Why It Held.
- English pages must not leak raw Japanese condition text in the condition-card path.

## Public Acceptance Checklist

- Public `/api/health` `build_sha` matches expected SHA.
- Owner-visible public URL is inspected.
- For data-dependent UI, at least one public-visible real record is verified.
- Old-record fallback is checked and classified.
- SOURCE/OUTPUT and Turn Log are visible.
- No `[object Object]`.
- No forbidden embeds.
- No oversized confidence card.
