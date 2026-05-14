# MMAR Release Ledger

Read first: docs/APPROVAL_POLICY.md, then docs/MMAR_PUBLIC_CANON.md, docs/MMAR_MISTAKES.md, docs/MMAR_RELEASE_LEDGER.md, and docs/MMAR_WORK_PROTOCOL.md before any MMAR public/preview/candidate work.

This ledger records durable release fixed points for future MMAR work. Keep entries concise. Do not paste raw chat logs, secrets, tokens, webhooks, or provider keys.

## 2026-05-14 Public Break And Rollback

- Broken public candidate: `6e37cc037477cc399476e9740221943f5a21647b`.
- Observed public break: `/gallery` on mobile showed unstyled HTML after the candidate public deploy.
- Public rollback deployed: `699a640c13b33f851c4184754ece3acabf9af554`.
- Public restored health: `/api/health` returned `build_sha=699a640` and `env_tag=public`.
- Public restored checks:
  - `/gallery` styled UI restored; unstyled HTML no longer observed.
  - `/battle/fefb70ebe4d1` smoke passed.
  - `/battle/ce07d53d3093` smoke passed.
  - `/battle/9c5f1615bdc3` smoke passed.
  - SOURCE image, OUTPUT, full source text, Judge Notes, and Turn content remained visible.
  - No `[object Object]`, header-only state, or forbidden iframe/video/twitter embeds observed in restored smoke.
- Candidate status: `6e37cc0` is rejected for public until the gallery public smoke / asset loading issue is resolved.
- Preview cause check:
  - Preview `6e37cc0` health matched.
  - Preview `/gallery` CSS/JS returned 200.
  - Preview `/gallery` rendered styled.
  - Cause not conclusively proven; likely public deploy artifact/cache/path mismatch or public-only asset mismatch.
- Operational result: rollback first was correct; investigate the candidate only on preview.

## 2026-05-14 Preview-Accepted Candidate

- Candidate SHA: `855fd9ab5206e528840d8a0951b1d166ce28562c`
- Preview health verified: yes, `/api/health` returned `build_sha=855fd9a` and `env_tag=preview` for `https://mmar-debate-preview.onrender.com`.
- Owner acceptance: pass.
- Public deploy: not yet.
- Public/main/env/DB: untouched.
- Rollback target: `699a640c13b33f851c4184754ece3acabf9af554`.
- Included commits:
  - `7ad2b58` `style: polish mobile battle flow`
  - `855fd9a` `fix: open battle routes in battle mode initially`
- Accepted items:
  - Gallery -> battle flash removed.
  - Mobile battle readability improved.
  - Turn A/B guide improved.
  - Judge Notes readability improved.
- Excluded from this acceptance:
  - No public deploy.
  - No main/env/DB changes.
  - No further Judge Notes polish in this ledger entry.

## 2026-05-13 Release State Alignment

- Public/current: `636bce8`
- Public health verified: yes, `/api/health` returned `build_sha=636bce8` and `env_tag=public` for `https://mmar-l0-core.onrender.com`.
- Preview/current: unknown / not verified in this mission.
- Candidate/current: `636bce8` as the current repo HEAD and user-handoff accepted public state; no candidate branch mutation in this mission.
- Rollback target: `699a640c13b33f851c4184754ece3acabf9af554`.
- Rollback reason: previous public stable rollback after `636bce8` acceptance.
- Status: docs-only ledger correction before any UI work.
- Included in this alignment:
  - Reconciled stale ledger current-public pointer with observed public health.
  - Preserved preview as unverified instead of inferring from public or repo state.
  - Recorded rollback target supplied for the next candidate mission.
- Excluded from this alignment:
  - No UI, CSS, JS, template, judge, API, DB, admin, gallery, preview deploy, or public deploy changes.
  - No public/main/env/publish/remove/delete/archive operation.

## 2026-05-09 Public-Accepted Fixed Point

- Fixed SHA: `699a640c13b33f851c4184754ece3acabf9af554`
- Public/current: `699a640c13b33f851c4184754ece3acabf9af554`
- Preview/current: `699a640c13b33f851c4184754ece3acabf9af554`
- Rollback target: previous public `8b9c00b`; stable rollback `e7a313f`.
- Status: fresh public accepted.
- Accepted by Shin: yes.
- Public result:
  - Beyonce-style condition cards render for complete `verdict_conditions`.
  - New battles generate real `verdict_conditions`.
  - UAE battle with missing `verdict_conditions` uses readable fallback.
  - Mobile condition cards remain one column.
  - Judge Notes reading trail remains visible.
  - SOURCE/OUTPUT and Turn Log remained intact.
  - No `[object Object]`.
  - No iframe/video/twitter/script embeds.
  - No oversized confidence card.

## Included Changes At Fixed Point

- Added unresolved/medium Judge condition-card support.
- Added mobile condition-card one-column behavior.
- Organized Judge Notes lower reading trail.
- Improved readable fallback for missing `verdict_conditions`.
- Added Judge Pass2 `verdict_conditions` completion check and repair pass.

## Excluded From This Fixed Point

- No DB migration.
- No publish/remove/delete/archive operation.
- No debate mode rewrite.
- No unresolved/medium fixture acceptance.

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
