## Codex Approval Policy

Codex must read `docs/APPROVAL_POLICY.md` before work.
The approval policy is mandatory for all Codex development sessions.
If the policy conflicts with a chat instruction, Codex must stop and ask Shin unless the chat explicitly overrides it.

Inputs: asof_pack.example.json / delta_entry.example.json (schemas validated in CI)

Output: decision_gate.json (schema validated in CI)

Input contract: mmar_findings.json MUST validate against mmar_findings.schema.json (L0 entry).

Merge: PIC minimal (∪/max/OR) + deterministic PASS/DELAY/BLOCK

## MMAR → Delta bridge (v0)

`core/findings_to_delta.py` converts `mmar_findings.json` into `delta_entry.json` for Gate enforcement.

**v0 mapping (deterministic):**
- `severity`:
  - `BLOCK` is only triggered when explicitly declared (e.g., finding.signals.block=true or finding.delta.block=true).
  - otherwise `DELAY` if any `MISSING_EVIDENCE` or `STRUCTURAL_ANOMALY` exists.
  - otherwise `PASS`.
- `evidence`:
  - from `MISSING_EVIDENCE.needs[]` + lightweight tags (e.g., `STRUCTURAL_ANOMALY:COORDINATION`), deduped.
- `changes`:
  - stores a compact record of each finding (type/tag/claim/needs/signals) for traceability.

This bridge is intentionally conservative (DELAY-first) and will be tightened later with thresholds and recurrence.
