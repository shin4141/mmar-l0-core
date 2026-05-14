# MMAR Mistakes To Preserve

Read first: docs/APPROVAL_POLICY.md, then docs/MMAR_PUBLIC_CANON.md, docs/MMAR_MISTAKES.md, docs/MMAR_RELEASE_LEDGER.md, and docs/MMAR_WORK_PROTOCOL.md before any MMAR public/preview/candidate work.

This file records operational mistakes that must not be repeated. Keep it actionable and free of raw chat logs or sensitive audit material.

## Acceptance Mistakes

- Do not treat partial screenshots as complete owner acceptance.
- Do not confuse mock-only acceptance with real-condition acceptance.
- Do not assume preview data exists on public.
- Do not treat same SHA as sufficient when public-visible data differs.
- Do not deploy public before real owner-visible preview acceptance.
- Do not call old-data fallback a regression before checking whether the record actually has the new structured fields.
- Do not treat battle detail smoke as sufficient public acceptance; fresh public smoke must include `/gallery` on mobile.
- Do not assume preview pass proves public artifact/cache correctness.

## Preview/Public Data Mistakes

- Same code can behave differently when preview and public data stores contain different records.
- Data-dependent UI needs at least one real record generated through the target environment's normal flow.
- Existing records without `summary.verdict_conditions` should use the safe fallback path. That is normal unless the record is expected to contain the new fields.
- Mock flags are useful for visual validation, but public acceptance must not depend on mock data.

## Provider/Environment Mistakes

- Do not ignore public provider/env differences after preview passes.
- A public `/api/judge` fallback with the same SHA can still be caused by provider behavior, key/project limitations, or model discovery differences.
- `models:list` failure must not force full Judge fallback when an explicit model or default model can be used for `generateContent`.
- Capture sanitized request summaries and provider status details. Do not expose API keys.

## UI Scope Mistakes

- Do not fix one visual issue by rewriting SOURCE/OUTPUT, Turn Log, or unrelated Judge sections.
- Do not let a mock-only condition-card path become a public candidate.
- Do not let condition-card changes break old-record fallback.
- Do not let English labels be translated while English body text remains raw Japanese.
- After public deploy, verify CSS/JS asset loading and styled UI on `/gallery`, not just HTTP 200 or battle pages.
- If public shows unstyled HTML, rollback first and investigate later on preview.
