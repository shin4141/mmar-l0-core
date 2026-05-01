# MMAR Work Protocol

## Purpose
This file defines the work start and end protocol for Codex so MMAR / VerdAIct development stays bounded, recoverable, and release-safe.

## Work Start Protocol
1. Read `docs/MMAR_PUBLIC_CANON.md`.
2. Read `docs/MMAR_RELEASE_LEDGER.md`.
3. Check relevant mistakes in `docs/MMAR_MISTAKES.md`.
4. If battle UI/render path may change, read `docs/MMAR_BATTLE_UI_SMOKE.md`.
5. Fix the mission in one sentence.
6. Fix keep / remove / maybe / rollback / verify.
7. Fix included_changes / excluded_changes.
8. Create a snapshot.
9. Confirm the working tree is clean or explain expected dirt.
10. Confirm current public / preview / candidate state.
11. If deploy is needed, stop for Shin approval.

## Work End Protocol
1. Check changed files.
2. Confirm no mission-outside changes.
3. Reconfirm rollback target.
4. Record verification results.
5. Update docs ledger when state changes.
6. Record whether deploy was touched.
7. If battle UI/render path changed, attach `BATTLE_UI_SMOKE_REPORT`.
8. Confirm clean status for the files touched by the mission.
9. Give one next recommended action.

## Required Planning Block
- mission:
- branch:
- base_sha:
- included_changes:
- excluded_changes:
- rollback_target:
- verification:
- deploy_touched:
- owner_gate_needed:

## Codex DO
- Advance one purpose at a time.
- Fix rollback before editing.
- Check build_sha before UI inspection.
- Keep preview and public separate.
- Stop where manual approval is required.
- Leave state in docs.
- If branches diverge, compare side-by-side before choosing one path.
- For battle UI changes, run existing battle ID smoke checks.

## Codex DO NOT
- Do not deploy `main` to public.
- Do not inspect UI while build_sha mismatches.
- Do not treat local success as release completion.
- Do not treat `node --check` alone as battle UI acceptance.
- Do not treat `node --check` as UI safety proof.
- Do not escape to an old base and drop good changes.
- Do not make incidental fixes outside the mission.
- Do not test on public.
- Do not touch env / DB / publish / remove / delete / archive without explicit instruction.
- Do not request Chrome or logged-in browser access casually.
- Do not Render deploy without owner approval.
- Do not fix multiple render paths in one patch.

## Deploy Rules
- preview deploy = Shin approval only.
- public deploy = Shin approval only.
- completion = fresh public success only.
- docs missions can complete without deploy.

## Verification Rules
- Build SHA match comes first.
- UI/screen checks come after build identity.
- Do not mix public acceptance and preview acceptance.
- Mark known failures as mission-in or mission-out.
- Battle UI changes require smoke checks for:
  - `/battle/fefb70ebe4d1`
  - `/battle/ce07d53d3093`
  - `/battle/9c5f1615bdc3`

## Owner Gate
The following require Shin approval:
- Render operation.
- public deploy.
- branch policy change.
- rollback execution.
- release candidate finalization.

## Stop Conditions
- Unexpected dirty tree.
- build_sha mismatch.
- branch mismatch.
- candidate branch is not separated.
- docs-only work touches code.
- public access is needed.
- mission splits into more than one purpose.
- battle render path breaks.
- node check passes but screen smoke fails.
