# Battle UI Smoke Checklist v1 Start

- started_at: 2026-05-01T06:48:32Z
- branch: candidate/battle-ui-smoke-checklist-v1
- HEAD SHA: 0fe6116daaa1b94de4abf53b1acfae4cb1f8da5d
- mission: add docs-only battle UI smoke checklist to prevent syntax-pass/render-fail regressions.
- included_changes:
  - battle UI smoke checklist docs
  - minimal references from canon, work protocol, mistakes, and release ledger
  - broken preview `b3c1e98` lesson
  - required smoke IDs
  - build_sha-before-UI-check procedure
- excluded_changes:
  - smoke automation script
  - Playwright or CI changes
  - Render API integration
  - UI/code/English copy changes
- rollback_target: hotfix/public-canon-source-context-restore at `0fe6116daaa1b94de4abf53b1acfae4cb1f8da5d`
- deploy touched: no
- code changes: no

