![ci](https://github.com/shin4141/mmar-l0-core/actions/workflows/ci.yml/badge.svg)　CI validates input/output JSON schemas (contract) and runs run_once.

## Quickstart (local)

### Dev API (for DG_URL-based tests / demo)

Canonical local server start command:

```bash
python tools/dev_api.py
```

Health check:

```bash
curl -fsS http://127.0.0.1:8787/api/health
```

### Quickstart A: delta_entry → gate

```bash
python -m core.run_once \
  --asof examples/asof_pack.example.json \
  --delta examples/delta_entry.example.json \
  --out out_gate_test/decision_gate.json
```

### Quickstart B: mmar_findings → delta_entry → gate

#### B1: findings → delta_entry
```bash
python3 core/findings_to_delta.py --in examples/mmar_findings.example.json --out out_gate_test/delta_entry.from_findings.json
```

#### B2: delta_entry → gate

Note: BLOCK is only triggered when explicitly declared (signals.block=true).

```bash
python -m core.run_once --asof examples/asof_pack.example.json --delta out_gate_test/delta_entry.from_findings.json --out out_gate_test/decision_gate.json
```

### Quickstart C: Gate → Intervene (budget/time-aware)

```bash
python3 tools/intervene_gate.py --gate out_gate_test/decision_gate.from_findings.json --profile examples/intervene_profile.example.json --out out_gate_test/intervene.json
```

python -m pip install jsonschema
python -c "import json; from jsonschema import validate; validate(json.load(open('out_gate_test/decision_gate.json')), json.load(open('decision_gate.schema.json'))); print('schema: OK')"

## Recurrence (aggregate)

Aggregate multiple `recurrence_log.json` files (e.g., downloaded artifacts) and promote recurring patterns:

```bash
python3 tools/recurrence_aggregate.py --in downloads --out out/recurrence_aggregate.json
```

**What is guaranteed (L0)**

As-of (Time V2): decisions are evaluated under the given snapshot, not hindsight.
Deterministic: same inputs → same output JSON.
PIC merge (minimal):

evidence = ∪ (dedupe)
until = max (currently direct from delta)
severity = OR (e.g., delta.block=true => BLOCK)

**Files**

examples/asof_pack.example.json : As-of snapshot input
examples/delta_entry.example.json : Δ input (what changed / what is claimed)
decision_gate.schema.json : output schema
out_gate_test/decision_gate.json : output (generated)

**Roadmap (next)**

Stagnation → Intervene (Subtract-first)
When progress stalls, switch from “keep adding” to:
SUBTRACT (reduce scope/assumptions/dependencies)
ADD_MODEL (inject a different model/OS only if needed)
Progress metric (v0): resolved_count per window (session/day).
If a deadline exists: intervene earlier (threshold is compressed to meet the date).
Default intervention order: SUBTRACT → ADD_MODEL (avoid endless adding).
