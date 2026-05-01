# MMAR Mistakes

## Purpose
This file records operational mistakes and prevention rules so MMAR / VerdAIct work does not restart from zero context each turn.

## How to use this file
- Read this before implementation, deploy, rollback, or candidate work.
- Match the current mission against the mistake ledger.
- If a similar risk appears, write the prevention rule into the working plan before editing.
- Treat this as an operations memory, not a blame log.

## Mistake Ledger

### MISTAKE-001
- mistake_id: MISTAKE-001
- what happened: `main` was treated as public-ready and pushed toward public, breaking battle UI.
- why it happened: branch role and public candidate status were not fixed before release work.
- visible damage: public battle detail could diverge from accepted behavior.
- rule learned: never treat `main` as the public candidate by default.
- prevention: create explicit candidate branches and promote only a preview-verified SHA.

### MISTAKE-002
- mistake_id: MISTAKE-002
- what happened: work moved back to an old base and lost `admin/data` and Turn2 context behavior.
- why it happened: rollback target did not list known-good features and lost-change risks.
- visible damage: recovered UI lost analytics and context injection behavior.
- rule learned: old bases are unsafe unless lost changes are enumerated.
- prevention: write rollback_target, included_changes, excluded_changes, and known preserved items first.

### MISTAKE-003
- mistake_id: MISTAKE-003
- what happened: gallery and battle detail were checked as if they shared one image resolver.
- why it happened: separate render paths were not treated as separate verification surfaces.
- visible damage: one page could pass while the other still showed broken or fallback images.
- rule learned: gallery image success does not prove battle detail image success.
- prevention: verify `/gallery` and existing `/battle/{id}` pages independently.

### MISTAKE-004
- mistake_id: MISTAKE-004
- what happened: X embed / video behavior returned through a separate path after it was banned.
- why it happened: only the obvious embed field was blocked; alternate rendering helpers remained active.
- visible damage: battle detail risked rendering iframe, video, script, or twitter blockquote paths.
- rule learned: embed prohibition must cover every render path.
- prevention: grep for `iframe`, `video`, `blockquote`, `script`, `x_embed_html`, and X widget helpers before release.

### MISTAKE-005
- mistake_id: MISTAKE-005
- what happened: original source text and additional information were mixed together.
- why it happened: source panel responsibilities were not fixed before layout work.
- visible damage: `元ネタ` and `追加情報` became confusing or duplicated.
- rule learned: source and additional context are separate responsibilities.
- prevention: keep original source under `元ネタ`; keep context under a separate additional-info label.

### MISTAKE-006
- mistake_id: MISTAKE-006
- what happened: unrelated differences entered a change because included/excluded scope was not fixed.
- why it happened: implementation began before the allowed change surface was written down.
- visible damage: docs, UI, backend, and snapshot churn became hard to separate.
- rule learned: no implementation without scope boundaries.
- prevention: write included_changes and excluded_changes before edits.

### MISTAKE-007
- mistake_id: MISTAKE-007
- what happened: rollback target was not fixed before changing release state.
- why it happened: work moved from local success toward preview/public before a known return point existed.
- visible damage: rollback decisions became slower and riskier.
- rule learned: rollback is part of the start protocol, not the emergency protocol.
- prevention: record rollback_target in the snapshot and canon before edits.

### MISTAKE-008
- mistake_id: MISTAKE-008
- what happened: UI checks almost started before live `/api/health` build_sha matched the intended SHA.
- why it happened: page behavior was checked before build identity.
- visible damage: verification could describe the wrong deployment.
- rule learned: build_sha identity comes before screen inspection.
- prevention: check `/api/health` first and stop on mismatch.

### MISTAKE-009
- mistake_id: MISTAKE-009
- what happened: Codex exploration mode spent 46 minutes without narrowing to a safe action.
- why it happened: investigation lacked a stop condition and decision checkpoint.
- visible damage: time was spent without producing a bounded candidate or clear blocker.
- rule learned: exploration needs a budget and a decision gate.
- prevention: after investigation, report one recommended action or stop with blockers.

### MISTAKE-010
- mistake_id: MISTAKE-010
- what happened: preview/public separation was nearly bypassed, putting unaccepted differences near public.
- why it happened: local and preview confidence were treated as sufficient for public movement.
- visible damage: public could receive an unverified UI or data-path change.
- rule learned: preview acceptance and public promotion are separate gates.
- prevention: only the exact SHA accepted on preview may become a public candidate.

### MISTAKE-011
- mistake_id: MISTAKE-011
- what happened: `node --check` passed, but preview battle detail rendering broke.
- why it happened: syntax validation was mistaken for render validation.
- visible damage: battle detail showed only the header; source, turn log, and judge content did not render.
- rule learned: `node --check` is necessary but not enough for battle UI changes.
- prevention: run existing battle-id smoke checks before preview deploy.

### MISTAKE-012
- mistake_id: MISTAKE-012
- what happened: battle layout restoration, compact judge preservation, and English spectator copy were handled in one render-path patch.
- why it happened: multiple UI responsibilities were combined before DOM smoke coverage existed.
- visible damage: one combined patch broke battle detail rendering.
- rule learned: one render path at a time.
- prevention: create a read-only DOM/render smoke checklist first, then patch one render path per mission.

## Repeated Failure Patterns
- Branch role ambiguity: `main`, `preview`, public candidate, and side candidates get mixed.
- Verification order inversion: UI is checked before build_sha.
- Render-path coupling: source image, context cards, OUTPUT, judge, and localization are changed together.
- Old-base rollback temptation: an older branch appears safer but silently drops newer good behavior.
- Syntax-only confidence: `node --check` or local success is treated as UI acceptance.

## Prevention Rules
- Fix branch, mission, included_changes, excluded_changes, and rollback_target before edits.
- Check `/api/health` build_sha before UI verification.
- For battle UI changes, smoke these existing IDs before preview deploy:
  - `/battle/fefb70ebe4d1`
  - `/battle/ce07d53d3093`
  - `/battle/9c5f1615bdc3`
- Keep gallery, battle detail, and admin/data as separate verification surfaces.
- Patch one render path at a time.

## Stop Conditions
- Branch is not the expected branch.
- Working tree is unexpectedly dirty.
- build_sha does not match the intended SHA.
- A change needs public, main, env, DB, publish, remove, delete, or archive access.
- A docs-only mission begins touching code.
- A battle UI change passes syntax but fails render smoke.

