# MMAR Normative Judge Baseline v44

## Status

- This snapshot freezes the current normative judge as the clean live baseline.
- From this point, the lane is `final_surface_check`, not further bias patching.
- The baseline is accepted from clean live runs only.

## Frozen Outcome Set

- `life_pricing_base = B`
- `life_pricing_swapped = Draw`
- `love_money_base = B`
- `love_money_swapped = A`
- `private_violence_base = Draw`
- `private_violence_swapped = Draw`
- `sora_video_base = A`
- `sora_video_swapped = Draw`

## Judge Shape

- Core judge path is `scorecard_v1_shadow`.
- Gemini scores side A and side B separately on:
  - `self_integrity`
  - `opponent_core_damage`
  - `type_mismatch_hit`
  - `drift_penalty`
  - `closure_bonus`
- Code computes the winner from the scorecard.

## Scorecard Intent

- `opponent_core_damage = 3` is reserved for actual constitutive or necessary-condition breaks.
- `closure_bonus` is narrow and secondary. It is not awarded for tidy rebuttal alone.
- `drift_penalty` does not fire merely for explaining urgency, victim abandonment, institutional failure, or limited handoff-oriented defensive framing.
- `type_mismatch_hit` includes normative/descriptive mismatch and related category errors, but is not intended to dominate by itself.

## Draw Tiebreak

- Draw tiebreak is narrow and schema-driven.
- It runs only when the scorecard winner is `Draw`.
- It requires all of the following:
  - `normative_superiority_side = A` or `B`
  - `bridge_valid = yes`
  - `constitutive_break_side = normative_superiority_side`
  - `constitutive_break_confidence >= 1`
  - `block_tiebreak_reason = none`
- Otherwise it is no-op.

## Blind Explanation Schema

- `causal_legibility_side`
- `structural_failure_side`
- `normative_superiority_side`
- `bridge_valid`
- `bridge_reason`
- `constitutive_break_side`
- `constitutive_break_confidence`
- Legacy free-text explanation fields remain, but schema is preferred.

## Behavioral Summary

- `private_violence` is allowed to remain `Draw` when the system understands the background but should not convert that understanding into winnerization.
- `sora_video_base` is allowed to resolve from `Draw` to `A` when the blind explanation sees a viability or strategy constitutive break.
- `Draw` is treated as a valid hold outcome, not an automatic defect.

## Phase Marker

This baseline is frozen. Subsequent work should focus on surface readability, UI meaning, and public precheck rather than further fairness patches.
