# MMAR Work Protocol

Read first: docs/APPROVAL_POLICY.md, then docs/MMAR_PUBLIC_CANON.md, docs/MMAR_MISTAKES.md, docs/MMAR_RELEASE_LEDGER.md, and docs/MMAR_WORK_PROTOCOL.md before any MMAR public/preview/candidate work.

This protocol is the default path for candidate, preview, and public work. `docs/APPROVAL_POLICY.md` remains mandatory and takes precedence.

## Release Flow

1. Candidate branch work.
2. Local verification.
3. Candidate fixed commit.
4. Push accepted candidate to `origin/preview`.
5. Preview deploy only after Shin approval.
6. Check preview `/api/health`.
7. Stop if `build_sha` does not match the expected SHA.
8. Run owner-visible preview smoke on the exact URL and data path.
9. Public deploy only after Shin approval.
10. Check public `/api/health`.
11. Stop if public `build_sha` does not match.
12. Run public smoke on the exact owner-visible URL and real data path.

## Final Acceptance Rule

Final acceptance requires all three:

- Same expected SHA.
- Owner-visible URL.
- Real data path for the feature being accepted.

Mock-only proof is not public acceptance. Same SHA alone is not enough when public-visible data differs from preview.

## Data-Dependent UI Rule

For UI that depends on stored or generated fields:

- Verify a record that actually contains those fields.
- Verify old records that lack the fields fall back safely.
- Classify old-data fallback as normal or regression before changing code.
- Do not save, publish, remove, delete, archive, or mutate DB records without Shin approval.

## Stop Rules

Stop before visual checks when `build_sha` mismatches.

Stop before public deployment unless Shin explicitly approves public deploy.

Stop before env/DB/main/public/publish/remove/delete/archive operations unless Shin explicitly approves the exact operation.

Stop when a security audit contains BLOCK/DELAY sensitive material that would leak into long-term operational records.

## Docs-Only Missions

Docs-only missions must not deploy, push, or alter app code. Verify with:

- `git status --short`
- `git diff --stat`
- docs-only file list
- no secrets or raw logs
