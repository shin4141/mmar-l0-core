from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "mmar" / "apps" / "debate" / "debate.js"
AUDITOR_PATH = ROOT / "mmar" / "apps" / "debate" / "constraint_auditor.js"
ALIGNER_PATH = ROOT / "mmar" / "apps" / "debate" / "story_aligner.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _clone(value):
    return deepcopy(value or {})


def _winner_side(pass1):
    return str((pass1 or {}).get("winner", {}).get("side", "Draw"))


def _losing_side(side):
    if side == "A":
        return "B"
    if side == "B":
        return "A"
    return "both"


def _text_favors_side(text, side):
    value = str(text or "")
    if not value or side == "Draw":
        return False
    other = "B" if side == "A" else "A"
    return f"{other}が" in value or f"{other}優勢" in value or f"最後に残ったのは{other}" in value


def _apply_drift_penalty(pass1, report, rewrite_reason):
    aligned = _clone(pass1)
    penalties = (report or {}).get("drift_penalty", {"A": 0, "B": 0})
    side = _winner_side(aligned)
    if side not in {"A", "B"}:
        return aligned
    loser = _losing_side(side)
    side_penalty = penalties.get(side, 0)
    loser_penalty = penalties.get(loser, 0)
    exposed = any(event.get("exposed_by_opponent") for event in (report or {}).get("drift_events", []))
    if exposed and side_penalty > loser_penalty:
        aligned["winner"] = {
            "side": loser,
            "reason": f"{loser}が元の問いを守り、{side}の命題逸脱を突いた。",
        }
        aligned["reason_one_liner"] = f"{side}は命題からずれ、{loser}が元の問いを固定した。"
        aligned["momentum"] = {"a": 70, "b": 30} if loser == "A" else {"a": 30, "b": 70}
        rewrite_reason.append("drift penalty flipped locked winner")
    return aligned


def _rewrite_takeaway_if_needed(pass1, pass2):
    next_takeaway = _clone((pass2 or {}).get("gemini_takeaway", {}))
    side = _winner_side(pass1)
    if side == "Draw":
        return next_takeaway
    if not (
        _text_favors_side(next_takeaway.get("debate_dynamic"), side)
        or _text_favors_side(next_takeaway.get("structural_explanation"), side)
        or _text_favors_side(next_takeaway.get("quote"), side)
    ):
        return next_takeaway
    return {
        "structural_explanation": (pass1 or {}).get("reason_one_liner") or f"{side}が最後に主導権を保った。",
        "debate_dynamic": f"流れが揺れても、最終的に{side}が押し返した。",
        "quote": f"「最後に残ったのは{side}の論理だ。」",
    }


def _rewrite_fatal_if_needed(pass1, pass2):
    next_fatal = _clone((pass2 or {}).get("fatal_phrase", {}))
    side = _winner_side(pass1)
    if side == "Draw" or not next_fatal.get("speaker") or next_fatal.get("speaker") == side:
        return next_fatal
    next_fatal["speaker"] = side
    next_fatal["reason"] = f"{side}が最後に勝敗の傾きを固定した。"
    return next_fatal


def _repair_weak_spot_if_needed(pass1, pass2):
    next_weak = _clone((pass2 or {}).get("weak_spot", {}))
    side = _winner_side(pass1)
    loser = _losing_side(side)
    if side == "Draw" or next_weak.get("side") == loser:
        return next_weak
    if not next_weak.get("side"):
        next_weak["side"] = loser
        next_weak["speaker"] = next_weak.get("speaker") if next_weak.get("speaker") == "A/B" else loser
        next_weak["label"] = next_weak.get("label") or "論拠不足"
        next_weak["why_one_sentence"] = next_weak.get("why_one_sentence") or f"{loser}の弱点が最後まで残り、勝敗に響いた。"
        next_weak["how_to_fix"] = next_weak.get("how_to_fix") or f"{loser}は元の問いを守りつつ、相手の核心に先に返すべきだった。"
        return next_weak
    next_weak["side"] = loser
    next_weak["speaker"] = next_weak.get("speaker") if next_weak.get("speaker") == "A/B" else loser
    next_weak["why_one_sentence"] = f"{loser}の弱点が最後まで残り、勝敗に響いた。"
    next_weak["how_to_fix"] = f"{loser}は元の問いを守りつつ、相手の核心に先に返すべきだった。"
    return next_weak


def _align_story(pass1, pass2, constraint_report):
    rewrite_reason = []
    locked_pass1 = _apply_drift_penalty(pass1, constraint_report, rewrite_reason)
    next_takeaway = _rewrite_takeaway_if_needed(locked_pass1, pass2)
    if next_takeaway != _clone((pass2 or {}).get("gemini_takeaway", {})):
        rewrite_reason.append("takeaway contradicted locked winner")
    next_fatal = _rewrite_fatal_if_needed(locked_pass1, pass2)
    if next_fatal != _clone((pass2 or {}).get("fatal_phrase", {})):
        rewrite_reason.append("fatal phrase favored opposite side")
    next_weak = _repair_weak_spot_if_needed(locked_pass1, pass2)
    if next_weak != _clone((pass2 or {}).get("weak_spot", {})):
        rewrite_reason.append("weak spot attribution repaired")
    return {
        "summary": {
            "winner": locked_pass1["winner"],
            "reason_one_liner": locked_pass1.get("reason_one_liner"),
            "momentum": locked_pass1.get("momentum"),
            "fatal_phrase": next_fatal,
            "weak_spot": next_weak,
            "gemini_takeaway": next_takeaway,
        },
        "report": {
            "winner_lock_source": "judge_pass1",
            "rewrite_reason": rewrite_reason,
        },
    }


def test_debate_js_runs_constraint_then_passes_then_alignment():
    js = _read(JS_PATH)

    assert 'import { runConstraintAudit } from "./constraint_auditor.js";' in js
    assert 'import { alignDebateStory } from "./story_aligner.js";' in js
    assert "currentConstraintReport = await runConstraintAudit" in js
    assert "currentJudgePass1 = await runJudgePass1" in js
    assert "currentJudgePass2 = await runJudgePass2" in js
    assert "const aligned = alignDebateStory(currentJudgePass1, currentJudgePass2, currentConstraintReport);" in js
    assert "currentStoryAlignReport = aligned.report;" in js
    assert "currentResult.debate.summary = {" in js
    assert "debug_constraint_report: currentConstraintReport" in js
    assert "debug_pass1: currentJudgePass1" in js
    assert "debug_pass2: currentJudgePass2" in js
    assert "debug_story_align_report: currentStoryAlignReport" in js


def test_debate_js_locks_winner_in_pass1_and_uses_aligned_summary():
    js = _read(JS_PATH)

    assert "async function runJudgePass1(transcript, constraintReport)" in js
    assert "async function runJudgePass2(transcript, pass1, constraintReport)" in js
    assert "const rawSummary = currentResult?.debate?.raw_summary || currentResult?.debate?.summary || {};" in js
    assert "let lockedWinner = { ...winner };" in js
    assert "if (exposed && lockedWinner.side === \"A\" && penalties.A > penalties.B)" in js
    assert "if (exposed && lockedWinner.side === \"B\" && penalties.B > penalties.A)" in js
    assert "renderSummary(debate.summary || {});" in js


def test_constraint_auditor_emits_drift_penalty_and_violation_types():
    auditor = _read(AUDITOR_PATH)

    assert "export async function runConstraintAudit(topic, turns)" in auditor
    assert "export function detectDriftEvents(topic, turns)" in auditor
    assert "export function scoreDriftPenalty(driftEvents)" in auditor
    assert '"subject_narrowing"' in auditor
    assert '"timeframe_shift"' in auditor
    assert '"condition_swap"' in auditor
    assert '"question_reinvention"' in auditor
    assert "drift_penalty:" in auditor


def test_story_aligner_repairs_takeaway_fatal_and_weak_spot():
    aligner = _read(ALIGNER_PATH)

    assert "export function alignDebateStory(pass1, pass2, constraintReport)" in aligner
    assert "export function rewriteTakeawayIfNeeded(pass1, pass2)" in aligner
    assert "export function rewriteFatalIfNeeded(pass1, pass2)" in aligner
    assert "export function repairWeakSpotIfNeeded(pass1, pass2)" in aligner
    assert '"takeaway contradicted locked winner"' in aligner
    assert '"fatal phrase favored opposite side"' in aligner
    assert '"weak spot attribution repaired"' in aligner
    assert '"drift penalty flipped locked winner"' in aligner
    assert 'if (!next?.side)' in aligner
    assert 'rule_applied: ruleApplied' in aligner
    assert 'rule_reason: ruleReason' in aligner
    assert '"repair_missing_or_winner_side_weak_spot"' in aligner
    assert '"weak_spot was missing or pointed at the locked winner"' in aligner


def test_ask_uses_aligned_summary_via_current_battle_record():
    js = _read(JS_PATH)

    assert "function getCurrentBattleRecord()" in js
    assert "return buildBattleRecord(currentResult, currentPayload);" in js
    assert 'body: JSON.stringify({' in js
    assert "match: record," in js


def test_artificial_case_takeaway_mismatch_is_aligned_to_locked_winner():
    pass1 = {
        "winner": {"side": "A", "reason": "Aが押し切った。"},
        "reason_one_liner": "Aが押し切った。",
        "momentum": {"a": 60, "b": 40},
    }
    pass2 = {
        "gemini_takeaway": {
            "structural_explanation": "Bが議論の焦点を変えた。",
            "debate_dynamic": "最終的にBが押し返した。",
            "quote": "「最後に残ったのはBだ。」",
        }
    }
    aligned = _align_story(pass1, pass2, {"drift_events": [], "drift_penalty": {"A": 0, "B": 0}})
    takeaway = aligned["summary"]["gemini_takeaway"]
    assert takeaway["structural_explanation"] == "Aが押し切った。"
    assert takeaway["debate_dynamic"] == "流れが揺れても、最終的にAが押し返した。"
    assert "takeaway contradicted locked winner" in aligned["report"]["rewrite_reason"]


def test_artificial_case_drift_penalty_flips_winner_when_exposed():
    pass1 = {
        "winner": {"side": "A", "reason": "Aが勢いで押した。"},
        "reason_one_liner": "Aが勢いで押した。",
        "momentum": {"a": 60, "b": 40},
    }
    pass2 = {}
    constraint_report = {
        "drift_events": [
            {"turn": 5, "speaker": "A", "type": "timeframe_shift", "severity": "high", "exposed_by_opponent": True}
        ],
        "drift_penalty": {"A": 2, "B": 0},
    }
    aligned = _align_story(pass1, pass2, constraint_report)
    assert aligned["summary"]["winner"]["side"] == "B"
    assert aligned["summary"]["momentum"] == {"a": 30, "b": 70}
    assert "drift penalty flipped locked winner" in aligned["report"]["rewrite_reason"]


def test_artificial_case_fatal_phrase_opposite_side_is_rewritten():
    pass1 = {
        "winner": {"side": "A", "reason": "Aが押し切った。"},
        "reason_one_liner": "Aが押し切った。",
        "momentum": {"a": 60, "b": 40},
    }
    pass2 = {
        "fatal_phrase": {
            "turn": 4,
            "speaker": "B",
            "text": "Bの一撃",
            "reason": "Bが決めた。",
        }
    }
    aligned = _align_story(pass1, pass2, {"drift_events": [], "drift_penalty": {"A": 0, "B": 0}})
    fatal = aligned["summary"]["fatal_phrase"]
    assert fatal["speaker"] == "A"
    assert fatal["reason"] == "Aが最後に勝敗の傾きを固定した。"
    assert "fatal phrase favored opposite side" in aligned["report"]["rewrite_reason"]
