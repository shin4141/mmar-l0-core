# APPROVAL_POLICY

## Purpose
This policy defines what Codex may do automatically, what requires Shin approval, and what must stop.

## Core Rule
Reading and verification may proceed.
Fixing, destructive actions, external reflection, deployment, and public-facing changes require explicit boundaries or Shin approval.

## AUTO: Allowed without Shin approval
- git status
- git diff
- git diff --stat
- git ls-remote
- git rev-parse
- git log read-only
- local tests
- node --check
- pytest
- py_compile
- read-only curl to /api/health
- browser/local screenshots for verification
- grep/search/read-only inspection

## SEMI-AUTO: Allowed only inside the fixed mission
- git add
- git commit

Conditions:
- branch is correct
- base SHA is confirmed
- diff is inside mission scope
- git status and git diff --stat are checked before commit
- commit message matches mission

## SHIN APPROVAL REQUIRED
- git push
- preview deploy
- public deploy
- Render operation
- env changes
- DB changes
- publish/remove/delete/archive
- merge
- reset --hard
- revert
- rm/rm -rf
- dependency install
- token/private URL use
- POST/DELETE API calls
- changing main/preview/public branches
- history rewrite
- branch deletion
- production data mutation

## FORBIDDEN UNLESS EXPLICITLY APPROVED
- public deploy from main
- public deploy from unaccepted preview SHA
- testing on public
- touching env/DB/publish/remove/delete/archive
- destructive cleanup
- broad merge of preview/main
- mixing unrelated missions
- claiming completion from tests only
- claiming visual pass without screenshots for UI/layout work

## UI / Layout Work Rule
For UI/layout changes, HTML 200, node --check, and pytest are not enough.

Required before Shin preview deploy:
1. SCREEN CONTRACT
2. DATA CONTRACT where relevant
3. browser-rendered screenshots
4. acceptance map against the screen contract
5. explicit remaining risks

Shin preview deploy is final confirmation, not debugging.

## Release Rule
- local success is not completion
- preview SHA must match /api/health before visible smoke
- public deploy requires Shin approval
- public can receive only the same SHA that passed preview

## Output Required After Work
Report:
- branch
- base SHA
- new commit SHA
- pushed yes/no
- working tree clean yes/no
- changed files
- included changes
- excluded changes
- tests run
- visual/browser evidence if UI
- deploy touched yes/no
- public/main/env/DB touched yes/no
- ready/not ready and why
