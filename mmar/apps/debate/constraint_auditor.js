function normalizeAuditText(value) {
  return String(value || "").trim();
}

function extractPropositionConstraints(topic) {
  const text = normalizeAuditText(topic);
  return {
    subject: /(人間|大学|仮想通貨|AI|作者|読者|BOT)/.exec(text)?.[0] || "",
    timeframe: /(昔のように|これから|今|短期|長期)/.exec(text)?.[0] || "",
    condition: /(BOT|AI時代|分散|作者性|短期投資)/.exec(text)?.[0] || "",
  };
}

function candidateViolationType(topic, speech) {
  const proposition = normalizeAuditText(topic);
  const text = normalizeAuditText(speech);
  if (!text) return "";
  if (/人間/.test(proposition) && /(一部の人間|一部の強い人|例外的な人|プロだけ)/.test(text)) return "subject_narrowing";
  if (/(短期|昔のように)/.test(proposition) && /(長期|中期|数年|長い目)/.test(text)) return "timeframe_shift";
  if (/BOT/.test(proposition) && /(一般論|市場全体|いつの時代も)/.test(text)) return "condition_swap";
  if (/(勝てるか|べきか|分散しているか)/.test(proposition) && /(生き残れるか|可能性があるか|別の意味で|新しい形なら)/.test(text)) return "question_reinvention";
  return "";
}

function exposeSignal(topic, speech) {
  const proposition = normalizeAuditText(topic);
  const text = normalizeAuditText(speech);
  if (!text) return false;
  if (/(元の問い|その問いに答えていない|話をずらした|条件をすり替えた|定義をずらした|短期の話だ|人間一般の話だ)/.test(text)) return true;
  if (/BOT/.test(proposition) && /(BOTが増える前提|その環境から逃げている)/.test(text)) return true;
  return false;
}

export function detectDriftEvents(topic, turns) {
  const events = [];
  for (const turn of turns || []) {
    const aViolation = candidateViolationType(topic, turn?.a);
    if (aViolation) {
      events.push({
        turn: Number(turn?.turn) || 0,
        speaker: "A",
        type: aViolation,
        severity: "high",
        exposed_by_opponent: exposeSignal(topic, turn?.b),
      });
    }
    const bViolation = candidateViolationType(topic, turn?.b);
    if (bViolation) {
      events.push({
        turn: Number(turn?.turn) || 0,
        speaker: "B",
        type: bViolation,
        severity: "high",
        exposed_by_opponent: exposeSignal(topic, turn?.a),
      });
    }
  }
  return events;
}

export function scoreDriftPenalty(driftEvents) {
  return (driftEvents || []).reduce((acc, event) => {
    const side = String(event?.speaker || "").toUpperCase();
    if (side === "A" || side === "B") {
      const weight = event?.exposed_by_opponent ? 2 : 1;
      acc[side] += weight;
    }
    return acc;
  }, { A: 0, B: 0 });
}

export async function runConstraintAudit(topic, turns) {
  const driftEvents = detectDriftEvents(topic, turns);
  return {
    proposition_constraints: extractPropositionConstraints(topic),
    drift_events: driftEvents,
    violation_type: [...new Set(driftEvents.map((event) => event.type))],
    exposed_by_opponent: driftEvents.some((event) => event.exposed_by_opponent),
    drift_penalty: scoreDriftPenalty(driftEvents),
  };
}
