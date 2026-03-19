import { runConstraintAudit } from "./constraint_auditor.js";
import { alignDebateStory } from "./story_aligner.js";

const form = document.querySelector("#debate-form");
const runButton = document.querySelector("#run-button");
const judgeButton = document.querySelector("#judge-button");
const saveButton = document.querySelector("#save-button");
const historyButton = document.querySelector("#history-button");
const archiveButton = document.querySelector("#archive-button");
const historyCloseButton = document.querySelector("#history-close-button");
const historyBackdrop = document.querySelector("#history-backdrop");
const archiveCloseButton = document.querySelector("#archive-close-button");
const archiveBackdrop = document.querySelector("#archive-backdrop");
const askCloseButton = document.querySelector("#ask-close-button");
const askBackdrop = document.querySelector("#ask-backdrop");
const viewerLibraryEl = document.querySelector("#viewer-library");
const viewerListEl = document.querySelector("#viewer-list");
const viewerCountEl = document.querySelector("#viewer-count");
const viewerFeedbackInputEl = document.querySelector("#viewer-feedback-input");
const viewerFeedbackButton = document.querySelector("#viewer-feedback-button");
const viewerTopicButton = document.querySelector("#viewer-topic-button");
const viewerFeedbackStatusEl = document.querySelector("#viewer-feedback-status");
const statusRowEl = document.querySelector(".status-row");
const statusEl = document.querySelector("#status");
const errorHintEl = document.querySelector("#error-hint");
const topicDisplayEl = document.querySelector("#topic-display");
const runMetaEl = document.querySelector("#run-meta");
const outputMetaEl = document.querySelector("#output-meta");
const turnLogEl = document.querySelector("#turn-log");
const outputPanelEl = document.querySelector(".output-panel");
const pageShellEl = document.querySelector(".page-shell");
const apiBaseInput = document.querySelector("#api-base");
const fighterAProviderInput = document.querySelector("#fighter-a-provider");
const fighterBProviderInput = document.querySelector("#fighter-b-provider");
const historyShellEl = document.querySelector("#history-shell");
const historyPanelEl = document.querySelector("#history-panel");
const historyCountEl = document.querySelector("#history-count");
const historyListEl = document.querySelector("#history-list");
const archiveShellEl = document.querySelector("#archive-shell");
const archivePanelEl = document.querySelector("#archive-panel");
const archiveCountEl = document.querySelector("#archive-count");
const archiveRecentCountEl = document.querySelector("#archive-recent-count");
const archiveSavedCountEl = document.querySelector("#archive-saved-count");
const archiveSearchEl = document.querySelector("#archive-search");
const archiveRecentListEl = document.querySelector("#archive-recent-list");
const archiveListEl = document.querySelector("#archive-list");
const askShellEl = document.querySelector("#ask-shell");
const askPanelEl = document.querySelector("#ask-panel");
const askMatchChipEl = document.querySelector("#ask-match-chip");
const askThreadEl = document.querySelector("#ask-thread");
const askFormEl = document.querySelector("#ask-form");
const askInputEl = document.querySelector("#ask-input");
const askStatusEl = document.querySelector("#ask-status");
const askSendButton = document.querySelector("#ask-send-button");
const debugPipelinePanelEl = document.querySelector("#debug-pipeline-panel");
const debugConstraintReportEl = document.querySelector("#debug-constraint-report");
const debugJudgePass1El = document.querySelector("#debug-judge-pass1");
const debugJudgePass2El = document.querySelector("#debug-judge-pass2");
const debugStoryAlignReportEl = document.querySelector("#debug-story-align-report");
const mobileMedia = window.matchMedia("(max-width: 768px)");

let healthCheckTimer = null;
let currentResult = null;
let currentPayload = null;
let analysisHidden = true;
let currentFighters = { a: "openai", b: "anthropic", judge: "gemini" };
let currentRecordId = null;
let verdictStripEl = null;
let geminiQuoteEl = null;
let analysisPanelEl = null;
let verdictGridEl = null;
let spotlightGridEl = null;
let detailPanelEl = null;
let currentAskMessages = [];
let currentAskContextKey = null;
const dismissedAskHints = new Set();
let activeJumpTimer = null;
let archiveModeFilter = "all";
let currentLoadedRecord = null;
let curatedViewerRecords = [];
let mobileAnalysisCollapsed = true;
let historyRecordsCache = [];
let historyRecordsHydrated = false;
let historyFetchInFlight = false;
let currentConstraintReport = null;
let currentJudgePass1 = null;
let currentJudgePass2 = null;
let currentStoryAlignReport = null;

const queryParams = new URLSearchParams(window.location.search);
const VIEWER_MODE = queryParams.get("viewer") === "1" || queryParams.get("demo") === "1";

const HISTORY_STORAGE_KEY = "mmar.debate.history.v1";
const VIEWER_ARCHIVE_URL = "./fixtures/viewer_archive.json";
const MODEL_LABELS = {
  openai: "GPT-5-mini",
  anthropic: "Claude Sonnet 4.5",
  gemini: "Gemini 2.5 Flash",
};

function isMobileLayout() {
  return mobileMedia.matches;
}

function syncMobileLayoutClass() {
  document.body.classList.toggle("mobile-ui", isMobileLayout());
}

function setStatus(kind, text) {
  statusEl.className = `status ${kind}`;
  statusEl.textContent = text;
  statusEl.hidden = kind === "idle" || kind === "ok";
  refreshStatusRow();
}

function setHint(text) {
  errorHintEl.textContent = text;
  errorHintEl.hidden = !text;
  refreshStatusRow();
}

function setRunMeta(text, visible) {
  runMetaEl.textContent = text;
  runMetaEl.hidden = !visible;
}

function refreshStatusRow() {
  statusRowEl.hidden = statusEl.hidden && errorHintEl.hidden;
}

function setRevealState(hidden) {
  analysisHidden = hidden;
  if (hidden) {
    setHint("");
  }
  saveButton.hidden = hidden;
  saveButton.disabled = hidden || !currentResult;
  if (hidden) {
    toggleAskPanel(false);
    destroyVerdictStrip();
    destroyGeminiQuote();
    destroyAnalysisPanel();
  } else {
    ensureVerdictStrip();
    ensureGeminiQuote();
    ensureAnalysisPanel();
    syncMobileAnalysisPanel();
    syncSaveButton();
    syncAskButton();
  }
}

function setReadingMode(active) {
  pageShellEl.classList.toggle("reading-mode", active);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeArrayValue(value) {
  if (Array.isArray(value)) {
    return value.map((item, index) => `${index + 1}. ${item}`).join("\n");
  }
  return String(value ?? "未生成");
}

function normalizeFatalPhrase(summary) {
  const value = summary?.fatal_phrase;
  const winnerSide = normalizeWinner(summary).side;
  const turning = normalizeTurningPoint(summary);
  if (!value) {
    return {
      turn: extractTurnNumber(turning.turn) || 3,
      speaker: winnerSide === "Draw" ? "A/B" : "?",
      quote: winnerSide === "Draw" ? "「単独の決定打はなかったが、この応酬が最も勝負を動かした。」" : "「この場面で相手の穴が最もはっきり見えた。」",
      why: winnerSide === "Draw" ? "流れは動いたが、どちらもここから決め切れなかった。" : "この場面で勝敗の傾きが固まった。",
    };
  }
  if (typeof value === "string") {
    return {
      turn: extractTurnNumber(turning.turn) || 3,
      speaker: winnerSide === "Draw" ? "A/B" : "?",
      quote: `「${value}」`,
      why: winnerSide === "Draw" ? "この応酬が最も流れを動かした。" : "この一文が勝敗の傾きを決めた。",
    };
  }
  return {
    turn: Number(value.turn) || extractTurnNumber(turning.turn) || 3,
    speaker: value.speaker || (winnerSide === "Draw" ? "A/B" : "?"),
    quote: value.text ? `「${value.text}」` : (winnerSide === "Draw" ? "「単独の決定打はなかったが、この応酬が最も勝負を動かした。」" : "「この場面で相手の穴が最もはっきり見えた。」"),
    why: value.reason || (winnerSide === "Draw" ? "流れは動いたが、どちらもここから決め切れなかった。" : "この一文が勝敗の傾きを決めた。"),
  };
}

function normalizeWinner(summary) {
  const raw = summary?.winner;
  let side = typeof raw === "object" ? raw?.side : raw;
  const reason = typeof raw === "object" ? raw?.reason : summary?.reason_one_liner;
  const lowered = String(side || "").trim().toLowerCase();
  if (["a", "fighter a", "gpt"].includes(lowered)) side = "A";
  else if (["b", "fighter b", "claude"].includes(lowered)) side = "B";
  else if (["draw", "tie", "undecidable", "cannot decide", "引き分け", "互角", "五分"].includes(lowered)) side = "Draw";
  else side = inferWinnerFromSummary(summary, reason);
  return {
    side: side || "Draw",
    reason: reason || summary?.reason_one_liner || (side === "Draw" ? "流れは動いたが、どちらも決定打を押し切れませんでした。" : "押し込みは見えたが、最後の決め手までは届きませんでした。"),
  };
}

function inferWinnerFromSummary(summary, reason = "") {
  const combined = [
    summary?.reason_one_liner,
    summary?.provisional_judgment,
    reason,
    summary?.full_rationale,
  ].filter(Boolean).join(" ");
  const text = String(combined || "");
  if (/(引き分け|互角|五分|決め切れない|決めきれない|cannot decide|undecidable|\bdraw\b|\btie\b)/i.test(text)) return "Draw";
  if (/(A優勢|Aが押した|Aが押し切|Aが守り切|Bが崩れ|Bが後退|Aの方|Aが)/.test(text)) return "A";
  if (/(B優勢|Bが押した|Bが押し切|Bが守り切|Aが崩れ|Aが後退|Bの方|Bが)/.test(text)) return "B";
  const fatalSpeaker = String(summary?.fatal_phrase?.speaker || "").trim().toUpperCase();
  const weakSpeaker = String(summary?.weak_spot?.speaker || "").trim().toUpperCase();
  if (weakSpeaker === "A" || fatalSpeaker === "B") return "B";
  if (weakSpeaker === "B" || fatalSpeaker === "A") return "A";
  const flip = String(summary?.flip_condition || "");
  if (flip.includes("Aが戻る") || flip.includes("Aが返す")) return "B";
  if (flip.includes("Bが戻る") || flip.includes("Bが返す")) return "A";
  return "Draw";
}

function normalizeWeakSpot(summary) {
  const raw = summary?.weak_spot;
  const winnerSide = normalizeWinner(summary).side;
  const defaultSide = winnerSide === "Draw" ? "both" : (winnerSide === "A" ? "B" : "A");
  const defaultSpeaker = winnerSide === "Draw" ? "A/B" : defaultSide;
  const defaultLabel = winnerSide === "Draw" ? "Why it stayed unresolved" : "論拠不足";
  const defaultWhy = winnerSide === "Draw"
    ? "A/Bともに相手の核を崩し切れず、決着に届かなかった。"
    : `${defaultSide}は勝負を決める根拠を最後まで守れなかった。`;
  const defaultFix = winnerSide === "Draw"
    ? "相手の核を崩す一手を一つに絞って、そこへ証拠を足すべきだった。"
    : "抽象的に守るのではなく、相手の核心を崩す具体例か基準を先に置くべきだった。";
  const defaultTurn = extractTurnNumber(summary?.turning_point || summary?.fatal_phrase) || 3;
  if (raw && typeof raw === "object") {
    return {
      side: raw.side || defaultSide,
      turn: Number(raw.turn) || defaultTurn,
      speaker: raw.speaker || defaultSpeaker,
      label: raw.label || defaultLabel,
      quote_excerpt: raw.quote_excerpt || raw.quote || raw.text || "相手に最も刺された弱点がここで露出した。",
      why_one_sentence: raw.why_one_sentence || raw.why || defaultWhy,
      how_to_fix: raw.how_to_fix || defaultFix,
    };
  }
  return {
    side: defaultSide,
    turn: defaultTurn,
    speaker: defaultSpeaker,
    label: defaultLabel,
    quote_excerpt: summary?.contradiction_exposed || "相手に最も刺された弱点がここで露出した。",
    why_one_sentence: summary?.contradiction_exposed || defaultWhy,
    how_to_fix: defaultFix,
  };
}

function normalizeTurningPoint(value) {
  const raw = typeof value === "object" && !Array.isArray(value) && value?.turning_point ? value.turning_point : value;
  const winnerSide = typeof value === "object" && !Array.isArray(value) ? normalizeWinner(value).side : "Draw";
  const turn = extractTurnNumber(raw);
  return {
    turn: turn ? `Turn ${turn}` : "Turn ?",
    summary: raw ? normalizeArrayValue(raw) : (winnerSide === "Draw" ? "流れは動いたが、どちらも決定打を最後まで押し切れなかった。" : "流れが変わった場所は見えている。"),
  };
}

function normalizeGeminiTakeaway(summary, topic = "") {
  const winner = normalizeWinner(summary);
  const why = summary?.reason_one_liner || winner.reason;
  const turning = normalizeTurningPoint(summary);
  const weakSpot = normalizeWeakSpot(summary);
  const raw = summary?.gemini_takeaway;
  if (raw && typeof raw === "object") {
    const structural = String(raw.structural_explanation || "").trim();
    const dynamic = String(raw.debate_dynamic || "").trim();
    const quote = normalizeTakeawayQuote(raw.quote);
    if (structural && dynamic && quote) {
      return {
        structural_explanation: structural,
        debate_dynamic: dynamic,
        quote,
      };
    }
  }
  if (winner.side === "A") {
    return {
      structural_explanation: why || "Aは相手の核を崩し、判定基準を握った。",
      debate_dynamic: `${turning.summary}`,
      quote: "「基準を握った側が、議論を支配する。」",
    };
  }
  if (winner.side === "B") {
    return {
      structural_explanation: why || "Bは相手の弱点を閉じずに残し、勝負を握った。",
      debate_dynamic: `${turning.summary}`,
      quote: normalizeTakeawayQuote(summary?.weak_spot?.label ? `「${summary.weak_spot.label}を突いた側が残る。」` : "「きれいな理屈でも、穴があれば崩れる。」"),
    };
  }
  return {
    structural_explanation: "流れは動いたが、どちらも決着まで押し切れなかった。",
    debate_dynamic: `${turning.summary}`,
    quote: "「流れは揺れたが、決着は届かなかった。」",
  };
}

function normalizeTakeawayQuote(value) {
  const quote = String(value || "").trim();
  if (!quote) return "";
  return quote.startsWith("「") ? quote : `「${quote.replace(/^「|」$/g, "")}」`;
}

function normalizeGeminiQuote(summary) {
  const raw = summary?.gemini_quote;
  if (raw && typeof raw === "object" && String(raw.text || "").trim()) {
    const text = String(raw.text || "").trim();
    if (!looksLikeGenericGeminiQuote(text)) return normalizeTakeawayQuote(text);
  }
  const winner = normalizeWinner(summary);
  const weakSpot = normalizeWeakSpot(summary);
  const turning = normalizeTurningPoint(summary);
  const concepts = extractGeminiQuoteConcepts(summary, turning, weakSpot);
  const primary = concepts[0] || "";
  const secondary = concepts[1] || "";
  const label = String(weakSpot.label || "");
  if (label === "定義の後退" && primary && secondary) return normalizeTakeawayQuote(`${primary}を広げても、${secondary}は守れない。`);
  if (label === "循環論法" && primary) return normalizeTakeawayQuote(`${primary}の言い換えでは、穴は埋まらない。`);
  if (label === "未応答" && primary) return normalizeTakeawayQuote(`${primary}に答えないままでは、勝ちは作れない。`);
  if (winner.side === "Draw" && primary && secondary) return normalizeTakeawayQuote(`${primary}は揺れたが、${secondary}までは折れなかった。`);
  if (winner.side === "A" && primary && secondary) return normalizeTakeawayQuote(`${primary}は残り、${secondary}が先に崩れた。`);
  if (winner.side === "B" && primary && secondary) return normalizeTakeawayQuote(`${primary}は残らず、${secondary}が最後まで刺さった。`);
  if (primary) return normalizeTakeawayQuote(`${primary}を守れない理屈は、長く持たない。`);
  return "「その試合の穴を突いた側が残った。」";
}

function looksLikeGenericGeminiQuote(text) {
  const value = String(text || "");
  return [
    "基準を握った側が議論を支配する",
    "定義を握った側が勝つ",
    "ルールを作る側が有利",
    "whoever controls the definition wins",
    "whoever sets the rules wins",
  ].some((phrase) => value.includes(phrase));
}

function extractGeminiQuoteConcepts(summary, turning, weakSpot) {
  const sources = [
    String(summary?.fatal_phrase?.text || ""),
    String(weakSpot?.quote_excerpt || ""),
    String(weakSpot?.why_one_sentence || ""),
    String(turning?.summary || ""),
    String(summary?.reason_one_liner || ""),
  ];
  const stopwords = new Set(["こと", "それ", "これ", "ため", "もの", "よう", "相手", "自分", "議論", "論点", "理由", "可能", "必要", "基準", "定義", "ルール", "勝負", "支配", "決着"]);
  const concepts = [];
  for (const source of sources) {
    const matches = source.match(/[A-Za-z]{3,}|[一-龥]{2,}|[ァ-ヶー]{2,}/g) || [];
    for (const match of matches) {
      const term = match.trim();
      if (!term || stopwords.has(term) || /^(Turn|\d+|A|B|A\/B)$/i.test(term)) continue;
      if (!concepts.includes(term)) concepts.push(term);
      if (concepts.length >= 4) return concepts;
    }
  }
  return concepts;
}

function normalizeDetailList(value) {
  if (Array.isArray(value)) return value;
  if (value == null) return [];
  return [String(value)];
}

function providerModeForSide(providerStatuses, providerKey) {
  return providerStatuses?.[providerKey]?.mode || "mock";
}

function modelLabelForProvider(providerKey) {
  return MODEL_LABELS[providerKey] || providerKey;
}

function providerBadgeLabel(providerStatuses) {
  const providers = providerStatuses || {};
  const aMode = providerModeForSide(providers, currentFighters.a);
  const bMode = providerModeForSide(providers, currentFighters.b);
  const jMode = providerModeForSide(providers, currentFighters.judge);
  return `A:${aMode} B:${bMode} J:${jMode}`;
}

function classifyProviderIssue(mode, reason) {
  const text = String(reason || "").trim().toLowerCase();
  if (mode === "mock") return "mock";
  if (mode === "mock-fallback") {
    if (text.includes("timeout")) return "timeout";
    if (text.includes("provider_error")) return "provider_error";
    if (text.includes("schema")) return "schema_mismatch";
    if (text.includes("json")) return "json_parse_error";
    if (text.includes("auth")) return "auth_error";
    if (text.includes("model")) return "model_not_found";
    return "fallback";
  }
  if (mode === "live-ready") return "pending";
  return mode || "unknown";
}

function formatProviderToken(label, providerKey, providerStatuses) {
  const info = providerStatuses?.[providerKey] || {};
  const mode = info.mode || "mock";
  if (mode === "live") return `${label} live`;
  return `${label} ${classifyProviderIssue(mode, info.reason)}`;
}

function normalizeSavedOutputMeta(savedOutputMeta) {
  if (savedOutputMeta && typeof savedOutputMeta === "object") {
    const judgeMode = String(savedOutputMeta.judge_mode || "").trim();
    const judgeReason = String(savedOutputMeta.judge_reason || "").trim();
    const judgeStage = String(savedOutputMeta.judge_stage || "").trim();
    const judgeProvider = String(savedOutputMeta.judge_provider || "gemini").trim();
    const judgeRaw = savedOutputMeta.judge_raw_received === true ? "raw:yes" : "raw:no";
    const judgeParse = savedOutputMeta.judge_parse_success === true ? "parse:yes" : "parse:no";
    const tokens = [
      judgeProvider && `judge ${judgeProvider}`,
      judgeMode,
      judgeReason,
      judgeStage && `@ ${judgeStage}`,
      judgeRaw,
      judgeParse,
    ].filter(Boolean);
    return tokens.join(" · ");
  }
  const text = String(savedOutputMeta || "").trim();
  if (!text) return "";
  if (!text.includes("/")) return text;
  const match = text.match(/^(\d+\s+turns)\s*\/\s*A:([a-z-]+)\s+B:([a-z-]+)\s+J:([a-z-]+)$/i);
  if (!match) return text;
  const [, turns, aMode, bMode, jMode] = match;
  return `${turns} · A ${aMode.toLowerCase()} · B ${bMode.toLowerCase()} · J ${jMode.toLowerCase()}`;
}

function buildOutputMeta(providerStatuses, turnCount, mode, savedOutputMeta = "") {
  const normalizedSavedOutputMeta = normalizeSavedOutputMeta(savedOutputMeta);
  if (normalizedSavedOutputMeta) return normalizedSavedOutputMeta;
  const countText = `${turnCount} turns`;
  const tokens = [
    formatProviderToken("A", currentFighters.a, providerStatuses),
    formatProviderToken("B", currentFighters.b, providerStatuses),
    formatProviderToken("J", currentFighters.judge, providerStatuses),
  ];
  return [countText, ...tokens].join(" · ");
}

function buildAbnormalHint(providerStatuses) {
  const parts = [];
  for (const [label, key] of [["A", currentFighters.a], ["B", currentFighters.b], ["J", currentFighters.judge]]) {
    const info = providerStatuses?.[key] || {};
    const mode = info.mode || "mock";
    if (mode === "live") continue;
    parts.push(`${label}: ${classifyProviderIssue(mode, info.reason)}`);
  }
  return parts.join(" / ");
}

function composeMomentumSplit(winnerSide, confidence) {
  if (winnerSide === "Draw") return { a: 50, b: 50 };
  const swing = confidence === "High" ? 16 : confidence === "Medium" ? 10 : 4;
  if (winnerSide === "A") return { a: 50 + swing, b: 50 - swing };
  return { a: 50 - swing, b: 50 + swing };
}

function normalizeMomentum(summary, winner, confidence) {
  const raw = summary?.momentum;
  if (raw && typeof raw === "object" && Number.isFinite(Number(raw.a)) && Number.isFinite(Number(raw.b))) {
    const aRaw = Number(raw.a);
    const bRaw = Number(raw.b);
    const total = aRaw + bRaw;
    if (total > 0) {
      const a = Math.max(0, Math.min(100, Math.round((aRaw / total) * 100)));
      const b = Math.max(0, Math.min(100, 100 - a));
      if (winner?.side === "A" && a <= b) return { a: 55, b: 45 };
      if (winner?.side === "B" && b <= a) return { a: 45, b: 55 };
      return { a, b };
    }
  }
  const inferred = winner?.side === "Draw" ? inferWinnerFromSummary(summary, winner?.reason || "") : winner?.side;
  return composeMomentumSplit(inferred || "Draw", confidence);
}

function composeFlipCondition(winner, weakSpot, why) {
  const loser = winner?.side === "A" ? "B" : winner?.side === "B" ? "A" : "A/B";
  const label = weakSpot?.label || "弱点";
  const reason = weakSpot?.how_to_fix || weakSpot?.why_one_sentence || why || "押し返しの条件が足りない。";
  if (loser === "A/B") {
    return `次にひっくり返すには、${label}を具体化して決定打に変える必要がある。`;
  }
  return `${loser}が戻るには、「${label}」を消す具体例か定義を先に出す必要がある。${reason}`;
}

function storageAvailable() {
  try {
    return Boolean(window.localStorage);
  } catch {
    return false;
  }
}

function setViewerFeedbackStatus(text) {
  viewerFeedbackStatusEl.textContent = text;
  viewerFeedbackStatusEl.hidden = !text;
}

function loadHistoryRecords() {
  return historyRecordsCache;
}

function loadHistoryRecordsFromLocalStorage() {
  if (!storageAvailable()) return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeSavedRecordForPreview) : [];
  } catch {
    return [];
  }
}

function updateHistoryButton(count = loadHistoryRecords().length) {
  historyButton.textContent = `History (${count})`;
  historyCountEl.textContent = `${count} match${count === 1 ? "" : "es"}`;
}

function persistHistoryRecords(records) {
  if (!storageAvailable()) return;
  window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(records));
}

async function fetchHistoryListFromServer() {
  const response = await fetch(endpointUrl("/api/history/list"), { method: "GET" });
  const data = await parseResponse(response);
  if (!response.ok || !data.ok || !Array.isArray(data.items)) {
    throw new Error(normalizeApiError("history_list", response.status, data));
  }
  return data.items.map(normalizeSavedRecordForPreview);
}

async function fetchHistoryRecordById(recordId) {
  try {
    const response = await fetch(endpointUrl(`/api/history/${encodeURIComponent(recordId)}`), { method: "GET" });
    const data = await parseResponse(response);
    if (!response.ok || !data.ok || !data.item) {
      throw new Error(normalizeApiError("history_item", response.status, data));
    }
    const record = normalizeSavedRecordForPreview(data.item);
    const existingIndex = historyRecordsCache.findIndex((item) => item.id === record.id);
    if (existingIndex >= 0) historyRecordsCache[existingIndex] = record;
    else historyRecordsCache.unshift(record);
    persistHistoryRecords(historyRecordsCache);
    updateHistoryButton(historyRecordsCache.length);
    updateArchiveButton(historyRecordsCache.length);
    return record;
  } catch {
    return historyRecordsCache.find((item) => item.id === recordId) || loadHistoryRecordsFromLocalStorage().find((item) => item.id === recordId) || null;
  }
}

async function refreshHistoryRecords() {
  historyFetchInFlight = true;
  renderHistoryList();
  renderArchiveList();
  try {
    historyRecordsCache = await fetchHistoryListFromServer();
    persistHistoryRecords(historyRecordsCache);
  } catch {
    historyRecordsCache = loadHistoryRecordsFromLocalStorage();
  } finally {
    historyFetchInFlight = false;
    historyRecordsHydrated = true;
  }
  updateHistoryButton(historyRecordsCache.length);
  updateArchiveButton(historyRecordsCache.length);
  renderHistoryList();
  renderArchiveList();
  return historyRecordsCache;
}

async function saveHistoryRecordToServer(record) {
  try {
    const response = await fetch(endpointUrl("/api/history/save"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(record),
    });
    const data = await parseResponse(response);
    if (!response.ok || !data.ok || !data.record) {
      throw new Error(normalizeApiError("history_save", response.status, data));
    }
    const saved = normalizeSavedRecordForPreview(data.record);
    const existingIndex = historyRecordsCache.findIndex((item) => item.id === saved.id || item.fingerprint === saved.fingerprint);
    if (existingIndex >= 0) historyRecordsCache[existingIndex] = saved;
    else historyRecordsCache.unshift(saved);
    persistHistoryRecords(historyRecordsCache);
    updateHistoryButton(historyRecordsCache.length);
    updateArchiveButton(historyRecordsCache.length);
    return saved;
  } catch {
    const records = loadHistoryRecordsFromLocalStorage();
    const existingIndex = records.findIndex((item) => item.fingerprint === record.fingerprint);
    if (existingIndex >= 0) {
      records[existingIndex] = { ...records[existingIndex], ...record, id: records[existingIndex].id };
      historyRecordsCache = records.map(normalizeSavedRecordForPreview);
      persistHistoryRecords(historyRecordsCache);
      return historyRecordsCache[existingIndex];
    }
    historyRecordsCache = [normalizeSavedRecordForPreview(record), ...records];
    persistHistoryRecords(historyRecordsCache);
    return historyRecordsCache[0];
  }
}

function normalizeSavedRecordForPreview(record) {
  if (!record || typeof record !== "object") return record;
  const summary = record.judge_json || {};
  const winner = normalizeWinner(summary);
  const confidence = summary?.confidence || "Medium";
  const why = summary?.reason_one_liner || winner.reason;
  const momentum = normalizeMomentum(summary, winner, confidence);
  const weakSpot = normalizeWeakSpot(summary);
  const topic = record.topic || "";
  return {
    ...record,
    output_meta: normalizeSavedOutputMeta(record.output_meta || ""),
    judge_json: {
      ...summary,
      winner,
      reason_one_liner: why,
      fatal_phrase: normalizeFatalPhrase(summary),
      weak_spot: weakSpot,
      turning_point: normalizeTurningPoint(summary),
      momentum,
      verdict_headline: composeVerdictHeadline(topic, winner),
      verdict_subline: composeVerdictSubline(topic, winner, why),
      flip_condition: summary?.flip_condition || composeFlipCondition(winner, weakSpot, why),
      gemini_takeaway: normalizeGeminiTakeaway(summary, topic),
      gemini_quote: summary?.gemini_quote || { text: normalizeGeminiQuote(summary) },
    },
  };
}

function matchFingerprint(result, payload) {
  const debate = result?.debate || {};
  const summary = debate.summary || {};
  return JSON.stringify({
    topic: debate.topic || payload?.topic || "",
    side_a: payload?.side_a || "",
    side_b: payload?.side_b || "",
    turn_count: debate.turn_count || payload?.turn_count || 0,
    mode: payload?.mode || "",
    fighters: currentFighters,
    winner: summary?.winner?.side || summary?.winner || "",
    turns: (debate.turns || []).map((turn) => [turn.turn, turn.a, turn.b]),
  });
}

function buildBattleRecord(result, payload) {
  const debate = result?.debate || {};
  const summary = debate.summary || {};
  const winner = normalizeWinner(summary);
  const why = summary?.reason_one_liner || winner.reason;
  const confidence = summary?.confidence || "Medium";
  const providerStatuses = result?.provider_statuses || {};
  const record = {
    id: currentRecordId || `match_${Date.now()}`,
    topic: debate.topic || payload?.topic || "",
    stance_a: payload?.side_a || "",
    stance_b: payload?.side_b || "",
    turn_count: debate.turn_count || payload?.turn_count || 0,
    mode: payload?.mode || "casual",
    fighter_a_provider: currentFighters.a,
    fighter_b_provider: currentFighters.b,
    judge_provider: currentFighters.judge,
    fighter_a_model: modelLabelForProvider(currentFighters.a),
    fighter_b_model: modelLabelForProvider(currentFighters.b),
    judge_model: modelLabelForProvider(currentFighters.judge),
    transcript_json: debate.turns || [],
    judge_json: {
      ...summary,
      verdict_headline: composeVerdictHeadline(debate.topic || payload?.topic || "", winner),
      verdict_subline: composeVerdictSubline(debate.topic || payload?.topic || "", winner, why),
      momentum: normalizeMomentum(summary, winner, confidence),
      flip_condition: composeFlipCondition(winner, normalizeWeakSpot(summary), why),
      gemini_takeaway: normalizeGeminiTakeaway(summary, debate.topic || payload?.topic || ""),
      gemini_quote: summary?.gemini_quote || { text: normalizeGeminiQuote(summary) },
    },
    created_at: new Date().toISOString(),
    source_mode: result?.mode || "mock",
    output_meta: buildOutputMeta(providerStatuses, (debate.turns || []).length, result?.mode || "mock"),
    saved_from_ui: true,
    fingerprint: matchFingerprint(result, payload),
  };
  return record;
}

function currentMatchContextKey() {
  if (currentLoadedRecord?.id && !currentRecordId) return `viewer:${currentLoadedRecord.id}`;
  if (currentRecordId) return `saved:${currentRecordId}`;
  if (currentResult && currentPayload) return `live:${matchFingerprint(currentResult, currentPayload)}`;
  return "none";
}

function getCurrentBattleRecord() {
  if (!currentResult || !currentPayload) return null;
  if (currentLoadedRecord) return currentLoadedRecord;
  if (currentRecordId) {
    const saved = historyRecordsCache.find((item) => item.id === currentRecordId);
    if (saved) return saved;
  }
  return buildBattleRecord(currentResult, currentPayload);
}

function resetAskThreadForCurrentMatch() {
  const nextKey = currentMatchContextKey();
  if (currentAskContextKey === nextKey) return;
  currentAskContextKey = nextKey;
  currentAskMessages = [];
}

function shouldShowAskHint() {
  const key = currentMatchContextKey();
  return key !== "none" && !dismissedAskHints.has(key);
}

function syncSaveButton() {
  if (analysisHidden || !currentResult) {
    saveButton.hidden = true;
    saveButton.disabled = true;
    saveButton.textContent = "Save Match";
    return;
  }
  saveButton.hidden = false;
  const records = loadHistoryRecords();
  const saved = records.some((record) => record.id === currentRecordId);
  saveButton.disabled = saved;
  saveButton.textContent = saved ? "Saved" : "Save Match";
}

function syncAskButton() {
  if (!analysisHidden && currentResult) {
    renderSummary(currentResult.debate?.summary || {});
  }
}

function formatCreatedAt(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "";
  return date.toLocaleString("ja-JP", { hour12: false });
}

function buildHistoryItemMarkup(record) {
  const preview = normalizeSavedRecordForPreview(record);
  const winner = preview.judge_json?.winner?.side || "Draw";
  const verdict = preview.judge_json?.verdict_headline || "Saved match";
  return `
    <button type="button" class="history-item" data-record-id="${escapeHtml(preview.id)}">
      <div class="history-topic">${escapeHtml(preview.topic)}</div>
      <div class="history-meta">${escapeHtml(formatCreatedAt(preview.created_at))} / ${escapeHtml(winner)} / ${escapeHtml(preview.mode)} / ${escapeHtml(`${preview.turn_count} turns`)}</div>
      <div class="history-submeta">${escapeHtml(`${preview.fighter_a_model} vs ${preview.fighter_b_model} / ${preview.judge_model}`)}</div>
      <div class="history-verdict">${escapeHtml(verdict)}</div>
    </button>
  `;
}

function buildViewerItemMarkup(record) {
  const preview = normalizeSavedRecordForPreview(record);
  const winner = preview.judge_json?.winner?.side || "Draw";
  const verdict = preview.judge_json?.verdict_headline || "Viewer match";
  return `
    <button type="button" class="viewer-match${preview.id === currentLoadedRecord?.id ? " is-active" : ""}" data-viewer-record-id="${escapeHtml(preview.id)}">
      <div class="viewer-match-topic">${escapeHtml(preview.topic)}</div>
      <div class="viewer-match-tease">${escapeHtml(preview.tease || "議論の崩れ方と決め手を追える一戦。")}</div>
      <div class="viewer-match-meta">${escapeHtml(preview.label || formatCreatedAt(preview.created_at))} / ${escapeHtml(winner)} / ${escapeHtml(preview.mode)} / ${escapeHtml(`${preview.turn_count} turns`)}</div>
      <div class="viewer-match-submeta">${escapeHtml(`${preview.fighter_a_model} vs ${preview.fighter_b_model} / ${preview.judge_model}`)}</div>
      <div class="viewer-match-verdict">${escapeHtml(verdict)}</div>
    </button>
  `;
}

function renderHistoryList() {
  const records = [...historyRecordsCache].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  updateHistoryButton(records.length);
  if (historyFetchInFlight && !historyRecordsHydrated) {
    historyListEl.classList.add("empty");
    historyListEl.innerHTML = '<div class="empty-state">履歴を読み込み中です。</div>';
    return;
  }
  if (!records.length) {
    historyListEl.classList.add("empty");
    historyListEl.innerHTML = '<div class="empty-state">保存した試合はまだありません。</div>';
    return;
  }
  historyListEl.classList.remove("empty");
  historyListEl.innerHTML = records.map(buildHistoryItemMarkup).join("");
}

function updateArchiveButton(count = loadHistoryRecords().length) {
  archiveButton.textContent = `⚙️`;
  archiveButton.setAttribute("aria-label", `Open archive (${count} matches)`);
  archiveCountEl.textContent = `${count} match${count === 1 ? "" : "es"}`;
}

function filteredArchiveRecords(records, query, modeFilter) {
  const normalizedQuery = normalizeSearchText(query);
  return records.filter((record) => {
    const matchesMode = modeFilter === "all" || record.mode === modeFilter;
    if (!matchesMode) return false;
    if (!normalizedQuery) return true;
    return normalizeSearchText(record.topic).includes(normalizedQuery);
  });
}

function renderArchiveList() {
  const records = [...historyRecordsCache].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  const filtered = filteredArchiveRecords(records, archiveSearchEl.value, archiveModeFilter);
  const recent = filtered.slice(0, 3);
  updateArchiveButton(records.length);
  archiveRecentCountEl.textContent = `${recent.length}`;
  archiveSavedCountEl.textContent = `${filtered.length}`;

  if (historyFetchInFlight && !historyRecordsHydrated) {
    archiveRecentListEl.classList.add("empty");
    archiveRecentListEl.innerHTML = '<div class="empty-state">履歴を読み込み中です。</div>';
    archiveListEl.classList.add("empty");
    archiveListEl.innerHTML = '<div class="empty-state">履歴を読み込み中です。</div>';
    return;
  }

  if (!recent.length) {
    archiveRecentListEl.classList.add("empty");
    archiveRecentListEl.innerHTML = '<div class="empty-state">保存した試合はまだありません。</div>';
  } else {
    archiveRecentListEl.classList.remove("empty");
    archiveRecentListEl.innerHTML = recent.map(buildHistoryItemMarkup).join("");
  }

  if (!filtered.length) {
    archiveListEl.classList.add("empty");
    archiveListEl.innerHTML = '<div class="empty-state">一致する試合はありません。</div>';
    return;
  }
  archiveListEl.classList.remove("empty");
  archiveListEl.innerHTML = filtered.map(buildHistoryItemMarkup).join("");
}

function renderViewerList() {
  if (!VIEWER_MODE) return;
  viewerCountEl.textContent = `${curatedViewerRecords.length} matches`;
  if (!curatedViewerRecords.length) {
    viewerListEl.classList.add("empty");
    viewerListEl.innerHTML = '<div class="empty-state">閲覧用の試合をまだ読み込めていません。</div>';
    return;
  }
  viewerListEl.classList.remove("empty");
  viewerListEl.innerHTML = curatedViewerRecords.map(buildViewerItemMarkup).join("");
}

function toggleHistory(open) {
  if (open) {
    toggleArchive(false);
    toggleAskPanel(false);
  }
  historyShellEl.hidden = !open;
  if (open) {
    void refreshHistoryRecords();
    historyListEl.scrollTop = 0;
  }
}

function toggleArchive(open) {
  if (open) {
    toggleHistory(false);
    toggleAskPanel(false);
  }
  archiveShellEl.hidden = !open;
  if (open) {
    void refreshHistoryRecords();
    archiveRecentListEl.scrollTop = 0;
    archiveListEl.scrollTop = 0;
  }
}

function renderAskThread() {
  if (!currentAskMessages.length) {
    askThreadEl.innerHTML = '<div class="empty-state">この試合の transcript と judge 結果だけを材料に、Gemini に質問できます。</div>';
    return;
  }
  askThreadEl.innerHTML = currentAskMessages.map((message) => `
    <article class="ask-bubble ask-bubble-${escapeHtml(message.role)}">
      <div class="ask-bubble-label">${escapeHtml(message.role === "user" ? "You" : "Gemini")}</div>
      <div class="ask-bubble-copy">${escapeHtml(message.text)}</div>
    </article>
  `).join("");
  askThreadEl.scrollTop = askThreadEl.scrollHeight;
}

function setAskStatus(text) {
  askStatusEl.textContent = text;
  askStatusEl.hidden = !text;
}

function updateAskMatchChip() {
  const record = getCurrentBattleRecord();
  if (!record) {
    askMatchChipEl.textContent = "match grounded";
    return;
  }
  const preview = normalizeSavedRecordForPreview(record);
  const winner = preview.judge_json?.winner?.side || "Draw";
  askMatchChipEl.textContent = `${winner} · ${preview.turn_count} turns · ${preview.mode}`;
}

function toggleAskPanel(open) {
  askShellEl.hidden = !open;
  if (open) {
    dismissedAskHints.add(currentMatchContextKey());
    resetAskThreadForCurrentMatch();
    updateAskMatchChip();
    renderAskThread();
    askInputEl.focus();
    if (currentResult && !analysisHidden) {
      renderSummary(currentResult.debate?.summary || {});
    }
  } else {
    setAskStatus("");
  }
}

function formatDebugJson(value) {
  if (!value) return "not available";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "not available";
  }
}

function renderDebugPipeline() {
  if (!debugPipelinePanelEl) return;
  const hasResult = Boolean(currentResult);
  debugPipelinePanelEl.hidden = !hasResult;
  if (debugConstraintReportEl) debugConstraintReportEl.textContent = formatDebugJson(currentConstraintReport);
  if (debugJudgePass1El) debugJudgePass1El.textContent = formatDebugJson(currentJudgePass1);
  if (debugJudgePass2El) debugJudgePass2El.textContent = formatDebugJson(currentJudgePass2);
  if (debugStoryAlignReportEl) debugStoryAlignReportEl.textContent = formatDebugJson(currentStoryAlignReport);
}

function buildResultFromRecord(record) {
  const preview = normalizeSavedRecordForPreview(record);
  return {
    ok: true,
    mode: preview.source_mode || "mock",
    output_meta: preview.output_meta || "",
    provider_statuses: {
      openai: { mode: preview.fighter_a_provider === "openai" || preview.fighter_b_provider === "openai" ? "live" : "mock", reason: "" },
      anthropic: { mode: preview.fighter_a_provider === "anthropic" || preview.fighter_b_provider === "anthropic" ? "live" : "mock", reason: "" },
      gemini: { mode: preview.judge_provider === "gemini" ? "live" : "mock", reason: "" },
    },
    debate: {
      topic: preview.topic,
      turn_count: preview.turn_count,
      participants: {
        a: preview.fighter_a_model,
        b: preview.fighter_b_model,
        judge: preview.judge_model,
      },
      turns: preview.transcript_json,
      summary: preview.judge_json,
    },
  };
}

function syncViewerReadOnlyControls() {
  if (!VIEWER_MODE) return;
  judgeButton.hidden = true;
  judgeButton.disabled = true;
  saveButton.hidden = true;
  saveButton.disabled = true;
}

function loadRecordIntoView(record, options = {}) {
  if (!record) return;
  const { saved = false } = options;
  const preview = normalizeSavedRecordForPreview(record);
  currentLoadedRecord = preview;
  currentRecordId = saved ? preview.id : null;
  currentPayload = {
    topic: preview.topic,
    side_a: preview.stance_a,
    side_b: preview.stance_b,
    turn_count: preview.turn_count,
    mode: preview.mode,
    fighter_a_provider: preview.fighter_a_provider,
    fighter_b_provider: preview.fighter_b_provider,
  };
  currentFighters = {
    a: preview.fighter_a_provider,
    b: preview.fighter_b_provider,
    judge: preview.judge_provider || "gemini",
  };
  document.querySelector("#topic").value = preview.topic;
  document.querySelector("#side-a").value = preview.stance_a;
  document.querySelector("#side-b").value = preview.stance_b;
  document.querySelector("#turn-count").value = String(preview.turn_count);
  document.querySelector(`input[name="debateMode"][value="${preview.mode}"]`)?.click();
  fighterAProviderInput.value = preview.fighter_a_provider;
  fighterBProviderInput.value = preview.fighter_b_provider;
  currentResult = buildResultFromRecord(preview);
  currentConstraintReport = currentResult.debate?.summary?.debug_constraint_report || null;
  currentJudgePass1 = currentResult.debate?.summary?.debug_pass1 || null;
  currentJudgePass2 = currentResult.debate?.summary?.debug_pass2 || null;
  currentStoryAlignReport = currentResult.debate?.summary?.debug_story_align_report || null;
  setReadingMode(true);
  setRevealState(false);
  resetAskThreadForCurrentMatch();
  refreshOutput();
  renderDebugPipeline();
  syncViewerReadOnlyControls();
  renderViewerList();
  setStatus("ok", "Structure revealed");
  toggleHistory(false);
  toggleArchive(false);
}

async function sendAskQuestion(question) {
  const trimmed = String(question || "").trim();
  const record = getCurrentBattleRecord();
  if (!trimmed || !record) return;
  resetAskThreadForCurrentMatch();
  currentAskMessages.push({ role: "user", text: trimmed });
  renderAskThread();
  askInputEl.value = "";
  askSendButton.disabled = true;
  setAskStatus("Gemini に確認中…");
  try {
    const response = await fetch(endpointUrl("/api/ask_match"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: trimmed,
        match: record,
        api_keys: {
          gemini: document.querySelector("#gemini-key").value.trim(),
        },
      }),
    });
    const data = await parseResponse(response);
    if (!response.ok || !data.ok) {
      throw new Error(normalizeApiError("ask_match", response.status, data) || data?.error || "ask failed");
    }
    currentAskMessages.push({ role: "assistant", text: data.answer || "返答が空でした。" });
    renderAskThread();
  } catch (error) {
    currentAskMessages.push({ role: "assistant", text: `Gemini を呼べませんでした: ${error.message || "unknown"}` });
    renderAskThread();
  } finally {
    askSendButton.disabled = false;
    setAskStatus("");
  }
}

async function loadSavedMatch(recordId) {
  const record = await fetchHistoryRecordById(recordId);
  if (!record) return;
  loadRecordIntoView(record, { saved: true });
}

async function saveCurrentMatch() {
  if (!currentResult || analysisHidden || !currentPayload) return;
  const record = buildBattleRecord(currentResult, currentPayload);
  const saved = await saveHistoryRecordToServer(record);
  currentRecordId = saved.id;
  renderHistoryList();
  renderArchiveList();
  syncSaveButton();
  syncAskButton();
}

function composeVerdictHeadline(topic, winner) {
  const cleanTopic = String(topic || "").trim();
  const side = winner?.side || "Draw";
  if (!cleanTopic) return side === "Draw" ? "今回は引き分けに近い" : `今回は${side}優勢`;
  if (side === "Draw") {
    if (/べきか$/.test(cleanTopic)) return cleanTopic.replace(/べきか$/, "べきかは決めきれない");
    if (/持つか$/.test(cleanTopic)) return cleanTopic.replace(/持つか$/, "持つとは決めきれない");
    if (/(.+)は存在するか$/.test(cleanTopic)) return cleanTopic.replace(/(.+)は存在するか$/, "$1の存在は決めきれない");
    if (/存在するか$/.test(cleanTopic)) return cleanTopic.replace(/存在するか$/, "存在するとは決めきれない");
    return `${cleanTopic.replace(/か$/, "")}は決めきれない`;
  }
  if (/べきか$/.test(cleanTopic)) {
    return side === "A" ? cleanTopic.replace(/か$/, "") : cleanTopic.replace(/べきか$/, "べきではない");
  }
  if (/持つか$/.test(cleanTopic)) {
    return side === "A" ? cleanTopic.replace(/か$/, "") : cleanTopic.replace(/持つか$/, "持つとは言い切れない");
  }
  if (/存在するか$/.test(cleanTopic)) {
    if (side === "A") return cleanTopic.replace(/か$/, "");
    if (/(.+)は存在するか$/.test(cleanTopic)) return cleanTopic.replace(/(.+)は存在するか$/, "$1の存在は立証できていない");
    return cleanTopic.replace(/存在するか$/, "存在は立証できていない");
  }
  if (/できるか$/.test(cleanTopic)) {
    return side === "A" ? cleanTopic.replace(/か$/, "") : cleanTopic.replace(/できるか$/, "できるとは言い切れない");
  }
  return `今回は${side}優勢`;
}

function composeVerdictSubline(topic, winner, why) {
  const cleanTopic = String(topic || "").trim();
  const side = winner?.side || "Draw";
  if (side === "Draw") {
    if (/持つか$/.test(cleanTopic)) return `少なくとも今回は「${cleanTopic.replace(/持つか$/, "持つ")}」を決め切る材料が足りませんでした。`;
    if (/べきか$/.test(cleanTopic)) return `少なくとも今回は「${cleanTopic.replace(/べきか$/, "べき")}」を決め切る材料が足りませんでした。`;
    return cleanTopic ? `少なくとも今回は、${cleanTopic.replace(/か$/, "")}を決め切る材料が足りませんでした。` : why;
  }
  if (/べきか$/.test(cleanTopic)) {
    return side === "A"
      ? `少なくとも今回は「${cleanTopic.replace(/か$/, "")}」が通りました。`
      : `少なくとも今回は「${cleanTopic.replace(/べきか$/, "べき")}」は弱いと見られました。`;
  }
  if (/持つか$/.test(cleanTopic)) {
    return side === "A"
      ? `少なくとも今回は「${cleanTopic.replace(/か$/, "")}」が押し切りました。`
      : `少なくとも今回は「${cleanTopic.replace(/か$/, "")}」を証明し切れませんでした。`;
  }
  if (/存在するか$/.test(cleanTopic)) {
    return side === "A" ? `少なくとも今回は「${cleanTopic.replace(/か$/, "")}」が優勢でした。` : "少なくとも今回は存在側の立証が届きませんでした。";
  }
  return why || `少なくとも今回は${side}の押し返しが上回りました。`;
}

async function loadStaticFixture() {
  const response = await fetch("./fixtures/debate_demo.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("fixture unavailable");
  }
  const data = await response.json();
  if (!data || !data.ok) {
    throw new Error("fixture invalid");
  }
  return data;
}

function extractTurnNumber(value) {
  if (value == null) return null;
  if (typeof value === "object" && Number.isFinite(value.turn)) return Number(value.turn);
  const text = typeof value === "string" ? value : JSON.stringify(value);
  const match = text.match(/Turn\s*(\d+)/i) || text.match(/turn\s*(\d+)/i);
  return match ? Number(match[1]) : null;
}

function normalizeSearchText(value) {
  return String(value || "")
    .replace(/[「」"'。、，,.!?！？\s]/g, "")
    .trim();
}

function clearJumpHighlight() {
  if (activeJumpTimer) {
    window.clearTimeout(activeJumpTimer);
    activeJumpTimer = null;
  }
  document.querySelectorAll(".jump-highlight").forEach((node) => node.classList.remove("jump-highlight"));
}

function pulseJumpTarget(target) {
  if (!target) return;
  clearJumpHighlight();
  target.classList.add("jump-highlight");
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  activeJumpTimer = window.setTimeout(() => {
    target.classList.remove("jump-highlight");
    activeJumpTimer = null;
  }, 2400);
}

function jumpToFatalPhrase(summary) {
  const fatal = normalizeFatalPhrase(summary);
  const turnNumber = extractTurnNumber(summary?.fatal_phrase);
  const speaker = String(summary?.fatal_phrase?.speaker || fatal.speaker || "").trim().toUpperCase();
  const quoteNeedle = normalizeSearchText(summary?.fatal_phrase?.text || "");
  const block = speaker && turnNumber
    ? document.querySelector(`[data-turn="${turnNumber}"][data-speaker="${speaker}"]`)
    : null;
  if (block) {
    const quotes = [...block.querySelectorAll(".turn-copy-sentence")];
    const exactSentence = quoteNeedle
      ? quotes.find((node) => normalizeSearchText(node.textContent).includes(quoteNeedle))
      : null;
    if (exactSentence) {
      pulseJumpTarget(exactSentence);
      return;
    }
    pulseJumpTarget(block);
    return;
  }
  const fallbackTurn = turnNumber ? document.querySelector(`#turn-${turnNumber}`) : null;
  if (fallbackTurn) pulseJumpTarget(fallbackTurn);
}

function jumpToTurningPoint(summary) {
  const turnNumber = extractTurnNumber(summary?.turning_point);
  const target = turnNumber ? document.querySelector(`#turn-${turnNumber}`) : null;
  if (target) pulseJumpTarget(target);
}

function jumpToWeakSpot(summary) {
  const weakSpot = normalizeWeakSpot(summary);
  const turnNumber = extractTurnNumber(weakSpot?.turn);
  const speaker = String(weakSpot?.speaker || "").trim().toUpperCase();
  const quoteNeedle = normalizeSearchText(weakSpot?.quote_excerpt || "");
  const blockSelector = turnNumber && speaker && speaker !== "A/B"
    ? `[data-turn="${turnNumber}"][data-speaker="${speaker}"]`
    : (speaker && speaker !== "A/B" ? `[data-speaker="${speaker}"]` : ".speaker-block");
  const blocks = [...document.querySelectorAll(blockSelector)];
  if (blocks.length) {
    const best = quoteNeedle
      ? blocks.find((node) => normalizeSearchText(node.textContent).includes(quoteNeedle))
      : null;
    pulseJumpTarget(best || blocks[blocks.length - 1]);
    return;
  }
  const fallback = turnNumber ? document.querySelector(`#turn-${turnNumber}`) : [...document.querySelectorAll(".speaker-block")].pop();
  if (fallback) pulseJumpTarget(fallback);
}

function detectTurnMarkers(summary) {
  return {
    fatal: extractTurnNumber(summary?.fatal_phrase),
    turning: extractTurnNumber(summary?.turning_point),
    contradiction: extractTurnNumber(summary?.contradiction_exposed),
  };
}

function apiBase() {
  const raw = apiBaseInput.value.trim().replace(/\/+$/, "");
  return raw || window.location.origin;
}

function endpointUrl(path) {
  return `${apiBase()}${path}`;
}

function renderSummary(summary) {
  ensureVerdictStrip();
  ensureGeminiQuote();
  ensureAnalysisPanel();
  syncMobileAnalysisPanel();
  const winner = normalizeWinner(summary);
  const fatal = normalizeFatalPhrase(summary);
  const turning = normalizeTurningPoint(summary);
  const weakSpot = normalizeWeakSpot(summary);
  const confidence = summary?.confidence || "Medium";
  const why = summary?.reason_one_liner || winner.reason;
  const topic = currentResult?.debate?.topic || "";
  const headline = composeVerdictHeadline(topic, winner);
  const subline = composeVerdictSubline(topic, winner, why);
  const momentum = normalizeMomentum(summary, winner, confidence);
  const flipCondition = composeFlipCondition(winner, weakSpot, why);
  const takeaway = normalizeGeminiTakeaway(summary, topic);
  const geminiQuote = normalizeGeminiQuote(summary);
  const keyDisagreements = normalizeDetailList(summary?.key_disagreement_top3);
  const unresolvedResidue = normalizeDetailList(summary?.unresolved_residue);
  const fullRationale = summary?.full_rationale || summary?.provisional_judgment || "";
  const askHint = shouldShowAskHint()
    ? "この試合について Gemini に質問できます。なぜ負けたか、何を足せば戻るかを聞けます。"
    : "";

  verdictStripEl.innerHTML = `
    <article class="verdict-strip-card">
      <div class="verdict-strip-main">${escapeHtml(headline)}</div>
      <div class="verdict-strip-meta">
        <span class="verdict-pill">Winner ${escapeHtml(winner.side)}</span>
        <span class="verdict-pill">${escapeHtml(confidence)}</span>
      </div>
      <div class="verdict-strip-subline">${escapeHtml(subline)}</div>
      <div class="verdict-strip-why">${escapeHtml(why)}</div>
      <div class="verdict-strip-aux">
        <section class="momentum-card">
          <div class="momentum-head">
            <span>A ${escapeHtml(momentum.a)}</span>
            <span>Momentum Bar</span>
            <span>B ${escapeHtml(momentum.b)}</span>
          </div>
          <div class="momentum-bar" aria-label="momentum bar">
            <div class="momentum-fill momentum-fill-a" style="width:${escapeHtml(momentum.a)}%"></div>
            <div class="momentum-fill momentum-fill-b" style="width:${escapeHtml(momentum.b)}%"></div>
          </div>
          <div class="momentum-note">この判定は真偽ではなく、この命題での押し込みです。</div>
        </section>
        <section class="flip-card">
          <div class="summary-label">Flip Condition</div>
          <div class="flip-copy">${escapeHtml(flipCondition)}</div>
        </section>
      </div>
      <section class="gemini-takeaway-card">
        <div class="summary-label">Gemini Takeaway</div>
        <div class="gemini-takeaway-line">${escapeHtml(takeaway.structural_explanation)}</div>
        <div class="gemini-takeaway-line">${escapeHtml(takeaway.debate_dynamic)}</div>
        <div class="gemini-takeaway-quote">${escapeHtml(takeaway.quote)}</div>
      </section>
      <div class="verdict-strip-actions">
        <div class="ask-cta-copy">
          <div class="ask-cta-title">この試合についてGeminiに聞く</div>
          ${askHint ? `<div class="ask-cta-hint">${escapeHtml(askHint)}</div>` : ""}
        </div>
        <button type="button" id="ask-match-button" class="secondary-button ask-cta-button">この試合をGeminiに聞く</button>
      </div>
    </article>
  `;

  geminiQuoteEl.innerHTML = `
    <article class="gemini-quote-card">
      <div class="summary-label">Gemini Quote</div>
      <div class="gemini-quote-copy">${escapeHtml(geminiQuote)}</div>
    </article>
  `;

  verdictGridEl.classList.remove("empty");
  spotlightGridEl.classList.remove("empty");
  verdictGridEl.innerHTML = `
    <article class="summary-card summary-card-verdict tone-winner">
      <div class="summary-label">Winner</div>
      <div class="summary-value summary-emphasis">${escapeHtml(winner.side)}</div>
      <div class="summary-subvalue">${escapeHtml(winner.reason)}</div>
    </article>
    <article class="summary-card summary-card-why">
      <div class="summary-label">Why in 1 sentence</div>
      <div class="summary-value">${escapeHtml(why)}</div>
    </article>
    <article class="summary-card summary-card-confidence">
      <div class="summary-label">Confidence</div>
      <div class="summary-value summary-emphasis">${escapeHtml(confidence)}</div>
    </article>
  `;
  spotlightGridEl.innerHTML = `
    <button type="button" class="summary-card tone-fatal summary-jump-card" data-jump-target="fatal">
      <div class="summary-label">Fatal Phrase</div>
      <div class="summary-meta">${escapeHtml(`Turn ${fatal.turn} / ${fatal.speaker}`)}</div>
      <div class="summary-value">${escapeHtml(fatal.quote)}</div>
      <div class="summary-subvalue">${escapeHtml(fatal.why)}</div>
    </button>
    <button type="button" class="summary-card tone-turning summary-jump-card" data-jump-target="turning">
      <div class="summary-label">Turning Point</div>
      <div class="summary-meta">${escapeHtml(turning.turn)}</div>
      <div class="summary-value">${escapeHtml(turning.summary)}</div>
    </button>
    <button type="button" class="summary-card tone-contradiction summary-jump-card" data-jump-target="weak">
      <div class="summary-label">Weak Spot / Foul</div>
      <div class="summary-meta">${escapeHtml(`${weakSpot.side} / Turn ${weakSpot.turn} / ${weakSpot.speaker} / ${weakSpot.label}`)}</div>
      <div class="summary-value">${escapeHtml(weakSpot.why_one_sentence)}</div>
      <div class="summary-subvalue">${escapeHtml(`「${weakSpot.quote_excerpt}」 / ${weakSpot.how_to_fix}`)}</div>
    </button>
  `;
  detailPanelEl.innerHTML = `
    <details class="analysis-details">
      <summary>Key Disagreement</summary>
      <div class="analysis-detail-copy">${escapeHtml(keyDisagreements.map((item, index) => `${index + 1}. ${item}`).join("\n"))}</div>
    </details>
    <details class="analysis-details">
      <summary>Unresolved Residue</summary>
      <div class="analysis-detail-copy">${escapeHtml(unresolvedResidue.join("\n"))}</div>
    </details>
    <details class="analysis-details">
      <summary>Full Rationale</summary>
      <div class="analysis-detail-copy">${escapeHtml(fullRationale)}</div>
    </details>
  `;
}

function ensureVerdictStrip() {
  if (verdictStripEl) return;
  verdictStripEl = document.createElement("section");
  verdictStripEl.id = "verdict-strip";
  verdictStripEl.className = "output-block verdict-strip-block";
  outputPanelEl.appendChild(verdictStripEl);
}

function destroyVerdictStrip() {
  if (verdictStripEl) {
    verdictStripEl.remove();
  }
  verdictStripEl = null;
}

function ensureGeminiQuote() {
  if (geminiQuoteEl) return;
  geminiQuoteEl = document.createElement("section");
  geminiQuoteEl.id = "gemini-quote";
  geminiQuoteEl.className = "output-block gemini-quote-block";
  if (analysisPanelEl && analysisPanelEl.parentNode === outputPanelEl) {
    outputPanelEl.insertBefore(geminiQuoteEl, analysisPanelEl);
    return;
  }
  outputPanelEl.appendChild(geminiQuoteEl);
}

function destroyGeminiQuote() {
  if (geminiQuoteEl) {
    geminiQuoteEl.remove();
  }
  geminiQuoteEl = null;
}

function ensureAnalysisPanel() {
  if (analysisPanelEl && verdictGridEl && spotlightGridEl && detailPanelEl) return;
  analysisPanelEl = document.createElement("section");
  analysisPanelEl.id = "analysis-panel";
  analysisPanelEl.className = "output-block";
  analysisPanelEl.innerHTML = `
    <div class="section-title-row">
      <h3>Structure Detector Result</h3>
      <div class="analysis-head-actions">
        <button type="button" id="analysis-toggle-button" class="chip-button analysis-toggle-button" hidden>▼ 分析を見る</button>
        <span class="meta-chip">Judge</span>
      </div>
    </div>
    <div id="analysis-content">
      <div id="verdict-grid" class="verdict-grid empty"></div>
      <div id="spotlight-grid" class="summary-grid empty"></div>
      <div id="detail-panel" class="detail-panel"></div>
    </div>
  `;
  if (geminiQuoteEl && geminiQuoteEl.parentNode === outputPanelEl) {
    outputPanelEl.insertBefore(analysisPanelEl, geminiQuoteEl.nextSibling);
  } else {
    outputPanelEl.appendChild(analysisPanelEl);
  }
  verdictGridEl = analysisPanelEl.querySelector("#verdict-grid");
  spotlightGridEl = analysisPanelEl.querySelector("#spotlight-grid");
  detailPanelEl = analysisPanelEl.querySelector("#detail-panel");
  analysisPanelEl.querySelector("#analysis-toggle-button")?.addEventListener("click", () => {
    mobileAnalysisCollapsed = !mobileAnalysisCollapsed;
    syncMobileAnalysisPanel();
  });
}

function destroyAnalysisPanel() {
  if (analysisPanelEl) {
    analysisPanelEl.remove();
  }
  analysisPanelEl = null;
  verdictGridEl = null;
  spotlightGridEl = null;
  detailPanelEl = null;
}

function syncMobileAnalysisPanel() {
  if (!analysisPanelEl) return;
  const toggleButton = analysisPanelEl.querySelector("#analysis-toggle-button");
  const content = analysisPanelEl.querySelector("#analysis-content");
  if (!toggleButton || !content) return;
  if (isMobileLayout()) {
    toggleButton.hidden = false;
    analysisPanelEl.classList.toggle("mobile-analysis-collapsed", mobileAnalysisCollapsed);
    content.hidden = mobileAnalysisCollapsed;
    toggleButton.textContent = mobileAnalysisCollapsed ? "▼ 分析を見る" : "▲ 分析を閉じる";
    return;
  }
  toggleButton.hidden = true;
  analysisPanelEl.classList.remove("mobile-analysis-collapsed");
  content.hidden = false;
}

function renderTurns(turns, summary = {}, reveal = false) {
  const markers = reveal ? detectTurnMarkers(summary) : {};
  turnLogEl.classList.remove("empty");
  turnLogEl.innerHTML = turns
    .map((turn) => {
      const stageLabel = turn.stage_label || `Turn ${turn.turn}`;
      const phaseMeta = describePhase(turn.turn, stageLabel, turns.length);
      const isRally = turn.turn >= 3;
      const classes = ["turn-card"];
      if (isRally) classes.push("turn-card-rally");
      if (reveal && markers.fatal === turn.turn) classes.push("marker-fatal");
      if (reveal && markers.turning === turn.turn) classes.push("marker-turning");
      if (reveal && markers.contradiction === turn.turn) classes.push("marker-contradiction");
      const aMarkup = sentenceMarkup(turn.a);
      const bMarkup = sentenceMarkup(turn.b);
      const bodyMarkup = isRally
        ? `
          <div class="rally-stack">
            <section id="turn-${escapeHtml(turn.turn)}-a" class="speaker-block rally-block rally-first" data-turn="${escapeHtml(turn.turn)}" data-speaker="A">
              <div class="speaker-label">
                <span class="speaker-role">先攻</span>
                <span class="speaker-side">A</span>
              </div>
              <div class="turn-copy">${aMarkup}</div>
            </section>
            <section id="turn-${escapeHtml(turn.turn)}-b" class="speaker-block rally-block rally-second" data-turn="${escapeHtml(turn.turn)}" data-speaker="B">
              <div class="speaker-label">
                <span class="speaker-role">後攻</span>
                <span class="speaker-side">B</span>
              </div>
              <div class="turn-copy">${bMarkup}</div>
            </section>
          </div>
        `
        : `
          <div class="turn-pair">
            <section id="turn-${escapeHtml(turn.turn)}-a" class="speaker-block" data-turn="${escapeHtml(turn.turn)}" data-speaker="A">
              <div class="speaker-label">A</div>
              <div class="turn-copy">${aMarkup}</div>
            </section>
            <section id="turn-${escapeHtml(turn.turn)}-b" class="speaker-block" data-turn="${escapeHtml(turn.turn)}" data-speaker="B">
              <div class="speaker-label">B</div>
              <div class="turn-copy">${bMarkup}</div>
            </section>
          </div>
        `;
      return `
        <article id="turn-${escapeHtml(turn.turn)}" class="${classes.join(" ")}" data-turn="${escapeHtml(turn.turn)}">
          <div class="turn-head">
            <strong class="turn-index">Turn ${escapeHtml(turn.turn)}</strong>
            <div class="turn-phase-group">
              <span class="turn-phase">${escapeHtml(phaseMeta.phase)}</span>
              <span class="turn-stage">${escapeHtml(phaseMeta.stage)}</span>
            </div>
          </div>
          ${bodyMarkup}
        </article>
      `;
    })
    .join("");
}

function sentenceMarkup(text) {
  const value = String(text || "");
  const parts = value
    .split(/(?<=[。！？!?])/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.length) return escapeHtml(value);
  return parts.map((part) => `<span class="turn-copy-sentence" data-normalized="${escapeHtml(normalizeSearchText(part))}">${escapeHtml(part)}</span>`).join("");
}

function describePhase(turnNumber, stageLabel, totalTurns) {
  if (turnNumber === 1) return { phase: "Turn 1", stage: "主張" };
  if (turnNumber === 2) return { phase: "Turn 2", stage: "反論" };
  if (turnNumber === 3) return { phase: "Turn 3", stage: "討論開始" };
  if (turnNumber === totalTurns) return { phase: `Turn ${turnNumber}`, stage: "締め" };
  return { phase: `Turn ${turnNumber}`, stage: "討論継続" };
}

function refreshOutput() {
  if (!currentResult) return;
  const debate = currentResult.debate || {};
  const turns = Array.isArray(debate.turns) ? debate.turns : [];
  const mode = currentResult.mode || "unknown";
  const providerStatuses = currentResult.provider_statuses || {};
  topicDisplayEl.textContent = debate.topic || "Topic";
  setRunMeta(analysisHidden ? "Generating..." : "Judging...", false);
  outputMetaEl.textContent = buildOutputMeta(providerStatuses, turns.length, mode, currentResult.output_meta || "");
  renderTurns(turns, debate.summary || {}, !analysisHidden);

  if (analysisHidden) {
    judgeButton.hidden = false;
    judgeButton.disabled = false;
    setHint("");
    return;
  }

  judgeButton.hidden = false;
  judgeButton.disabled = true;
  renderSummary(debate.summary || {});
  setHint(buildAbnormalHint(providerStatuses));
}

function renderResult(result) {
  currentResult = result;
  if (currentResult?.debate?.summary && !currentResult.debate.raw_summary) {
    currentResult.debate.raw_summary = JSON.parse(JSON.stringify(currentResult.debate.summary));
  }
  currentConstraintReport = null;
  currentJudgePass1 = null;
  currentJudgePass2 = null;
  currentStoryAlignReport = null;
  currentRecordId = null;
  currentLoadedRecord = null;
  resetAskThreadForCurrentMatch();
  setRevealState(true);
  setReadingMode(true);
  refreshOutput();
  renderDebugPipeline();
  syncSaveButton();
  syncAskButton();
  syncViewerReadOnlyControls();
}

function collectPayload() {
  const topic = document.querySelector("#topic").value.trim();
  const sideA = document.querySelector("#side-a").value.trim();
  const sideB = document.querySelector("#side-b").value.trim();
  const turnCountRaw = Number.parseInt(document.querySelector("#turn-count").value, 10);
  const turnCount = Number.isFinite(turnCountRaw) ? Math.max(5, Math.min(9, turnCountRaw)) : 5;
  const mode = document.querySelector('input[name="debateMode"]:checked')?.value || "casual";

  return {
    topic,
    side_a: sideA,
    side_b: sideB,
    turn_count: turnCount,
    mode,
    fighter_a_provider: fighterAProviderInput?.value || "openai",
    fighter_b_provider: fighterBProviderInput?.value || "anthropic",
    api_keys: {
      openai: document.querySelector("#openai-key").value.trim(),
      anthropic: document.querySelector("#anthropic-key").value.trim(),
      gemini: document.querySelector("#gemini-key").value.trim(),
    },
  };
}

async function checkApiHealth() {
  const healthUrl = endpointUrl("/api/health");
  try {
    const response = await fetch(healthUrl, { method: "GET" });
    if (response.status === 404) {
      setApiHealth("error", "health check failed");
      if (!analysisHidden) setHint("API health unavailable");
      return;
    }
    if (!response.ok) {
      setApiHealth("error", `health check failed (${response.status})`);
      if (!analysisHidden) setHint("API unavailable");
      return;
    }
    const data = await response.json();
    return data;
  } catch {
    if (!analysisHidden) setHint("API unavailable");
  }
}

syncMobileLayoutClass();
mobileMedia.addEventListener("change", () => {
  syncMobileLayoutClass();
  if (!isMobileLayout()) {
    mobileAnalysisCollapsed = true;
  }
  syncMobileAnalysisPanel();
});

function explainHttpError(endpointLabel, status) {
  if (status === 404) return `${endpointLabel} endpoint unavailable`;
  if (status === 400) return "request rejected";
  if (status >= 500) return "API error";
  return `HTTP ${status}`;
}

function normalizeApiError(endpointLabel, status, data) {
  const raw = String(data?.error || "").trim();
  if (
    status === 404
    || status === 405
    || status === 501
    || raw === "not found"
    || /unsupported method/i.test(raw)
  ) {
    return `${endpointLabel} endpoint unavailable`;
  }
  if (status === 400) return "request rejected";
  if (status >= 500) return "API error";
  return raw || explainHttpError(endpointLabel, status);
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return { ok: false, error: await response.text() };
}

async function runDebate(event) {
  event.preventDefault();
  const payload = collectPayload();
  currentPayload = payload;
  currentFighters = {
    a: payload.fighter_a_provider || "openai",
    b: payload.fighter_b_provider || "anthropic",
    judge: "gemini",
  };
  if (!payload.topic || !payload.side_a || !payload.side_b) {
    setStatus("error", "Missing input");
    return;
  }

  const endpoint = endpointUrl("/api/debate");
  currentResult = null;
  currentRecordId = null;
  currentLoadedRecord = null;
  setReadingMode(false);
  judgeButton.hidden = true;
  judgeButton.disabled = true;
  setRevealState(true);
  runButton.disabled = true;
  setStatus("running", "Generating");
  setRunMeta("Generating...", true);
  outputMetaEl.textContent = `${payload.turn_count} turns · pending`;
  topicDisplayEl.textContent = payload.topic;

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await parseResponse(response);
    if (!response.ok || !data.ok) {
      throw new Error(normalizeApiError("debate", response.status, data));
    }
    renderResult(data);
    setStatus("ok", "Debate ready");
  } catch (error) {
    const fallback = await loadStaticFixture();
    renderResult(fallback);
    setStatus("warn", "Debate ready");
  } finally {
    runButton.disabled = false;
    checkApiHealth();
    setRunMeta("", false);
    syncSaveButton();
  }
}

async function loadViewerArchive() {
  if (!VIEWER_MODE) return;
  try {
    const response = await fetch(VIEWER_ARCHIVE_URL, { cache: "no-store" });
    const data = await response.json();
    curatedViewerRecords = Array.isArray(data) ? data : [];
    renderViewerList();
    if (curatedViewerRecords.length) {
      loadRecordIntoView(curatedViewerRecords[0], { saved: false });
    }
  } catch {
    curatedViewerRecords = [];
    renderViewerList();
  }
}

async function copyViewerFeedback(kind) {
  const record = getCurrentBattleRecord();
  const body = viewerFeedbackInputEl.value.trim();
  const prefix = kind === "theme" ? "見たいテーマ" : "フィードバック";
  const topic = record?.topic ? `\n対象試合: ${record.topic}` : "";
  const text = `${prefix}${topic}\n\n${body || "(ここに内容を書く)"}`;
  try {
    await navigator.clipboard.writeText(text);
    setViewerFeedbackStatus(`${prefix}文をコピーしました。`);
  } catch {
    console.info(text);
    setViewerFeedbackStatus(`${prefix}文をコンソールへ出しました。`);
  }
}

function setupViewerMode() {
  if (!VIEWER_MODE) return;
  document.body.classList.add("viewer-mode");
  viewerLibraryEl.hidden = false;
  setStatus("idle", "Ready");
  setHint("");
  loadViewerArchive();
}

async function judgeDebate() {
  if (!currentResult) return;
  judgeButton.disabled = true;
  setStatus("running", "Judging...");
  setRunMeta("Judging...", true);
  await new Promise((resolve) => window.setTimeout(resolve, 150));
  const debate = currentResult.debate || {};
  const turns = Array.isArray(debate.turns) ? debate.turns : [];
  const transcript = buildCanonicalTranscript(turns);
  currentConstraintReport = await runConstraintAudit(debate.topic || currentPayload?.topic || "", turns);
  currentJudgePass1 = await runJudgePass1(transcript, currentConstraintReport);
  currentJudgePass2 = await runJudgePass2(transcript, currentJudgePass1, currentConstraintReport);
  const aligned = alignDebateStory(currentJudgePass1, currentJudgePass2, currentConstraintReport);
  currentStoryAlignReport = aligned.report;
  currentResult.debate.summary = {
    ...aligned.summary,
    debug_constraint_report: currentConstraintReport,
    debug_pass1: currentJudgePass1,
    debug_pass2: currentJudgePass2,
    debug_story_align_report: currentStoryAlignReport,
  };
  setRevealState(false);
  refreshOutput();
  renderDebugPipeline();
  setStatus("ok", "Structure revealed");
  setRunMeta("", false);
}

function buildCanonicalTranscript(turns) {
  return (turns || []).map((turn) => {
    const turnNumber = Number(turn?.turn) || 0;
    return [`Turn ${turnNumber} A: ${turn?.a || ""}`, `Turn ${turnNumber} B: ${turn?.b || ""}`].join("\n");
  }).join("\n");
}

async function runJudgePass1(transcript, constraintReport) {
  const rawSummary = currentResult?.debate?.raw_summary || currentResult?.debate?.summary || {};
  const winner = normalizeWinner(rawSummary);
  let lockedWinner = { ...winner };
  let momentum = normalizeMomentum(rawSummary, winner, rawSummary?.confidence || "Medium");
  const penalties = constraintReport?.drift_penalty || { A: 0, B: 0 };
  const exposed = Array.isArray(constraintReport?.drift_events) && constraintReport.drift_events.some((event) => event.exposed_by_opponent);
  if (exposed && lockedWinner.side === "A" && penalties.A > penalties.B) {
    lockedWinner = { side: "B", reason: "Bが命題逸脱を暴き、元の問いを固定した。" };
    momentum = { a: 30, b: 70 };
  } else if (exposed && lockedWinner.side === "B" && penalties.B > penalties.A) {
    lockedWinner = { side: "A", reason: "Aが命題逸脱を暴き、元の問いを固定した。" };
    momentum = { a: 70, b: 30 };
  }
  return {
    winner: lockedWinner,
    momentum,
    turning_point_turn: extractTurnNumber(rawSummary?.turning_point) || extractTurnNumber(rawSummary?.fatal_phrase) || 3,
    reason_one_liner: rawSummary?.reason_one_liner || lockedWinner.reason,
    confidence: rawSummary?.confidence || "Medium",
    transcript,
    raw_summary: rawSummary,
  };
}

async function runJudgePass2(transcript, pass1, constraintReport) {
  const rawSummary = currentResult?.debate?.raw_summary || currentResult?.debate?.summary || {};
  return {
    fatal_phrase: rawSummary?.fatal_phrase || {},
    weak_spot: rawSummary?.weak_spot || {},
    flip_condition: rawSummary?.flip_condition || "",
    gemini_takeaway: rawSummary?.gemini_takeaway || {},
    gemini_quote: rawSummary?.gemini_quote || {},
    turning_point: rawSummary?.turning_point || `Turn ${pass1?.turning_point_turn || 3}`,
    constraint_report: constraintReport,
    transcript,
    raw_summary: rawSummary,
  };
}

function scheduleHealthCheck() {
  if (healthCheckTimer) window.clearTimeout(healthCheckTimer);
  healthCheckTimer = window.setTimeout(() => {
    checkApiHealth();
  }, 250);
}

form.addEventListener("submit", runDebate);
judgeButton.addEventListener("click", judgeDebate);
saveButton.addEventListener("click", saveCurrentMatch);
historyButton.addEventListener("click", () => toggleHistory(true));
historyCloseButton.addEventListener("click", () => toggleHistory(false));
historyBackdrop.addEventListener("click", () => toggleHistory(false));
archiveButton.addEventListener("click", () => toggleArchive(true));
archiveCloseButton.addEventListener("click", () => toggleArchive(false));
archiveBackdrop.addEventListener("click", () => toggleArchive(false));
askCloseButton.addEventListener("click", () => toggleAskPanel(false));
askBackdrop.addEventListener("click", () => toggleAskPanel(false));
historyListEl.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-record-id]");
  if (!trigger) return;
  void loadSavedMatch(trigger.dataset.recordId);
});
viewerListEl.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-viewer-record-id]");
  if (!trigger) return;
  const record = curatedViewerRecords.find((item) => item.id === trigger.dataset.viewerRecordId);
  if (!record) return;
  loadRecordIntoView(record, { saved: false });
});
archivePanelEl.addEventListener("click", (event) => {
  const filterTrigger = event.target.closest("[data-mode-filter]");
  if (filterTrigger) {
    archiveModeFilter = filterTrigger.dataset.modeFilter || "all";
    archivePanelEl.querySelectorAll("[data-mode-filter]").forEach((node) => {
      node.classList.toggle("is-active", node.dataset.modeFilter === archiveModeFilter);
    });
    renderArchiveList();
    return;
  }
  const recordTrigger = event.target.closest("[data-record-id]");
  if (!recordTrigger) return;
  void loadSavedMatch(recordTrigger.dataset.recordId);
});
archiveSearchEl.addEventListener("input", () => {
  renderArchiveList();
});
askPanelEl.addEventListener("click", (event) => {
  const trigger = event.target.closest(".ask-preset");
  if (!trigger) return;
  const fill = trigger.dataset.fill || "";
  if (fill) {
    askInputEl.value = fill;
    askInputEl.focus();
    askInputEl.setSelectionRange(fill.length, fill.length);
    return;
  }
  sendAskQuestion(trigger.dataset.question || "");
});
outputPanelEl.addEventListener("click", (event) => {
  const trigger = event.target.closest("#ask-match-button");
  if (!trigger) return;
  toggleAskPanel(true);
});
document.addEventListener("click", (event) => {
  const trigger = event.target.closest(".summary-jump-card");
  if (!trigger || !currentResult) return;
  const summary = currentResult.debate?.summary || {};
  const target = trigger.dataset.jumpTarget || "";
  if (target === "fatal") jumpToFatalPhrase(summary);
  if (target === "turning") jumpToTurningPoint(summary);
  if (target === "weak") jumpToWeakSpot(summary);
});
askFormEl.addEventListener("submit", (event) => {
  event.preventDefault();
  sendAskQuestion(askInputEl.value);
});
viewerFeedbackButton.addEventListener("click", () => copyViewerFeedback("feedback"));
viewerTopicButton.addEventListener("click", () => copyViewerFeedback("theme"));
apiBaseInput.addEventListener("input", scheduleHealthCheck);

setStatus("idle", "Ready");
checkApiHealth();
void refreshHistoryRecords();
renderAskThread();
renderDebugPipeline();
setupViewerMode();
