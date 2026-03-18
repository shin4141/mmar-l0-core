# Debate UI API Contract

This document fixes the public response contract consumed by the Debate UI.

## Scope

- `/api/debate`
- `/api/health`

This is a UI contract, not an engine spec. Public UI code should depend only on the keys below.

## `/api/debate`

Schema file:

- [schemas/debate_response.public.json](/Users/sn/workspaces/mmar-l0-core/schemas/debate_response.public.json)

### Required top-level keys

- `ok: boolean`
  - Used for request success handling.
- `mode: "live" | "mock" | "mock-fallback"`
  - Used for `source mode` display.
- `provider_statuses: object`
  - Used for `A/B/J` provider mode display.
- `debate: object`
  - Used for topic, turn log, and judge result rendering.

### Optional top-level keys

- `warning: string`
  - Optional user-facing note.

### Required `provider_statuses` keys

- `provider_statuses.openai.mode`
- `provider_statuses.anthropic.mode`
- `provider_statuses.gemini.mode`

Optional:

- `provider_statuses.{provider}.reason`
  - Public UI should treat this as display-only text.

### Required `debate` keys

- `debate.topic: string`
- `debate.turn_count: integer`
- `debate.turns: array`
- `debate.summary: object`

Optional:

- `debate.participants`

### Required `debate.turns[]` keys

- `turn: integer`
- `stage_label: string`
- `a: string`
- `b: string`

Optional:

- `phase: string`
  - Future key. When fixed, the UI can stop inferring `Phase 1 / Phase 2 / Phase 3` from turn number.

### Required `debate.summary` keys

- `fatal_phrase`
- `turning_point`
- `contradiction_exposed`
- `unresolved_residue`
- `provisional_judgment`
- `key_disagreement_top3`

Notes:

- `fatal_phrase` may be either a string or an object.
- Current UI supports the richer object shape:
  - `fatal_phrase.turn`
  - `fatal_phrase.speaker`
  - `fatal_phrase.text`
  - `fatal_phrase.reason`

### Future optional summary keys

- `rule_expansion`
- `rule_capture`
- `contradiction`

These are not required for the current UI. They should remain optional until the UI actually renders them.

## `/api/health`

Current UI dependency:

- `build_sha?: string`

This endpoint is only used for connection status text. No other health response fields are part of the frozen public UI contract.

## Current UI Dependency Surface

The Debate UI reads only the following response keys:

- `ok`
- `mode`
- `provider_statuses.openai.mode`
- `provider_statuses.anthropic.mode`
- `provider_statuses.gemini.mode`
- `debate.topic`
- `debate.turns[]`
- `debate.turns[].turn`
- `debate.turns[].stage_label`
- `debate.turns[].a`
- `debate.turns[].b`
- `debate.summary`
- `debate.summary.fatal_phrase`
- `debate.summary.turning_point`
- `debate.summary.contradiction_exposed`
- `debate.summary.unresolved_residue`
- `debate.summary.provisional_judgment`
- `debate.summary.key_disagreement_top3`
- `/api/health -> build_sha`

If backend internals change, the UI should remain stable as long as this contract is preserved.
