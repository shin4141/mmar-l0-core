function clone(value) {
  return JSON.parse(JSON.stringify(value || {}));
}

function winnerSide(pass1) {
  return String(pass1?.winner?.side || "Draw");
}

function losingSide(side) {
  if (side === "A") return "B";
  if (side === "B") return "A";
  return "both";
}

function textFavorsSide(text, side) {
  const value = String(text || "");
  if (!value || side === "Draw") return false;
  const other = side === "A" ? "B" : "A";
  return value.includes(`${other}が`) || value.includes(`${other}優勢`) || value.includes(`${other}を固定`);
}

function applyDriftPenalty(pass1, report, rewriteReason) {
  const aligned = clone(pass1);
  const penalties = report?.drift_penalty || { A: 0, B: 0 };
  const side = winnerSide(aligned);
  if (side !== "A" && side !== "B") return aligned;
  const loser = losingSide(side);
  const sidePenalty = penalties[side] || 0;
  const loserPenalty = penalties[loser] || 0;
  const exposed = Array.isArray(report?.drift_events) && report.drift_events.some((event) => event.exposed_by_opponent);
  if (exposed && sidePenalty > loserPenalty) {
    aligned.winner = {
      side: loser,
      reason: `${loser}が元の問いを守り、${side}の命題逸脱を突いた。`,
    };
    aligned.reason_one_liner = `${side}は命題からずれ、${loser}が元の問いを固定した。`;
    aligned.momentum = loser === "A" ? { a: 70, b: 30 } : { a: 30, b: 70 };
    rewriteReason.push("drift penalty flipped locked winner");
  }
  return aligned;
}

export function rewriteTakeawayIfNeeded(pass1, pass2) {
  const next = clone(pass2?.gemini_takeaway || {});
  const side = winnerSide(pass1);
  if (side === "Draw") return next;
  if (!textFavorsSide(next.debate_dynamic, side) && !textFavorsSide(next.structural_explanation, side) && !textFavorsSide(next.quote, side)) {
    return next;
  }
  return {
    structural_explanation: pass1?.reason_one_liner || `${side}が最後に主導権を保った。`,
    debate_dynamic: `流れが揺れても、最終的に${side}が押し返した。`,
    quote: `「最後に残ったのは${side}の論理だ。」`,
  };
}

export function rewriteFatalIfNeeded(pass1, pass2) {
  const next = clone(pass2?.fatal_phrase || {});
  const side = winnerSide(pass1);
  if (side === "Draw" || !next?.speaker || next.speaker === side) return next;
  return {
    ...next,
    speaker: side,
    reason: `${side}が最後に勝敗の傾きを固定した。`,
  };
}

export function repairWeakSpotIfNeeded(pass1, pass2) {
  const next = clone(pass2?.weak_spot || {});
  const side = winnerSide(pass1);
  const loser = losingSide(side);
  if (side === "Draw" || next.side === loser) return next;
  if (!next?.side) {
    return {
      ...next,
      side: loser,
      speaker: next.speaker === "A/B" ? next.speaker : loser,
      label: next.label || "論拠不足",
      why_one_sentence: next.why_one_sentence || `${loser}の弱点が最後まで残り、勝敗に響いた。`,
      how_to_fix: next.how_to_fix || `${loser}は元の問いを守りつつ、相手の核心に先に返すべきだった。`,
    };
  }
  return {
    ...next,
    side: loser,
    speaker: next.speaker === "A/B" ? next.speaker : loser,
    why_one_sentence: `${loser}の弱点が最後まで残り、勝敗に響いた。`,
    how_to_fix: `${loser}は元の問いを守りつつ、相手の核心に先に返すべきだった。`,
  };
}

function rewriteQuoteIfNeeded(pass1, pass2) {
  const raw = clone(pass2?.gemini_quote || {});
  const side = winnerSide(pass1);
  if (side === "Draw") return raw;
  if (!textFavorsSide(raw.text, side)) return raw;
  return {
    text: `${side}が問いを守り、最後に押し切った。`,
  };
}

export function alignDebateStory(pass1, pass2, constraintReport) {
  const rewriteReason = [];
  let ruleApplied = "";
  let ruleReason = "";
  const lockedPass1 = applyDriftPenalty(pass1, constraintReport, rewriteReason);
  const nextTakeaway = rewriteTakeawayIfNeeded(lockedPass1, pass2);
  if (JSON.stringify(nextTakeaway) !== JSON.stringify(pass2?.gemini_takeaway || {})) {
    rewriteReason.push("takeaway contradicted locked winner");
  }
  const nextFatal = rewriteFatalIfNeeded(lockedPass1, pass2);
  if (JSON.stringify(nextFatal) !== JSON.stringify(pass2?.fatal_phrase || {})) {
    rewriteReason.push("fatal phrase favored opposite side");
  }
  const nextWeak = repairWeakSpotIfNeeded(lockedPass1, pass2);
  if (JSON.stringify(nextWeak) !== JSON.stringify(pass2?.weak_spot || {})) {
    rewriteReason.push("weak spot attribution repaired");
    ruleApplied = "repair_missing_or_winner_side_weak_spot";
    ruleReason = "weak_spot was missing or pointed at the locked winner";
  }
  const nextQuote = rewriteQuoteIfNeeded(lockedPass1, pass2);
  if (JSON.stringify(nextQuote) !== JSON.stringify(pass2?.gemini_quote || {})) {
    rewriteReason.push("quote aligned to locked winner");
  }
  const rejectedFields = [];
  if (rewriteReason.some((reason) => reason.includes("takeaway"))) rejectedFields.push("takeaway");
  if (rewriteReason.some((reason) => reason.includes("fatal"))) rejectedFields.push("fatal_phrase");
  if (rewriteReason.some((reason) => reason.includes("weak"))) rejectedFields.push("weak_spot");
  if (rewriteReason.some((reason) => reason.includes("quote"))) rejectedFields.push("gemini_quote");

  return {
    summary: {
      ...clone(pass2?.raw_summary || {}),
      winner: lockedPass1.winner,
      reason_one_liner: lockedPass1.reason_one_liner,
      confidence: lockedPass1.confidence || pass2?.raw_summary?.confidence || "Medium",
      momentum: lockedPass1.momentum,
      turning_point: pass2?.turning_point || pass2?.raw_summary?.turning_point || (lockedPass1.turning_point_turn ? `Turn ${lockedPass1.turning_point_turn}` : ""),
      fatal_phrase: nextFatal,
      weak_spot: nextWeak,
      flip_condition: pass2?.flip_condition || pass2?.raw_summary?.flip_condition || "",
      gemini_takeaway: nextTakeaway,
      gemini_quote: nextQuote,
      constraint_report: clone(constraintReport),
    },
    report: {
      winner_lock_source: "judge_pass1",
      rejected_fields: rejectedFields,
      rewrite_reason: rewriteReason,
      rule_applied: ruleApplied,
      rule_reason: ruleReason,
    },
  };
}
