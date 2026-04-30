import { runConstraintAudit } from "./constraint_auditor.js";
import { alignDebateStory } from "./story_aligner.js";

const form = document.querySelector("#debate-form");
const runButton = document.querySelector("#run-button");
const judgeButton = document.querySelector("#judge-button");
const appTitleEl = document.querySelector("#app-title");
const appLedeEl = document.querySelector("#app-lede");
const brandSignoffEl = document.querySelector("#brand-signoff");
const battleLangSwitchEl = document.querySelector("#battle-lang-switch");
const battleLangSwitchLabelEl = document.querySelector("#battle-lang-switch-label");
const battleLangButtons = [...document.querySelectorAll("[data-battle-lang]")];
const battleXSourceSlotEl = document.querySelector("#battle-x-source-slot");
const battleXSourceTemplateEl = document.querySelector("#battle-x-source-template");
const modeButtons = [...document.querySelectorAll("[data-experience-mode]")];
const saveButton = document.querySelector("#save-button");
const historyButton = document.querySelector("#history-button");
const archiveButton = document.querySelector("#archive-button");
const detailLikeButton = document.querySelector("#detail-like-button");
const shareBattleButton = document.querySelector("#share-battle-button");
const shareBattleXButton = document.querySelector("#share-battle-x-button");
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
const topicLabelEl = document.querySelector("#topic-label");
const topicInputEl = document.querySelector("#topic");
const topicOverwriteNoteEl = document.querySelector("#topic-overwrite-note");
const sideAInputEl = document.querySelector("#side-a");
const sideBInputEl = document.querySelector("#side-b");
const topicDisplayEl = document.querySelector("#topic-display");
const keywordInput = document.querySelector("#keyword");
const swapSidesButton = document.querySelector("#swap-sides-button");
const runtimeFingerprintEl = document.querySelector("#runtime-fingerprint");
const runtimeDiagnosticEl = document.querySelector("#runtime-diagnostic");
const readerControlsEl = document.querySelector("#reader-controls");
const readerBackButton = document.querySelector("#reader-back-button");
const readerNextButton = document.querySelector("#reader-next-button");
const runMetaEl = document.querySelector("#run-meta");
const outputMetaEl = document.querySelector("#output-meta");
const turnLogTitleEl = document.querySelector("#turn-log-title");
const turnLogEl = document.querySelector("#turn-log");
const turnLogEmptyStateEl = document.querySelector("#turn-log-empty-state");
const publicSummaryEl = document.querySelector("#public-summary");
const publicSummaryWinnerEl = document.querySelector("#public-summary-winner");
const publicSummaryReasonEl = document.querySelector("#public-summary-reason");
const outputPanelEl = document.querySelector(".output-panel");
const outputHeroEl = document.querySelector(".output-panel > .hero");
const pageShellEl = document.querySelector(".page-shell");
const inputPanelEl = document.querySelector(".input-panel");
const apiBaseInput = document.querySelector("#api-base");
const fighterAProviderInput = document.querySelector("#fighter-a-provider");
const fighterBProviderInput = document.querySelector("#fighter-b-provider");
const turnCountInput = document.querySelector("#turn-count");
const turnCountButtons = [...document.querySelectorAll("[data-turn-count-option]")];
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
const archiveModeNoteEl = document.querySelector("#archive-mode-note");
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
const askRetryButton = document.querySelector("#ask-retry-button");
const askReferenceBarEl = document.querySelector("#ask-reference-bar");
const askReferenceChipsEl = document.querySelector("#ask-reference-chips");
const demoModeBadgeEl = document.querySelector("#demo-mode-badge");
const publicFixedDemoNoteEl = document.querySelector("#public-fixed-demo-note");
const debugPipelinePanelEl = document.querySelector("#debug-pipeline-panel");
const debugConstraintReportEl = document.querySelector("#debug-constraint-report");
const debugJudgePass1El = document.querySelector("#debug-judge-pass1");
const debugJudgePass2El = document.querySelector("#debug-judge-pass2");
const debugStoryAlignReportEl = document.querySelector("#debug-story-align-report");
const mobileMedia = window.matchMedia("(max-width: 768px)");
const DEBATE_API_PATH = "/api/debate_v4";
const DEFAULT_PUBLIC_SHARE_ORIGIN = "https://mmar-l0-core.onrender.com";

let healthCheckTimer = null;
let currentResult = null;
let currentPayload = null;
let analysisHidden = true;
let currentFighters = { a: "openai", b: "anthropic", judge: "gemini" };
let currentRecordId = null;
let expansionIntroEl = null;
let verdictStripEl = null;
let geminiQuoteEl = null;
let analysisPanelEl = null;
let verdictGridEl = null;
let spotlightGridEl = null;
let detailPanelEl = null;
let currentAskMessages = [];
let currentAskContextKey = null;
let currentAskReferences = [];
const dismissedAskHints = new Set();
let activeJumpTimer = null;
let archiveModeFilter = "all";
let currentLoadedRecord = null;
let curatedViewerRecords = [];
let mobileAnalysisCollapsed = true;
let historyRecordsCache = [];
let historyRecordsHydrated = false;
let historyFetchInFlight = false;
let historySortMode = "recent";
let currentConstraintReport = null;
let currentJudgePass1 = null;
let currentJudgePass2 = null;
let currentBattleLang = "ja";
let currentStoryAlignReport = null;
let currentHealthInfo = { status: "unknown", data: null, message: "health unavailable" };
let activeSelectedTargets = [];
let isReaderMode = false;
let activeDebateTimerId = null;
let activeDebateStartedAt = 0;
let currentElapsedSeconds = null;
let currentRunToken = 0;
let currentExperienceMode = "debate";
let currentBattleSource = null;
let battleXSourceEl = null;
let battleXUrlInput = null;
let battleXBuildButton = null;
let battleXSourceErrorEl = null;
let battleSourceCardEl = null;
let battleSourceSummaryEl = null;
let battleSourceLinkEl = null;
let battleSourcePlaceholderEl = null;
let resultTopGridEl = null;
let resultHeroMediaEl = null;
let battleXBuildInFlight = false;
let currentLocalizedViewFetchToken = 0;

function normalizeBattleLang(value) {
  return String(value || "").trim().toLowerCase() === "en" ? "en" : "ja";
}

function storedBattleLang() {
  try {
    return normalizeBattleLang(window.localStorage.getItem("mmar_lang") || "");
  } catch {
    return "ja";
  }
}

function resolveRequestedBattleLang(params = queryParams, options = {}) {
  const { mode = REQUESTED_EXPERIENCE_MODE } = options;
  if (params?.has("lang")) return normalizeBattleLang(params.get("lang") || "");
  if (mode === "battle") return storedBattleLang();
  return "ja";
}

const queryParams = new URLSearchParams(window.location.search);
const VIEWER_MODE = queryParams.get("viewer") === "1" || queryParams.get("demo") === "1";
const BETA_MODE = queryParams.get("beta") === "1";
const REQUESTED_EXPERIENCE_MODE = queryParams.get("mode") === "battle" ? "battle" : "debate";
const REQUESTED_FOCUS = String(queryParams.get("focus") || "").trim().toLowerCase();
const REQUESTED_BATTLE_LANG_EXPLICIT = queryParams.has("lang");
const REQUESTED_BATTLE_LANG = resolveRequestedBattleLang(queryParams, { mode: REQUESTED_EXPERIENCE_MODE });
const READ_ONLY_DEMO = false;
const PUBLIC_LIMITED_DEMO = false;
const VIEWER_ARCHIVE_URL = "./fixtures/viewer_archive.json";
const PUBLIC_FIXED_CASE = {
  topic: "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。",
  side_a: "手を出すべきでなかった",
  side_b: "手を出すべきだった",
  turn_count: 3,
  mode: "casual",
  fighter_a_provider: "openai",
  fighter_b_provider: "openai",
  fixture_url: "./fixtures/public_sora_demo.json",
};
const MODEL_LABELS = {
  openai: "GPT-5-mini",
  anthropic: "Claude Sonnet 4.5",
  gemini: "Gemini 2.5 Flash",
  judge: "Gemini Judge",
};
const PUBLIC_ASK_DISABLED = true;
const EXPERIENCE_COPY = {
  debate: {
    title: "VerdAIct",
    modeLabel: "討論",
    lede: "自由入力の題材で討論を走らせ、本文と判定をそのまま読む本線です。",
    runLabel: "Run Debate",
    judgeLabel: "判定を見る",
  },
  battle: {
    title: "VerdAIct",
    modeLabel: "AIバトル",
    lede: "勝敗と決定打を先に読む、テンポ重視の入口です。",
    runLabel: "バトル開始",
    judgeLabel: "勝敗を見る",
  },
};
const BATTLE_LANG_COPY = {
  ja: {
    title: "VerdAIct",
    modeLabel: "AIバトル",
    lede: "勝敗と決定打を先に読む、テンポ重視の入口です。",
    runLabel: "バトル開始",
    judgeLabel: "勝敗を見る",
    langLabel: "言語",
    xImportEyebrow: "X Import",
    xImportCopy: "Xの投稿URLを貼るだけでAIバトル開始",
    xUrlLabel: "Xの投稿URL",
    xUrlPlaceholder: "Xの投稿URLを貼る",
    xBuildLabel: "Xからバトル作成",
    sourceLabel: "元ネタ",
    sourcePrefix: "元ネタ",
    sourceLink: "元URLを開く",
    sourcePlaceholder: "Xの投稿URLを入れると元ネタを表示します。",
    shareCopyLabel: "共有リンクコピー",
    shareXLabel: "Xで共有",
    issueLabel: "AIバトル:",
    winnerLabel: "勝者",
    decisiveLabel: "決定打",
    turningLabel: "流れが変わった瞬間",
    summaryLabel: "一言まとめ",
    weakLabel: "痛いところ",
    xBuildReading: "X投稿を読み取り中",
    xBuildHint: "元投稿を争点化して、battle 用の A/B を作っています。",
    xBuildDone: "Xからバトル素材を作成",
    xBuildError: "X投稿の読み取り失敗",
    xBuildRetry: "この投稿は読み取れませんでした。別のX投稿URLで試してください",
    shareOpened: "X共有を開きました",
    shareFailed: "X共有を開けませんでした",
    shareFallback: "AIバトルを作った",
    historyBattleLabel: "Gallery",
    galleryTitle: "VerdAIct",
    galleryCopy: "気になるAIバトルを選ぶ",
    galleryAction: "バトルを作る",
    galleryCount: (count) => `${count} cards`,
    galleryEmpty: "AIバトルはまだありません。",
    galleryLoading: "AIバトルを読み込み中です。",
    galleryError: "AIバトルを読み込めませんでした。",
    battleBadge: "AIバトル",
    topicLabel: "争点",
    topicPlaceholder: "争点を入れる",
    sideAPlaceholder: "A側の主張を入れる",
    sideBPlaceholder: "B側の主張を入れる",
    keywordPlaceholder: "キーワード（任意）",
    emptyTurnLog: "バトルを始めると、勝敗と決定打までまとめて表示します。",
  },
  en: {
    title: "VerdAIct",
    modeLabel: "AI Battle",
    lede: "Two AIs argue. The judge shows where it turned.",
    runLabel: "Start AI Battle",
    judgeLabel: "See Breakdown",
    langLabel: "Language",
    xImportEyebrow: "X Import",
    xImportCopy: "Paste an X post to turn it into an argument breakdown.",
    xUrlLabel: "X post URL",
    xUrlPlaceholder: "Paste an X post URL",
    xBuildLabel: "Create from X",
    sourceLabel: "Source",
    sourcePrefix: "Source",
    sourceLink: "Open original",
    sourcePlaceholder: "Paste an X post URL to load the source.",
    shareCopyLabel: "Copy share link",
    shareXLabel: "Share on X",
    issueLabel: "Issue",
    winnerLabel: "Winner",
    decisiveLabel: "Fatal Phrase",
    turningLabel: "Turning Point",
    summaryLabel: "Why It Held",
    weakLabel: "Weak Spot",
    xBuildReading: "Reading the X post",
    xBuildHint: "Building the issue, both sides, and the structural judgment surface.",
    xBuildDone: "Built battle seed from X",
    xBuildError: "Could not read that X post",
    xBuildRetry: "Could not read that post. Try another X post URL.",
    shareOpened: "Opened X share",
    shareFailed: "Could not open X share",
    shareFallback: "VerdAIct shows where this AI argument turned",
    historyBattleLabel: "Gallery",
    galleryTitle: "VerdAIct",
    galleryCopy: "Pick an AI battle that grabs you",
    galleryAction: "Create a battle",
    galleryCount: (count) => `${count} cards`,
    galleryEmpty: "No AI battles yet.",
    galleryLoading: "Loading AI battles.",
    galleryError: "Could not load AI battles.",
    battleBadge: "AI Battle",
    topicLabel: "Issue",
    topicPlaceholder: "Enter the issue",
    sideAPlaceholder: "Enter Side A",
    sideBPlaceholder: "Enter Side B",
    keywordPlaceholder: "Optional keyword",
    emptyTurnLog: "Start an AI battle to see the winner, turning point, fatal phrase, and flip condition.",
  },
};
const DEBATE_FORM_COPY = {
  topicLabel: "Topic",
  topicPlaceholder: "例: 次の仮想通貨バブルは来るか",
  sideAPlaceholder: "例: 来る。流動性とETH主導の資金流入が起きる",
  sideBPlaceholder: "例: 来ない。規制と需要不足で前回ほど伸びない",
  keywordPlaceholder: "例: ETH",
  overwriteNote: "新しいお題を入力すると前の内容は上書きされます。",
  turnLogTitle: "Turn Log",
  emptyTurnLog: "Run を押すと、3ターンの討論ログと構造サマリーを表示します。",
};
currentBattleLang = REQUESTED_BATTLE_LANG;

function currentArchiveModeFilter() {
  return currentExperienceMode === "battle" ? "battle" : "debate";
}

function battleCopy() {
  return BATTLE_LANG_COPY[currentBattleLang] || BATTLE_LANG_COPY.ja;
}

function isEnglishBattleView() {
  return isBattleMode() && currentBattleLang === "en";
}

function battleLocaleText(jaText, enText) {
  return isEnglishBattleView() ? enText : jaText;
}

function battleSummaryCopy() {
  return {
    winnerPill: battleLocaleText("Winner", "Winner"),
    momentumLabel: battleLocaleText("Momentum Bar", "Momentum Bar"),
    momentumNote: battleLocaleText("この判定は真偽ではなく、この命題での押し込みです。", "This measures who controlled the proposition, not who proved objective truth."),
    flipConditionLabel: battleLocaleText("Flip Condition", "Flip Condition"),
    geminiTakeawayLabel: battleLocaleText("Gemini Takeaway", "Takeaway"),
    geminiQuoteLabel: battleLocaleText("Gemini Quote", "Signature Line"),
    askTitle: battleLocaleText("この試合についてGeminiに聞く", "Ask Gemini About This Match"),
    askButton: battleLocaleText("この試合をGeminiに聞く", "Ask Gemini About This Match"),
    askHint: battleLocaleText("この試合について Gemini に質問できます。なぜ負けたか、何を足せば戻るかを聞けます。", "Ask Gemini why one side lost, what could have flipped the result, or which rule decided the match."),
    sourceKicker: battleLocaleText("Source", "Source"),
    battleResultKicker: battleLocaleText("Battle Result", "Structural Judgment"),
    firstCrackLabel: battleLocaleText("最初のヒビ", "First Crack"),
    firstCrackEmptyQuote: battleLocaleText("まだ最初のヒビは特定されていない。", "The first crack has not been identified yet."),
    firstCrackEmptyReason: battleLocaleText("どこで最初の傷が入ったかを追う。", "This is where the first visible weakness opened."),
    confidenceLabel: battleLocaleText("判定の強さ", "Judge Confidence"),
    clincherLabel: battleLocaleText("最後の押し込み", "Clincher"),
    detailSummary: battleLocaleText("詳細を見る", "Read Full Judgment"),
    detailEmpty: battleLocaleText("詳しい判定メモはまだありません。", "No full judgment yet."),
    judgeNotesTitle: battleLocaleText("Judge Notes", "Judge Notes"),
    analysisOpen: battleLocaleText("▼ 分析を見る", "▼ View Analysis"),
    analysisClose: battleLocaleText("▲ 分析を閉じる", "▲ Hide Analysis"),
    turnOneStage: battleLocaleText("主張", "Opening"),
    turnTwoStage: battleLocaleText("反論", "Rebuttal"),
    turnThreeStage: battleLocaleText("討論開始", "Rally Begins"),
    finalStage: battleLocaleText("締め", "Closing"),
    continueStage: battleLocaleText("討論継続", "Rally Continues"),
    sideALabel: battleLocaleText("先攻", "Side A"),
    sideBLabel: battleLocaleText("後攻", "Side B"),
  };
}

function updateDocumentMeta() {
  document.title = "VerdAIct | AI Argument Breakdown";
  const metaDescription = document.querySelector("#app-meta-description");
  if (metaDescription) {
    metaDescription.setAttribute(
      "content",
      "Turn any issue or X post into an AI battle. See the winner, turning point, fatal phrase, weak spot, and flip condition."
    );
  }
}

function formatBattleSideLabel(side) {
  const normalized = String(side || "").trim().toUpperCase();
  if (normalized === "A") return isEnglishBattleView() ? "Side A" : "A";
  if (normalized === "B") return isEnglishBattleView() ? "Side B" : "B";
  if (normalized === "DRAW") return battleLocaleText("保留", "Draw");
  return normalized || battleLocaleText("保留", "Draw");
}

function clearBattleXSourceError() {
  setBattleXSourceError("");
}

function applyFormShellCopy() {
  if (turnLogTitleEl) turnLogTitleEl.textContent = DEBATE_FORM_COPY.turnLogTitle;
  if (isBattleMode()) {
    const copy = battleCopy();
    if (topicLabelEl) topicLabelEl.textContent = copy.topicLabel;
    if (topicInputEl) topicInputEl.placeholder = copy.topicPlaceholder;
    if (sideAInputEl) sideAInputEl.placeholder = copy.sideAPlaceholder;
    if (sideBInputEl) sideBInputEl.placeholder = copy.sideBPlaceholder;
    if (keywordInput) keywordInput.placeholder = copy.keywordPlaceholder;
    if (topicOverwriteNoteEl) topicOverwriteNoteEl.hidden = true;
    if (turnLogEmptyStateEl) turnLogEmptyStateEl.textContent = copy.emptyTurnLog;
    return;
  }
  if (topicLabelEl) topicLabelEl.textContent = DEBATE_FORM_COPY.topicLabel;
  if (topicInputEl) topicInputEl.placeholder = DEBATE_FORM_COPY.topicPlaceholder;
  if (sideAInputEl) sideAInputEl.placeholder = DEBATE_FORM_COPY.sideAPlaceholder;
  if (sideBInputEl) sideBInputEl.placeholder = DEBATE_FORM_COPY.sideBPlaceholder;
  if (keywordInput) keywordInput.placeholder = DEBATE_FORM_COPY.keywordPlaceholder;
  if (topicOverwriteNoteEl) {
    topicOverwriteNoteEl.textContent = DEBATE_FORM_COPY.overwriteNote;
    topicOverwriteNoteEl.hidden = false;
  }
  if (turnLogEmptyStateEl) turnLogEmptyStateEl.textContent = DEBATE_FORM_COPY.emptyTurnLog;
}

function experienceCopyFor(mode) {
  if (mode === "battle") return battleCopy();
  return EXPERIENCE_COPY.debate;
}

function isLocalOrigin(origin) {
  try {
    const parsed = new URL(origin);
    return parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
  } catch {
    return /127\.0\.0\.1|localhost/.test(String(origin || ""));
  }
}

function shouldShowOperationalDebug() {
  return isLocalOrigin(window.location.origin || "") || queryParams.get("debug") === "1";
}

function shouldShowRuntimeFingerprint(health = currentHealthInfo?.data || null) {
  void health;
  return shouldShowOperationalDebug();
}

function publicFacingOperationalHint(debugText, publicText = "") {
  return shouldShowOperationalDebug() ? debugText : publicText;
}

function configuredPublicShareOrigin() {
  const fromQuery = String(queryParams.get("share_origin") || "").trim();
  const fromStorage = String(window.localStorage.getItem("mmar_public_origin") || "").trim();
  const fromHealth = String(currentHealthInfo?.data?.public_origin || "").trim();
  const preferred = fromQuery || fromStorage || fromHealth || DEFAULT_PUBLIC_SHARE_ORIGIN;
  return preferred.replace(/\/+$/, "");
}

function currentShareOrigin() {
  const localOrigin = String(window.location.origin || "").replace(/\/+$/, "");
  if (!isLocalOrigin(localOrigin)) return localOrigin;
  return configuredPublicShareOrigin() || localOrigin;
}

function shouldUsePublicFixedDemo() {
  return false;
}

function isMobileLayout() {
  return mobileMedia.matches;
}

function currentModeLabel() {
  if (READ_ONLY_DEMO) return "read-only";
  if (VIEWER_MODE) return "viewer";
  if (BETA_MODE) return "beta";
  if (shouldUsePublicFixedDemo()) return "public-fixed";
  return "live";
}

function normalizeTopicForStance(topic) {
  return String(topic || "").trim().replace(/[。！？!?]+$/g, "");
}

function normalizeKeyword(keyword) {
  const compact = String(keyword || "").trim().replace(/\s+/g, " ");
  if (!compact) return "";
  return compact.split(" ")[0].slice(0, 40);
}

function formatTopicDisplay(topic, keyword = "") {
  const cleanTopic = String(topic || "").trim() || "Topic";
  const cleanKeyword = normalizeKeyword(keyword);
  return cleanKeyword ? `${cleanTopic} (${cleanKeyword})` : cleanTopic;
}

function topicAnchorTokens(topic) {
  const stopwords = new Set([
    "この",
    "その",
    "どの",
    "こと",
    "もの",
    "ため",
    "日本",
    "今後",
    "常時",
    "本当",
    "本当に",
  ]);
  const cleaned = normalizeTopicForStance(topic)
    .replace(/[「」『』（）(),，、。]/g, " ")
    .split(/について|とは|って|を|は|が|に|で|と|へ|も|の|から|まで|より|なら|か|\s+/)
    .map((part) => part.trim())
    .map((part) => part.replace(/(すべきか|するべきか|べきか|すべき|必要か|可能か|妥当か|正しいか|許されるか)$/g, ""))
    .filter((part) => part.length >= 2 && !stopwords.has(part));
  return [...new Set(cleaned)].slice(0, 3);
}

function topicAnchorPhrase(topic) {
  const anchors = topicAnchorTokens(topic);
  if (anchors.length >= 3) return `${anchors[0]}・${anchors[1]}・${anchors[2]}`;
  if (anchors.length === 2) return `${anchors[0]}と${anchors[1]}`;
  if (anchors.length === 1) return anchors[0];
  return normalizeTopicForStance(topic) || "この命題";
}

function generatedPositionsFromTopic(topic) {
  const normalizedTopic = normalizeTopicForStance(topic);
  const framedTopic = normalizedTopic ? `「${normalizedTopic}」` : "この命題";
  const anchorPhrase = topicAnchorPhrase(normalizedTopic);
  return {
    a: `私は${framedTopic}を支持する。焦点は${anchorPhrase}で実際に何が改善し、その改善が他の手段では代替しにくいかだ。${anchorPhrase}の便益と実行条件が立つなら、この提案を進める理由は十分ある。`,
    b: `私は${framedTopic}に反対する。焦点は${anchorPhrase}を進めたときに何が悪化し、その負担を誰が引き受けるのかだ。${anchorPhrase}の副作用と失敗時のコストが閉じない限り、この提案を採るには早い。`,
  };
}

function isBattleMode() {
  return currentExperienceMode === "battle";
}

function inferredRuntimeEnvTag() {
  const explicit = String(currentHealthInfo?.data?.env_tag || "").trim().toLowerCase();
  if (explicit) return explicit;
  const origin = String(window.location.origin || "").trim().toLowerCase();
  if (origin.includes("mmar-debate-preview.onrender.com")) return "preview";
  if (origin.includes("mmar-l0-core.onrender.com")) return "public";
  return "";
}

function isPublicBattleReadOnly() {
  return inferredRuntimeEnvTag() === "public" && isBattleMode();
}

function syncBattleAccessControls() {
  const restricted = isPublicBattleReadOnly();
  const sourceSection = battleXSourceEl;
  const sourceHead = sourceSection?.querySelector(".battle-x-source-head");
  const sourceRow = sourceSection?.querySelector(".battle-x-source-row");
  if (sourceHead) sourceHead.hidden = restricted;
  if (sourceRow) sourceRow.hidden = restricted;
  if (battleXSourceErrorEl) battleXSourceErrorEl.hidden = true;
  if (runButton) {
    runButton.hidden = restricted || READ_ONLY_DEMO;
    if (restricted) {
      runButton.disabled = true;
    } else if (!READ_ONLY_DEMO && !shouldUsePublicFixedDemo()) {
      runButton.disabled = false;
    }
  }
}

function setExperienceModeButtonState(mode) {
  modeButtons.forEach((button) => {
    const active = button.dataset.experienceMode === mode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function setBattleLangButtonState() {
  battleLangButtons.forEach((button) => {
    const active = normalizeBattleLang(button.dataset.battleLang) === currentBattleLang;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function syncBattleLanguageRoute() {
  if (currentExperienceMode !== "battle") return;
  const url = new URL(window.location.href);
  if (currentBattleLang === "en") {
    url.searchParams.set("lang", "en");
    queryParams.set("lang", "en");
  } else {
    url.searchParams.delete("lang");
    queryParams.delete("lang");
  }
  window.history.replaceState({}, "", url.toString());
}

function applyBattleLanguageText() {
  const copy = battleCopy();
  if (battleLangSwitchLabelEl) battleLangSwitchLabelEl.textContent = copy.langLabel;
  if (battleLangSwitchEl) battleLangSwitchEl.hidden = currentExperienceMode !== "battle";
  const xImportEyebrowEl = document.querySelector("#battle-x-import-eyebrow");
  const xImportCopyEl = document.querySelector("#battle-x-import-copy");
  const xUrlLabelEl = document.querySelector("#battle-x-url-label");
  const sourceLabelEl = document.querySelector("#battle-source-label");
  if (xImportEyebrowEl) xImportEyebrowEl.textContent = copy.xImportEyebrow;
  if (xImportCopyEl) xImportCopyEl.textContent = copy.xImportCopy;
  if (xUrlLabelEl) xUrlLabelEl.textContent = copy.xUrlLabel;
  if (battleXUrlInput) battleXUrlInput.placeholder = copy.xUrlPlaceholder;
  if (battleXBuildButton) battleXBuildButton.textContent = copy.xBuildLabel;
  if (sourceLabelEl) sourceLabelEl.textContent = copy.sourceLabel;
  if (battleSourceLinkEl) battleSourceLinkEl.textContent = copy.sourceLink;
  if (battleSourcePlaceholderEl) battleSourcePlaceholderEl.textContent = copy.sourcePlaceholder;
  if (shareBattleButton) shareBattleButton.textContent = copy.shareCopyLabel;
  if (shareBattleXButton) shareBattleXButton.textContent = copy.shareXLabel;
  setBattleLangButtonState();
}

function setBattleLanguage(lang, options = {}) {
  const nextLang = normalizeBattleLang(lang);
  const changed = currentBattleLang !== nextLang;
  currentBattleLang = nextLang;
  try {
    window.localStorage.setItem("mmar_lang", nextLang);
  } catch {}
  syncBattleLanguageRoute();
  applyBattleLanguageText();
  if (currentExperienceMode === "battle") {
    const copy = experienceCopyFor("battle");
    if (appTitleEl) appTitleEl.textContent = copy.title;
    if (appLedeEl) appLedeEl.textContent = copy.lede;
    const debateModeButton = document.querySelector("#mode-debate-button");
    const battleModeButton = document.querySelector("#mode-battle-button");
    if (debateModeButton) debateModeButton.textContent = currentBattleLang === "en" ? "Debate" : "討論";
    if (battleModeButton) battleModeButton.textContent = currentBattleLang === "en" ? "AI Battle" : "AIバトル";
    if (!shouldUsePublicFixedDemo()) runButton.textContent = copy.runLabel;
    judgeButton.textContent = copy.judgeLabel;
  }
  updateDocumentMeta();
  clearBattleXSourceError();
  applyFormShellCopy();
  if (options.refresh !== false && changed) {
    if (currentResult) refreshOutput();
    else renderBattleSourceCard();
  }
  if (currentExperienceMode === "battle" && currentBattleLang === "en" && (currentLoadedRecord || currentResult)) {
    void ensureLocalizedViewForCurrentBattle().catch(() => {});
  }
}

function applyExperienceMode(mode) {
  currentExperienceMode = mode === "battle" ? "battle" : "debate";
  const copy = experienceCopyFor(currentExperienceMode);
  document.body.classList.toggle("battle-mode", currentExperienceMode === "battle");
  setExperienceModeButtonState(currentExperienceMode);
  if (appTitleEl) appTitleEl.textContent = copy.title;
  if (brandSignoffEl) brandSignoffEl.textContent = copy.modeLabel || "";
  if (appLedeEl) appLedeEl.textContent = copy.lede;
  const debateModeButton = document.querySelector("#mode-debate-button");
  const battleModeButton = document.querySelector("#mode-battle-button");
  if (debateModeButton) debateModeButton.textContent = currentExperienceMode === "battle" && currentBattleLang === "en" ? "Debate" : "討論";
  if (battleModeButton) battleModeButton.textContent = currentExperienceMode === "battle" && currentBattleLang === "en" ? "AI Battle" : "AIバトル";
  if (!shouldUsePublicFixedDemo()) {
    runButton.textContent = copy.runLabel;
  }
  judgeButton.textContent = copy.judgeLabel;
  updateDocumentMeta();
  renderBattleXSourceSection();
  applyBattleLanguageText();
  applyFormShellCopy();
  clearBattleXSourceError();
  archiveModeFilter = currentArchiveModeFilter();
  syncArchiveModeFilterButtons();
  if (!archiveShellEl.hidden) {
    renderArchiveList();
  }
  if (currentResult) {
    refreshOutput();
  }
  renderBattleSourceCard();
  syncShareButton();
  syncBattleAccessControls();
}

function syncBattleXSourceRefs() {
  battleXSourceEl = document.querySelector("#battle-x-source");
  battleXUrlInput = document.querySelector("#battle-x-url");
  battleXBuildButton = document.querySelector("#battle-x-build-button");
  battleXSourceErrorEl = document.querySelector("#battle-x-source-error");
  battleSourceCardEl = document.querySelector("#battle-source-card");
  battleSourceSummaryEl = document.querySelector("#battle-source-summary");
  battleSourceLinkEl = document.querySelector("#battle-source-link");
  battleSourcePlaceholderEl = document.querySelector("#battle-source-placeholder");
}

function mountBattleXSourceSection() {
  if (!battleXSourceSlotEl || !battleXSourceTemplateEl) return;
  if (!battleXSourceSlotEl.firstElementChild) {
    battleXSourceSlotEl.appendChild(battleXSourceTemplateEl.content.cloneNode(true));
  }
  syncBattleXSourceRefs();
}

function unmountBattleXSourceSection() {
  if (battleXSourceSlotEl) {
    battleXSourceSlotEl.replaceChildren();
  }
  syncBattleXSourceRefs();
}

function renderBattleXSourceSection() {
  if (currentExperienceMode === "battle") {
    mountBattleXSourceSection();
  } else {
    unmountBattleXSourceSection();
  }
}

function applyRequestedBattleFocus() {
  if (REQUESTED_EXPERIENCE_MODE !== "battle") return;
  if (REQUESTED_FOCUS !== "x_url") return;
  if (!isBattleMode()) return;
  if (!battleXUrlInput) return;
  window.requestAnimationFrame(() => {
    battleXUrlInput?.focus();
    battleXUrlInput?.select?.();
  });
}

function normalizeExperienceMode(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "battle") return "battle";
  return "debate";
}

function recordExperienceMode(record) {
  return normalizeExperienceMode(record?.experience_mode || "debate");
}

function syncArchiveModeFilterButtons() {
  archivePanelEl?.querySelectorAll("[data-mode-filter]").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.modeFilter === archiveModeFilter);
  });
  if (archiveModeNoteEl) {
    archiveModeNoteEl.textContent = archiveModeFilter === "battle"
      ? "現在はAIバトルの履歴を表示中"
      : archiveModeFilter === "all"
        ? "すべての履歴を表示中"
        : "現在は討論の履歴を表示中";
  }
}

function renderBattleSourceCard() {
  if (!battleSourceCardEl || !battleSourceSummaryEl || !battleSourceLinkEl || !battleSourcePlaceholderEl) return;
  const source = currentBattleSource;
  const safeSourceUrl = sanitizeExternalUrl(source?.source_url, { xOnly: true });
  const visible = Boolean(source && currentBattleSourceSummary() && safeSourceUrl);
  battleSourceCardEl.hidden = !isBattleMode();
  if (!isBattleMode()) {
    battleSourceSummaryEl.textContent = "";
    battleSourcePlaceholderEl.hidden = true;
    safeSetExternalHref(battleSourceLinkEl, "", { xOnly: true });
    battleSourceLinkEl.hidden = true;
    return;
  }
  if (!visible) {
    battleSourceSummaryEl.textContent = "";
    battleSourcePlaceholderEl.hidden = false;
    safeSetExternalHref(battleSourceLinkEl, "", { xOnly: true });
    battleSourceLinkEl.hidden = true;
    return;
  }
  battleSourcePlaceholderEl.hidden = true;
  battleSourceSummaryEl.textContent = `${battleCopy().sourcePrefix}: ${currentBattleSourceSummary()}`;
  safeSetExternalHref(battleSourceLinkEl, safeSourceUrl, { xOnly: true });
  battleSourceLinkEl.hidden = false;
}

function ensureResultHeroMedia() {
  if (resultHeroMediaEl) return;
  resultHeroMediaEl = document.createElement("section");
  resultHeroMediaEl.id = "result-hero-media";
  resultHeroMediaEl.className = "output-block result-hero-media-block";
}

function ensureResultTopGrid() {
  if (resultTopGridEl) return;
  resultTopGridEl = document.createElement("section");
  resultTopGridEl.id = "result-top-grid";
  resultTopGridEl.className = "result-top-grid";
  if (outputHeroEl?.parentElement === outputPanelEl) {
    outputPanelEl.insertBefore(resultTopGridEl, outputHeroEl);
    return;
  }
  if (outputPanelEl.firstElementChild) {
    outputPanelEl.insertBefore(resultTopGridEl, outputPanelEl.firstElementChild);
    return;
  }
  outputPanelEl.appendChild(resultTopGridEl);
}

function restoreOutputHeroPosition() {
  if (!outputHeroEl || !outputPanelEl) return;
  if (resultTopGridEl?.contains(outputHeroEl)) {
    outputPanelEl.insertBefore(outputHeroEl, resultTopGridEl);
  }
}

function removeBattleOutputRightCopy() {
  const bodyEl = outputHeroEl?.querySelector("#battle-output-body");
  const actionStackEl = bodyEl?.querySelector(".chip-stack");
  if (bodyEl && actionStackEl && outputHeroEl && !outputHeroEl.contains(actionStackEl)) {
    outputHeroEl.insertBefore(actionStackEl, bodyEl);
  }
  bodyEl?.remove();
  outputHeroEl?.querySelector("#battle-output-right-copy")?.remove();
}

function currentBattleStances() {
  const sideA = String(
    currentLoadedRecord?.stance_a
    || currentResult?.stance_a
    || currentLoadedRecord?.a
    || currentResult?.a
    || currentLoadedRecord?.side_a
    || currentResult?.side_a
    || ""
  ).trim();
  const sideB = String(
    currentLoadedRecord?.stance_b
    || currentResult?.stance_b
    || currentLoadedRecord?.b
    || currentResult?.b
    || currentLoadedRecord?.side_b
    || currentResult?.side_b
    || ""
  ).trim();
  if (!sideA || !sideB) return null;
  return { sideA, sideB };
}

function shouldUseBattleOutputRightCopy() {
  return true;
}

function battleOutputRightAbCopy() {
  const stances = currentBattleStances();
  if (!stances) return null;
  return {
    a: `A: ${stances.sideA}`,
    b: `B: ${stances.sideB}`,
  };
}

function battleOutputRightNextStepCopy() {
  if (!shouldUseBattleOutputRightCopy()) return "";
  return battleLocaleText("次の問い：あなたはどちらの判断を支持する？", "Next question: Which side of this judgment would you support?");
}

function currentBattleOutputRightSummary() {
  const localized = currentBattleDisplayView();
  return String(
    localized?.summary
    || localized?.source_summary
    || currentBattleSource?.source_summary
    || currentLoadedRecord?.source_summary
    || currentResult?.source_summary
    || currentLoadedRecord?.description
    || currentResult?.description
    || currentLoadedRecord?.excerpt
    || currentResult?.excerpt
    || currentLoadedRecord?.tease
    || currentResult?.tease
    || ""
  ).trim();
}

function renderBattleOutputRightCopy({ summary, sourceUrl, copy }) {
  if (!outputHeroEl || !topicDisplayEl || !summary) {
    removeBattleOutputRightCopy();
    return;
  }
  const abCopy = battleOutputRightAbCopy();
  const nextStepCopy = battleOutputRightNextStepCopy();
  let sourceCopyEl = outputHeroEl.querySelector("#battle-output-right-copy");
  if (!sourceCopyEl) {
    sourceCopyEl = document.createElement("section");
    sourceCopyEl.id = "battle-output-right-copy";
    sourceCopyEl.className = "battle-output-right-copy";
  }
  const actionStackEl = outputHeroEl.querySelector(".chip-stack");
  let bodyEl = outputHeroEl.querySelector("#battle-output-body");
  if (!bodyEl) {
    bodyEl = document.createElement("section");
    bodyEl.id = "battle-output-body";
    bodyEl.className = "battle-output-body";
  }
  const titleBlockEl = outputHeroEl.querySelector(":scope > div:first-child");
  if (!outputHeroEl.contains(bodyEl)) {
    if (titleBlockEl?.nextSibling) {
      outputHeroEl.insertBefore(bodyEl, titleBlockEl.nextSibling);
    } else {
      outputHeroEl.appendChild(bodyEl);
    }
  }
  if (!bodyEl.contains(sourceCopyEl)) {
    bodyEl.appendChild(sourceCopyEl);
  }
  sourceCopyEl.innerHTML = `
    <div class="battle-output-right-copy-main">
      <div class="battle-output-right-copy-kicker">${escapeHtml(copy.sourceLabel)}</div>
      <div class="battle-output-right-copy-text">${escapeHtml(summary)}</div>
      ${abCopy ? `
        <div class="battle-output-right-copy-ab" aria-label="battle entry points">
          <div class="battle-output-right-copy-ab-line">${escapeHtml(abCopy.a)}</div>
          <div class="battle-output-right-copy-ab-line">${escapeHtml(abCopy.b)}</div>
        </div>
      ` : ""}
      ${sourceUrl ? `<a class="battle-output-right-copy-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer noopener">${escapeHtml(copy.sourceLink)}</a>` : ""}
      ${nextStepCopy ? `<div class="battle-output-right-copy-next">${escapeHtml(nextStepCopy)}</div>` : ""}
    </div>
  `;
  if (actionStackEl && actionStackEl.parentElement !== sourceCopyEl) {
    sourceCopyEl.insertBefore(actionStackEl, sourceCopyEl.firstChild);
  }
}

function renderResultHeroMedia() {
  ensureResultTopGrid();
  ensureResultHeroMedia();
  if (!resultHeroMediaEl) return;
  if (!currentResult || !isBattleMode()) {
    removeBattleOutputRightCopy();
    restoreOutputHeroPosition();
    if (resultTopGridEl) resultTopGridEl.hidden = true;
    resultHeroMediaEl.hidden = true;
    resultHeroMediaEl.innerHTML = "";
    return;
  }
  const battleIssue = currentBattleIssue() || currentResult?.debate?.topic || "";
  const battleSourceUrl = sanitizeExternalUrl(currentBattleSource?.source_url, { xOnly: true });
  const battleSourceSummary = currentBattleOutputRightSummary();
  const xEmbed = currentBattleXEmbedState();
  const isOutputRightCopyTrial = shouldUseBattleOutputRightCopy();
  const heroImage = resolveBattleSourceImageUrl()
    || buildBattleCardPlaceholderImage(battleIssue || battleCopy().battleBadge);
  if (resultTopGridEl) {
    resultTopGridEl.hidden = false;
    if (!resultTopGridEl.contains(resultHeroMediaEl)) resultTopGridEl.appendChild(resultHeroMediaEl);
    if (outputHeroEl && !resultTopGridEl.contains(outputHeroEl)) resultTopGridEl.appendChild(outputHeroEl);
  }
  resultHeroMediaEl.hidden = false;
  if (isOutputRightCopyTrial) {
    renderBattleOutputRightCopy({
      summary: battleSourceSummary,
      sourceUrl: battleSourceUrl,
      copy: battleCopy(),
    });
  } else {
    removeBattleOutputRightCopy();
  }
  const embedMarkup = xEmbed?.status === "success"
    ? `
      <div class="result-x-embed-shell">
        <div class="result-x-embed" data-battle-x-embed="1">${xEmbed.html}</div>
      </div>
    `
    : xEmbed
      ? `<div class="result-x-embed-fallback">${escapeHtml(battleXEmbedFailureLabel(xEmbed.error || xEmbed.status))}</div>`
      : `
        <div class="result-hero-media-shell">
          <img class="result-hero-media-image" src="${escapeHtml(heroImage)}" alt="${escapeHtml(battleIssue || battleCopy().battleBadge)}" />
        </div>
      `;
  resultHeroMediaEl.innerHTML = `
    ${isOutputRightCopyTrial ? "" : `<div class="result-source-card-head">
      <div class="summary-label">${escapeHtml(battleCopy().sourceLabel)}</div>
      ${battleSourceUrl ? `<a class="result-source-link" href="${escapeHtml(battleSourceUrl)}" target="_blank" rel="noreferrer noopener">${escapeHtml(battleCopy().sourceLink)}</a>` : ""}
    </div>`}
    ${embedMarkup}
    ${isOutputRightCopyTrial ? "" : (battleSourceSummary ? `<div class="result-source-summary">${escapeHtml(battleSourceSummary)}</div>` : "")}
  `;
  if (xEmbed?.status === "success") {
    void ensureBattleXWidgetsScript()
      .then(() => window.twttr?.widgets?.load?.(resultHeroMediaEl))
      .catch(() => {});
  }
}

function currentBattleShareId() {
  if (currentLoadedRecord?.run_id) return String(currentLoadedRecord.run_id).trim();
  if (currentLoadedRecord?.session_id) return String(currentLoadedRecord.session_id).trim();
  if (currentResult?.run_id) return String(currentResult.run_id).trim();
  if (currentResult?.session_id) return String(currentResult.session_id).trim();
  return "";
}

function buildBattleShareUrl(id) {
  const base = `${currentShareOrigin()}/battle/${encodeURIComponent(String(id || "").trim())}`;
  return currentBattleLang === "en" ? `${base}?lang=en` : base;
}

function buildBattleGalleryUrl() {
  const url = new URL("/gallery", window.location.origin);
  if (currentBattleLang === "en") url.searchParams.set("lang", "en");
  return url.toString();
}

function normalizeLocalizedViews(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const normalized = {};
  for (const [key, value] of Object.entries(raw)) {
    const lang = normalizeBattleLang(key);
    if (value && typeof value === "object" && !Array.isArray(value)) {
      normalized[lang] = lang === "en" ? polishEnglishBattleView(value) : value;
    }
  }
  return normalized;
}

function normalizedEnglishSurfaceKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/["“”'‘’`「」『』()[\]{}]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function looksLikeAdjacentEnglishDuplicate(left, right) {
  const a = normalizedEnglishSurfaceKey(left);
  const b = normalizedEnglishSurfaceKey(right);
  if (!a || !b) return false;
  if (a === b) return true;
  const shorter = a.length <= b.length ? a : b;
  const longer = a.length <= b.length ? b : a;
  return shorter.length >= 18 && longer.includes(shorter);
}

function dedupeEnglishSurfaceLines(lines) {
  const deduped = [];
  for (const line of lines) {
    const text = String(line || "").trim();
    if (!text) continue;
    const previous = deduped[deduped.length - 1] || "";
    if (looksLikeAdjacentEnglishDuplicate(text, previous)) continue;
    deduped.push(text);
  }
  return deduped;
}

function polishEnglishWeakSpotLabel(value) {
  const label = String(value || "").trim();
  const exactMap = {
    "Retreat of Definition": "Shifting the Claim",
    "Definition Retreat": "Shifting the Claim",
    "Retreat to a Weaker Claim": "Shifting the Claim",
    "Failure exposure": "Weak Spot",
    "Why it stayed unresolved": "Why It Stayed Unresolved",
  };
  if (exactMap[label]) return exactMap[label];
  if (/retreat of definition/i.test(label)) return "Shifting the Claim";
  if (/definition shift/i.test(label)) return "Shifting the Claim";
  if (/failure exposure/i.test(label)) return "Weak Spot";
  return label;
}

function polishEnglishSurfaceText(value) {
  let text = String(value || "").trim();
  if (!text) return "";
  const replacements = [
    [/\bline of establishment\b/gi, "path to proof"],
    [/\bretreat of definition\b/gi, "definition shift"],
    [/\bestablished dominance by\b/gi, "controlled the frame by"],
    [/\bEven a clean logic collapses if there is a hole\./gi, "Even a clean line of logic collapses if it has a hole."],
    [/\bEven a clean logic collapses if it has a hole\./gi, "Even a clean line of logic collapses if it has a hole."],
    [/\bwithout missing the initial question and closed off ([AB])'s path to proof\b/gi, "and shut down $1's path to proof"],
    [/\bwithout missing the initial question\b/gi, "while staying on the original question"],
    [/\bTo return,\b/gi, "To flip the result,"],
    [/\bTo return\b/gi, "To flip the result"],
    [/\bretreat to a weaker definition\b/gi, "shift to a weaker definition"],
    [/\bline of logic\b/gi, "line of logic"],
  ];
  for (const [pattern, replacement] of replacements) {
    text = text.replace(pattern, replacement);
  }
  text = text
    .replace(/'definition shift'/gi, '"definition shift"')
    .replace(/'shifting the claim'/gi, '"shifting the claim"')
    .replace(/\breturn, they need to\b/gi, "flip the result, they need to")
    .replace(/\s+/g, " ")
    .trim();
  return text;
}

function polishEnglishSummary(summary) {
  const raw = summary && typeof summary === "object" && !Array.isArray(summary) ? summary : {};
  const winner = raw.winner && typeof raw.winner === "object" && !Array.isArray(raw.winner) ? raw.winner : {};
  const turning = raw.turning_point && typeof raw.turning_point === "object" && !Array.isArray(raw.turning_point) ? raw.turning_point : {};
  const fatal = raw.fatal_phrase && typeof raw.fatal_phrase === "object" && !Array.isArray(raw.fatal_phrase) ? raw.fatal_phrase : {};
  const weak = raw.weak_spot && typeof raw.weak_spot === "object" && !Array.isArray(raw.weak_spot) ? raw.weak_spot : {};
  const firstCrack = raw.first_crack && typeof raw.first_crack === "object" && !Array.isArray(raw.first_crack) ? raw.first_crack : {};
  const clincher = raw.clincher && typeof raw.clincher === "object" && !Array.isArray(raw.clincher) ? raw.clincher : {};
  const takeaway = raw.gemini_takeaway && typeof raw.gemini_takeaway === "object" && !Array.isArray(raw.gemini_takeaway) ? raw.gemini_takeaway : {};
  const quote = raw.gemini_quote && typeof raw.gemini_quote === "object" && !Array.isArray(raw.gemini_quote) ? raw.gemini_quote : {};
  return {
    ...raw,
    reason_one_liner: polishEnglishSurfaceText(raw.reason_one_liner),
    flip_condition: polishEnglishSurfaceText(raw.flip_condition),
    provisional_judgment: polishEnglishSurfaceText(raw.provisional_judgment),
    full_rationale: polishEnglishSurfaceText(raw.full_rationale),
    winner: {
      ...winner,
      reason: polishEnglishSurfaceText(winner.reason),
    },
    turning_point: {
      ...turning,
      summary: polishEnglishSurfaceText(turning.summary),
      quote_excerpt: polishEnglishSurfaceText(turning.quote_excerpt),
    },
    fatal_phrase: {
      ...fatal,
      quote: polishEnglishSurfaceText(fatal.quote),
      reason: polishEnglishSurfaceText(fatal.reason),
    },
    weak_spot: {
      ...weak,
      label: polishEnglishWeakSpotLabel(weak.label),
      quote_excerpt: polishEnglishSurfaceText(weak.quote_excerpt),
      why_one_sentence: polishEnglishSurfaceText(weak.why_one_sentence),
      how_to_fix: polishEnglishSurfaceText(weak.how_to_fix),
    },
    first_crack: {
      ...firstCrack,
      quote: polishEnglishSurfaceText(firstCrack.quote),
      reason: polishEnglishSurfaceText(firstCrack.reason),
    },
    clincher: {
      ...clincher,
      quote: polishEnglishSurfaceText(clincher.quote),
      reason: polishEnglishSurfaceText(clincher.reason),
    },
    gemini_takeaway: {
      ...takeaway,
      structural_explanation: polishEnglishSurfaceText(takeaway.structural_explanation),
      debate_dynamic: polishEnglishSurfaceText(takeaway.debate_dynamic),
      quote: polishEnglishSurfaceText(takeaway.quote),
    },
    gemini_quote: {
      ...quote,
      text: polishEnglishSurfaceText(quote.text),
      framing_text: polishEnglishSurfaceText(quote.framing_text),
      evidence_quote: polishEnglishSurfaceText(quote.evidence_quote),
      framing_reason: polishEnglishSurfaceText(quote.framing_reason),
      pick_reason: polishEnglishSurfaceText(quote.pick_reason),
    },
  };
}

function polishEnglishBattleView(view) {
  const raw = view && typeof view === "object" && !Array.isArray(view) ? view : {};
  return {
    ...raw,
    issue: polishEnglishSurfaceText(raw.issue),
    side_a: polishEnglishSurfaceText(raw.side_a),
    side_b: polishEnglishSurfaceText(raw.side_b),
    source_summary: polishEnglishSurfaceText(raw.source_summary),
    turns: Array.isArray(raw.turns)
      ? raw.turns.map((turn, index) => ({
          turn: Number(turn?.turn) || index + 1,
          a: polishEnglishSurfaceText(turn?.a),
          b: polishEnglishSurfaceText(turn?.b),
        }))
      : [],
    summary: polishEnglishSummary(raw.summary),
  };
}

function currentLocalizedBattleView() {
  if (!isBattleMode() || currentBattleLang !== "en") return null;
  const loadedViews = normalizeLocalizedViews(currentLoadedRecord?.localized_views);
  if (loadedViews.en && String(loadedViews.en.status || "").trim().toLowerCase() === "ready") return loadedViews.en;
  const resultViews = normalizeLocalizedViews(currentResult?.localized_views);
  if (resultViews.en && String(resultViews.en.status || "").trim().toLowerCase() === "ready") return resultViews.en;
  return null;
}

function currentLocalizedBattleStatus() {
  if (!isBattleMode() || currentBattleLang !== "en") return "";
  const loadedViews = normalizeLocalizedViews(currentLoadedRecord?.localized_views);
  if (loadedViews.en) return String(loadedViews.en.status || currentLoadedRecord?.localized_en_status || "").trim().toLowerCase();
  const resultViews = normalizeLocalizedViews(currentResult?.localized_views);
  if (resultViews.en) return String(resultViews.en.status || currentResult?.localized_en_status || "").trim().toLowerCase();
  return String(currentLoadedRecord?.localized_en_status || currentResult?.localized_en_status || "").trim().toLowerCase();
}

function currentBattleDisplayView() {
  return currentBattleLang === "en" ? currentLocalizedBattleView() : null;
}

function mergeLocalizedSummary(base, overlay) {
  if (!overlay || typeof overlay !== "object" || Array.isArray(overlay)) return base || {};
  const source = base && typeof base === "object" && !Array.isArray(base) ? base : {};
  const merged = { ...source };
  for (const [key, value] of Object.entries(overlay)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      merged[key] = mergeLocalizedSummary(source[key], value);
    } else if (typeof value === "string") {
      merged[key] = value.trim() ? value : source[key];
    } else if (value !== undefined && value !== null && value !== "") {
      merged[key] = value;
    }
  }
  return merged;
}

function summaryForDisplay(summary) {
  const localized = currentBattleDisplayView();
  if (!localized?.summary) return summary || {};
  return mergeLocalizedSummary(summary || {}, localized.summary);
}

function currentLocalizedBattleTurns() {
  const localized = currentBattleDisplayView();
  if (!Array.isArray(localized?.turns) || !localized.turns.length) return [];
  return localized.turns
    .filter((turn) => turn && typeof turn === "object")
    .map((turn, index) => ({
      turn: Number(turn.turn) || index + 1,
      a: String(turn.a || ""),
      b: String(turn.b || ""),
    }))
    .filter((turn) => turn.a || turn.b);
}

function currentBattleSourceSummary() {
  const localized = currentBattleDisplayView();
  if (localized?.source_summary) return String(localized.source_summary).trim();
  return String(currentBattleSource?.source_summary || "").trim();
}

function safeBattleSourceImageUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (raw.startsWith("data:image/")) return raw;
  if (raw.startsWith("https://") || raw.startsWith("http://")) return raw;
  return "";
}

function battleSourceImageValue(key) {
  const sources = [
    currentBattleSource,
    currentLoadedRecord,
    currentResult,
    currentResult?.debate,
  ];
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    const imageUrl = safeBattleSourceImageUrl(source[key]);
    if (imageUrl) return imageUrl;
  }
  return "";
}

function resolveBattleSourceImageUrl() {
  return (
    battleSourceImageValue("x_embed_media_url")
    || battleSourceImageValue("source_image_url")
    || battleSourceImageValue("source_media_url")
    || battleSourceImageValue("source_image")
    || ""
  );
}

function currentBattleXEmbedState() {
  const sourceUrl = String(currentBattleSource?.source_url || currentLoadedRecord?.source_url || "").trim();
  const savedSourceUrl = String(currentLoadedRecord?.x_embed_source_url || currentResult?.x_embed_source_url || "").trim();
  if (!sourceUrl || !savedSourceUrl || sourceUrl !== savedSourceUrl) return null;
  const status = String(currentLoadedRecord?.x_embed_status || currentResult?.x_embed_status || "").trim();
  if (!status) return null;
  if (status === "success") {
    const html = String(currentLoadedRecord?.x_embed_html || currentResult?.x_embed_html || "").trim();
    const mediaUrl = String(currentLoadedRecord?.x_embed_media_url || currentResult?.x_embed_media_url || "").trim();
    if (!html || !html.includes("twitter-tweet")) return null;
    return { status, html, mediaUrl };
  }
  return {
    status,
    error: String(currentLoadedRecord?.x_embed_error || currentResult?.x_embed_error || status).trim(),
  };
}

function battleXEmbedFailureLabel(errorCode) {
  if (errorCode === "x_forbidden") {
    return currentBattleLang === "en"
      ? "Embedding unavailable on X (403)"
      : "X側の制限により埋め込めません（403）";
  }
  if (errorCode === "invalid" || errorCode === "invalid_x_post_url" || errorCode === "missing_url") {
    return currentBattleLang === "en" ? "Invalid URL" : "URL無効";
  }
  return currentBattleLang === "en"
    ? "Temporarily unavailable"
    : "一時的に取得できませんでした";
}

let battleXWidgetsPromise = null;
function ensureBattleXWidgetsScript() {
  if (window.twttr?.widgets?.load) return Promise.resolve(window.twttr);
  if (battleXWidgetsPromise) return battleXWidgetsPromise;
  battleXWidgetsPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-x-widgets="true"]');
    if (existing) {
      existing.addEventListener("load", () => resolve(window.twttr), { once: true });
      existing.addEventListener("error", () => reject(new Error("x_widgets_load_failed")), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = "https://platform.x.com/widgets.js";
    script.async = true;
    script.dataset.xWidgets = "true";
    script.addEventListener("load", () => resolve(window.twttr), { once: true });
    script.addEventListener("error", () => reject(new Error("x_widgets_load_failed")), { once: true });
    document.head.appendChild(script);
  });
  return battleXWidgetsPromise;
}

async function fetchLocalizedBattleView(recordId, lang = currentBattleLang) {
  const requestedLang = normalizeBattleLang(lang);
  const response = await fetch(endpointUrl(`/api/battle/${encodeURIComponent(recordId)}/localize?lang=${requestedLang}`), { method: "GET" });
  const data = await parseResponse(response);
  if (!response.ok || !data?.ok || !data?.record) {
    throw new Error(normalizeApiError("battle_localize", response.status, data));
  }
  return data;
}

async function ensureLocalizedViewForCurrentBattle() {
  if (!isBattleMode() || currentBattleLang !== "en") return null;
  const localized = currentLocalizedBattleView();
  if (localized?.status === "ready") return localized;
  const recordId = currentBattleShareId();
  if (!recordId) return null;
  const fetchToken = ++currentLocalizedViewFetchToken;
  const data = await fetchLocalizedBattleView(recordId, "en");
  if (fetchToken !== currentLocalizedViewFetchToken) return null;
  const normalized = normalizeSavedRecordForPreview(data.record);
  currentLoadedRecord = normalized;
  currentRecordId = normalized.id || currentRecordId;
  if (currentResult && currentResult.debate) {
    currentResult.localized_views = normalized.localized_views || {};
  }
  renderBattleSourceCard();
  refreshOutput();
  syncShareButton();
  return data.localized_view || null;
}

function syncShareButton() {
  if (!shareBattleButton && !shareBattleXButton) return;
  const visible = isBattleMode() && Boolean(currentResult);
  if (shareBattleButton) {
    shareBattleButton.hidden = !visible;
    shareBattleButton.disabled = !visible;
  }
  if (shareBattleXButton) {
    shareBattleXButton.hidden = !visible;
    shareBattleXButton.disabled = !visible;
  }
}

function setBattleXSourceError(message = "") {
  if (!battleXSourceErrorEl) return;
  battleXSourceErrorEl.textContent = message;
  battleXSourceErrorEl.hidden = !message;
}

function fillBattleSourceFromXSeed(data) {
  const topicInput = document.querySelector("#topic");
  const sideAInput = document.querySelector("#side-a");
  const sideBInput = document.querySelector("#side-b");
  if (!topicInput || !sideAInput || !sideBInput) return;
  setBattleLanguage(data.lang || currentBattleLang, { refresh: false });
  topicInput.value = String(data.issue || "").trim();
  sideAInput.value = String(data.side_a || "").trim();
  sideBInput.value = String(data.side_b || "").trim();
  if (keywordInput) keywordInput.value = "";
  currentBattleSource = {
    source_type: data.source_type || "x_post",
    source_url: String(data.source_url || "").trim(),
    source_image: String(data.source_image || "").trim(),
    source_summary: String(data.source_summary || "").trim(),
    issue: String(data.issue || "").trim(),
    lang: normalizeBattleLang(data.lang || currentBattleLang),
  };
  renderBattleSourceCard();
}

async function createBattleFromXUrl() {
  if (isPublicBattleReadOnly()) {
    setStatus("warn", "Preview/Admin only");
    setHint("公開環境ではAIバトルの生成はできません。");
    return;
  }
  const url = String(battleXUrlInput?.value || "").trim();
  if (!url) {
    setBattleXSourceError(currentBattleLang === "en" ? "Enter an X post URL." : "Xの投稿URLを入れてください");
    return;
  }
  if (battleXBuildInFlight) return;
  battleXBuildInFlight = true;
  if (battleXBuildButton) battleXBuildButton.disabled = true;
  setBattleXSourceError("");
  setStatus("running", battleCopy().xBuildReading);
  setHint(battleCopy().xBuildHint);
  try {
    const { response, data } = await postJsonWithBrowserFallback(endpointUrl("/api/battle_from_x_url"), { url, lang: currentBattleLang });
    if (!response.ok || !data?.ok) {
      throw new Error(normalizeApiError("battle_from_x_url", response.status, data));
    }
    fillBattleSourceFromXSeed(data);
    setStatus("ok", battleCopy().xBuildDone);
    setHint("");
    if (!runButton.disabled) {
      form.requestSubmit();
    }
  } catch (error) {
    currentBattleSource = null;
    renderBattleSourceCard();
    const message = String(error?.message || "");
    if (/invalid_x_url/i.test(message)) {
      setBattleXSourceError(battleCopy().xBuildRetry);
    } else {
      setBattleXSourceError(battleCopy().xBuildRetry);
    }
    setStatus("error", battleCopy().xBuildError);
    setHint("");
  } finally {
    battleXBuildInFlight = false;
    if (battleXBuildButton) battleXBuildButton.disabled = false;
  }
}

function applyPublicInteractiveDefaults() {
  document.body.classList.remove("public-fixed-demo");
  if (publicFixedDemoNoteEl) publicFixedDemoNoteEl.hidden = true;
  if (demoModeBadgeEl) demoModeBadgeEl.hidden = true;
  document.querySelector("#topic").readOnly = false;
  document.querySelector("#side-a").readOnly = false;
  document.querySelector("#side-b").readOnly = false;
  if (keywordInput) keywordInput.readOnly = false;
  fighterAProviderInput.value = "openai";
  fighterBProviderInput.value = "openai";
  fighterAProviderInput.disabled = true;
  fighterBProviderInput.disabled = true;
}

function publicFixedDemoLog(eventName, detail = undefined) {
  if (!shouldUsePublicFixedDemo()) return;
  if (detail === undefined) {
    console.info(eventName);
    return;
  }
  console.info(eventName, detail);
}

function isSymmetricLiveFixedResult(result) {
  const fighterA = String(result?.fighter_a_provider || "").trim().toLowerCase();
  const fighterB = String(result?.fighter_b_provider || "").trim().toLowerCase();
  if (fighterA !== "openai" || fighterB !== "openai") {
    return {
      ok: false,
      reason: `expected openai/openai, got ${fighterA || "?"}/${fighterB || "?"}`,
    };
  }
  const turns = Array.isArray(result?.debate?.turns) ? result.debate.turns : [];
  if (!turns.length) {
    return { ok: false, reason: "missing turn data" };
  }
  const topLevelStatuses = result?.provider_statuses || {};
  const topLevelAMode = String(
    topLevelStatuses?.openai_a?.mode || topLevelStatuses?.openai?.mode || "",
  )
    .trim()
    .toLowerCase();
  const topLevelBMode = String(
    topLevelStatuses?.openai_b?.mode || topLevelStatuses?.openai?.mode || "",
  )
    .trim()
    .toLowerCase();
  if (!turns.some((turn) => turn?.meta?.a || turn?.meta?.b)) {
    if (topLevelAMode !== "live" || topLevelBMode !== "live") {
      return {
        ok: false,
        reason: `symmetric live unavailable (${topLevelAMode || "?"}/${topLevelBMode || "?"})`,
      };
    }
    return { ok: true, reason: "" };
  }
  for (const turn of turns) {
    const aMode = String(turn?.meta?.a?.provider_mode || "").trim().toLowerCase();
    const bMode = String(turn?.meta?.b?.provider_mode || "").trim().toLowerCase();
    if (aMode !== "live" || bMode !== "live") {
      return {
        ok: false,
        reason: `symmetric live unavailable (${aMode || "?"}/${bMode || "?"})`,
      };
    }
  }
  return { ok: true, reason: "" };
}

function normalizePublicFixedDemoResult(data) {
  return {
    ...data,
    mode: "public-fixed",
    warning: null,
    provider_statuses: {
      openai: { mode: "live", reason: "" },
      anthropic: { mode: "mock", reason: "disabled" },
      gemini: { mode: "mock", reason: "disabled" },
      judge: { mode: "mock", reason: "judge disabled" },
      ...(data?.provider_statuses || {}),
    },
  };
}

async function loadPublicFixedDemoResult() {
  publicFixedDemoLog("fixture_fetch_started", PUBLIC_FIXED_CASE.fixture_url);
  const response = await fetch(PUBLIC_FIXED_CASE.fixture_url, { cache: "no-store" });
  const data = await parseResponse(response);
  if (!response.ok || !data?.ok) {
    publicFixedDemoLog("fixture_fetch_failed", {
      status: response.status,
      error: data?.error || "",
    });
    throw new Error(normalizeApiError("fixed_demo", response.status, data));
  }
  publicFixedDemoLog("fixture_fetch_succeeded");
  return normalizePublicFixedDemoResult(data);
}

async function runPublicFixedDemo() {
  publicFixedDemoLog("public_fixed_demo_branch_entered");
  if (runButton.disabled) {
    publicFixedDemoLog("run_blocked_by_busy_state");
    return;
  }
  const topic = document.querySelector("#topic")?.value?.trim() || "";
  const sideA = document.querySelector("#side-a")?.value?.trim() || "";
  const sideB = document.querySelector("#side-b")?.value?.trim() || "";
  if (!topic || !sideA || !sideB) {
    publicFixedDemoLog("run_blocked_by_validation", { topic: Boolean(topic), sideA: Boolean(sideA), sideB: Boolean(sideB) });
    setStatus("error", "Fixed demo not ready");
    setHint("固定ケースの値が正しく入っていません。");
    return;
  }
  currentPayload = {
    topic: PUBLIC_FIXED_CASE.topic,
    side_a: PUBLIC_FIXED_CASE.side_a,
    side_b: PUBLIC_FIXED_CASE.side_b,
    keyword: "",
    turn_count: PUBLIC_FIXED_CASE.turn_count,
    mode: PUBLIC_FIXED_CASE.mode,
    fighter_a_provider: PUBLIC_FIXED_CASE.fighter_a_provider,
    fighter_b_provider: PUBLIC_FIXED_CASE.fighter_b_provider,
  };
  currentFighters = { a: "openai", b: "openai", judge: "judge" };
  currentResult = null;
  currentRecordId = null;
  currentLoadedRecord = null;
  setReadingMode(false);
  setRevealState(true);
  judgeButton.hidden = true;
  judgeButton.disabled = true;
  outputMetaEl.textContent = `${PUBLIC_FIXED_CASE.turn_count} turns · fixed demo`;
  outputMetaEl.hidden = false;
  outputMetaEl.style.display = "";
  try {
    setStatus("running", "Checking server");
    setHint("");
    await ensureApiHealthBeforeRun();
  } catch (error) {
    clearCurrentResultView();
    outputMetaEl.textContent = `${PUBLIC_FIXED_CASE.turn_count} turns · blocked`;
    outputMetaEl.hidden = false;
    outputMetaEl.style.display = "";
    setStatus("error", "Live unavailable");
    const message = String(error?.message || "Backend not responding");
    setHint(message);
    setRunMetaForImmediateFailure(`Live unavailable: ${message}`);
    return;
  }
  try {
    setStatus("running", "Checking models");
    setHint("");
    const preflight = await runProviderPreflight(currentPayload);
    if (!preflight.ok) {
      clearCurrentResultView();
      outputMetaEl.textContent = `${PUBLIC_FIXED_CASE.turn_count} turns · blocked`;
      outputMetaEl.hidden = false;
      outputMetaEl.style.display = "";
      const reason = String(preflight.error || "Model check failed");
      setStatus("error", "Live unavailable");
      setHint(reason);
      setRunMetaForImmediateFailure(`Live unavailable: ${reason}`);
      return;
    }
  } catch (error) {
    clearCurrentResultView();
    outputMetaEl.textContent = `${PUBLIC_FIXED_CASE.turn_count} turns · blocked`;
    outputMetaEl.hidden = false;
    outputMetaEl.style.display = "";
    const reason = String(error?.message || "Model check failed");
    setStatus("error", "Live unavailable");
    setHint(reason);
    setRunMetaForImmediateFailure(`Live unavailable: ${reason}`);
    return;
  }
  setStatus("running", "Running fixed debate");
  beginDebateTimer();
  topicDisplayEl.textContent = formatTopicDisplay(PUBLIC_FIXED_CASE.topic, "");
  runButton.disabled = true;
  try {
    publicFixedDemoLog("fixed_live_loader_entered");
    const response = await fetch(endpointUrl("/api/debate_v4"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentPayload),
    });
    const data = await parseResponse(response);
    if (!response.ok || !data?.ok) {
      throw new Error(normalizeApiError("debate", response.status, data));
    }
    if (String(data?.mode || "").toLowerCase() !== "live") {
      throw new Error(String(data?.error || "Live unavailable"));
    }
    const symmetricLive = isSymmetricLiveFixedResult(data);
    if (!symmetricLive.ok) {
      throw new Error(`Blocked: symmetric live unavailable (${symmetricLive.reason})`);
    }
    data.elapsed_seconds = finishDebateTimer("completed");
    setRunMetaForResult("Completed in", data.elapsed_seconds, data.mode, data.provider_statuses || {});
    renderResult(data);
    publicFixedDemoLog("fixed_live_loader_completed");
    setStatus("ok", "Debate ready");
    setHint("");
  } catch (error) {
    publicFixedDemoLog("fixed_live_loader_failed", String(error?.message || error));
    currentResult = null;
    currentRecordId = null;
    currentLoadedRecord = null;
    setRevealState(true);
    destroyExpansionIntro();
    destroyVerdictStrip();
    destroyGeminiQuote();
    destroyAnalysisPanel();
    turnLogEl.innerHTML = "";
    outputMetaEl.textContent = `${PUBLIC_FIXED_CASE.turn_count} turns · blocked`;
    const failedSeconds = finishDebateTimer("failed");
    const message = String(error?.message || "Live unavailable");
    setRunMetaForResult("Blocked after", failedSeconds, "failed", {});
    setStatus("error", "Live unavailable");
    setHint(message);
  } finally {
    runButton.disabled = false;
    syncSaveButton();
  }
}

function applyPublicFixedDemoDefaults() {
  const betaEntryLinkEl = document.querySelector("#beta-entry-link");
  const fixedEntryLinkEl = document.querySelector("#fixed-entry-link");
  if (betaEntryLinkEl) betaEntryLinkEl.hidden = !shouldUsePublicFixedDemo();
  if (fixedEntryLinkEl) fixedEntryLinkEl.hidden = !BETA_MODE;
  if (!shouldUsePublicFixedDemo()) return;
  publicFixedDemoLog("public_fixed_demo_enabled");
  document.body.classList.add("public-fixed-demo");
  if (publicFixedDemoNoteEl) publicFixedDemoNoteEl.hidden = false;
  if (demoModeBadgeEl) {
    demoModeBadgeEl.hidden = false;
    demoModeBadgeEl.textContent = "Fixed case demo";
  }
  document.querySelector("#topic").value = PUBLIC_FIXED_CASE.topic;
  document.querySelector("#side-a").value = PUBLIC_FIXED_CASE.side_a;
  document.querySelector("#side-b").value = PUBLIC_FIXED_CASE.side_b;
  if (keywordInput) keywordInput.value = "";
  document.querySelector("#topic").readOnly = true;
  document.querySelector("#side-a").readOnly = true;
  document.querySelector("#side-b").readOnly = true;
  if (keywordInput) keywordInput.readOnly = true;
  fighterAProviderInput.value = PUBLIC_FIXED_CASE.fighter_a_provider;
  fighterBProviderInput.value = PUBLIC_FIXED_CASE.fighter_b_provider;
  fighterAProviderInput.disabled = true;
  fighterBProviderInput.disabled = true;
  document.querySelector("#openai-key").value = "";
  document.querySelector("#anthropic-key").value = "";
  document.querySelector("#gemini-key").value = "";
  document.querySelector("#openai-key").disabled = true;
  document.querySelector("#anthropic-key").disabled = true;
  document.querySelector("#gemini-key").disabled = true;
  setTurnCountSelection(PUBLIC_FIXED_CASE.turn_count);
  turnCountButtons.forEach((button) => {
    button.disabled = true;
  });
  document.querySelectorAll('input[name="debateMode"]').forEach((input) => {
    input.disabled = true;
    input.checked = input.value === PUBLIC_FIXED_CASE.mode;
  });
  runButton.textContent = "Run Fixed Debate";
}

function historyStorageKey() {
  const host = window.location.host || "unknown-host";
  return `mmar.debate.history.v1:${host}:${currentModeLabel()}`;
}

function normalizeTurnCount(value) {
  return Number(value) === 5 ? 5 : 3;
}

function selectedTurnCount() {
  return normalizeTurnCount(turnCountInput?.value);
}

function setTurnCountSelection(value) {
  const normalized = normalizeTurnCount(value);
  if (turnCountInput) turnCountInput.value = String(normalized);
  turnCountButtons.forEach((button) => {
    const active = normalizeTurnCount(button.dataset.turnCountOption) === normalized;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  return normalized;
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

function setRunMeta(text, visible, kind = "") {
  runMetaEl.textContent = text;
  runMetaEl.hidden = !visible;
  runMetaEl.style.display = visible ? "" : "none";
  runMetaEl.className = `meta-chip${kind ? ` ${kind}` : ""}`;
}

function clearDebateTimer() {
  if (activeDebateTimerId) {
    window.clearInterval(activeDebateTimerId);
    activeDebateTimerId = null;
  }
  activeDebateStartedAt = 0;
}

function elapsedSecondsSince(startedAt = activeDebateStartedAt) {
  if (!startedAt) return 0;
  return Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
}

function buildProgressMeta(label, estimate, seconds) {
  const waitingText = seconds >= 20 ? "応答待ち中" : "進行中";
  return `${label} · ${estimate} · ${waitingText} (${seconds}s)`;
}

function beginDebateTimer(label = "3ターンの討論を生成中", estimate = "約60〜120秒") {
  clearDebateTimer();
  currentElapsedSeconds = null;
  activeDebateStartedAt = Date.now();
  setRunMeta(buildProgressMeta(label, estimate, 0), true, "running");
  activeDebateTimerId = window.setInterval(() => {
    setRunMeta(buildProgressMeta(label, estimate, elapsedSecondsSince()), true, "running");
  }, 1000);
}

function finishDebateTimer(state) {
  const seconds = elapsedSecondsSince();
  clearDebateTimer();
  currentElapsedSeconds = seconds;
  if (state === "completed") {
    setRunMeta(`Completed in ${seconds}s`, true, "ok");
    return seconds;
  }
  if (state === "failed") {
    setRunMeta(`Failed after ${seconds}s`, true, "error");
    return seconds;
  }
  setRunMeta("Ready", true);
  return seconds;
}

function formatRunModeMeta(mode, providerStatuses = {}) {
  const normalizedMode = String(mode || "").trim().toLowerCase();
  if (normalizedMode === "live") return "Live";
  if (normalizedMode === "failed" || normalizedMode === "live-failed") return "Failed";
  if (normalizedMode === "mock-fallback") {
    const fallbackEntry = Object.entries(providerStatuses || {}).find(([providerKey, info]) => {
      if (providerKey === "judge") return false;
      return String(info?.mode || "").toLowerCase() === "mock-fallback";
    });
    if (!fallbackEntry) return "Mock fallback";
    const [providerKey, info] = fallbackEntry;
    const issue = classifyProviderIssue(info?.mode, info?.reason, info?.raw_reason);
    if (["bad_request", "auth_error", "model_access_error", "model_not_found"].includes(issue)) {
      return `Mock fallback (${modelLabelForProvider(providerKey)} unavailable)`;
    }
    return `Mock fallback (${modelLabelForProvider(providerKey)})`;
  }
  return normalizedMode ? normalizedMode.replace(/-/g, " ") : "";
}

function setRunMetaForResult(prefix, seconds, mode, providerStatuses = {}) {
  const modeMeta = formatRunModeMeta(mode, providerStatuses);
  setRunMeta(`${prefix} ${seconds}s${modeMeta ? ` · ${modeMeta}` : ""}`, true, "ok");
}

function setRunMetaForImmediateFailure(message) {
  clearDebateTimer();
  currentElapsedSeconds = 0;
  setRunMeta(message, true, "error");
}

function formatElapsedSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  return `${Math.round(seconds)}s`;
}

function renderRuntimeFingerprint() {
  const health = currentHealthInfo?.data || null;
  const visible = currentHealthInfo?.status === "ok" && !!health && shouldShowRuntimeFingerprint(health);
  if (runtimeFingerprintEl) {
    if (!visible) {
      runtimeFingerprintEl.hidden = true;
      runtimeFingerprintEl.style.display = "none";
      runtimeFingerprintEl.textContent = "";
    } else {
      const parts = [
        String(health.api_base || "").trim(),
        String(health.build_sha || "").trim(),
        String(health.boot_at || "").trim(),
        String(health.env_tag || "").trim(),
        String(health.history_store_id || "").trim(),
      ].filter(Boolean);
      runtimeFingerprintEl.hidden = false;
      runtimeFingerprintEl.style.display = "";
      runtimeFingerprintEl.textContent = parts.join(" · ");
    }
  }
  if (!runtimeDiagnosticEl) return;
  if (!visible) {
    runtimeDiagnosticEl.hidden = true;
    runtimeDiagnosticEl.style.display = "none";
    runtimeDiagnosticEl.textContent = "";
    return;
  }
  const details = [];
  if (health.history_count !== undefined) {
    details.push(`history ${health.history_count}`);
  }
  runtimeDiagnosticEl.hidden = details.length === 0;
  runtimeDiagnosticEl.style.display = details.length === 0 ? "none" : "";
  runtimeDiagnosticEl.textContent = details.join(" · ");
}

function refreshStatusRow() {
  statusRowEl.hidden = statusEl.hidden && errorHintEl.hidden;
}

function setRevealState(hidden) {
  analysisHidden = hidden;
  if (hidden) {
    setHint("");
  }
  saveButton.hidden = hidden || READ_ONLY_DEMO;
  saveButton.disabled = hidden || !currentResult || READ_ONLY_DEMO;
  if (hidden) {
    toggleAskPanel(false);
    destroyExpansionIntro();
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
  isReaderMode = Boolean(active);
  pageShellEl.classList.toggle("reading-mode", isReaderMode);
  inputPanelEl?.classList.toggle("reader-collapsed", isReaderMode);
  if (readerControlsEl) {
    readerControlsEl.hidden = !isReaderMode;
    readerControlsEl.style.display = isReaderMode ? "" : "none";
  }
}

function renderEmptyTurnLog() {
  const emptyCopy = isBattleMode() ? battleCopy().emptyTurnLog : DEBATE_FORM_COPY.emptyTurnLog;
  turnLogEl.innerHTML = `
    <div class="empty-state">
      ${escapeHtml(emptyCopy)}
    </div>
  `;
}

function clearCurrentResultView() {
  currentResult = null;
  currentRecordId = null;
  currentLoadedRecord = null;
  currentConstraintReport = null;
  currentJudgePass1 = null;
  currentJudgePass2 = null;
  currentStoryAlignReport = null;
  setRevealState(true);
  destroyExpansionIntro();
  destroyVerdictStrip();
  destroyGeminiQuote();
  destroyAnalysisPanel();
  renderDebugPipeline();
  renderRuntimeFingerprint();
  renderEmptyTurnLog();
  clearPublicSummary();
  clearDebateTimer();
  currentElapsedSeconds = null;
  setRunMeta("Ready", true);
  outputMetaEl.textContent = `${selectedTurnCount()} turns · pending`;
  outputMetaEl.hidden = false;
  outputMetaEl.style.display = "";
  topicDisplayEl.textContent = document.querySelector("#topic")?.value.trim() || "Topic";
  syncSaveButton();
  syncAskButton();
  syncDetailLikeButton();
  renderBattleSourceCard();
  syncShareButton();
  applyRequestedBattleFocus();
}

function clearPublicSummary() {
  if (!publicSummaryEl) return;
  publicSummaryEl.hidden = true;
  publicSummaryEl.style.display = "none";
  publicSummaryEl.setAttribute("aria-hidden", "true");
  publicSummaryEl.innerHTML = "";
  if (publicSummaryWinnerEl) publicSummaryWinnerEl.textContent = "-";
  if (publicSummaryReasonEl) publicSummaryReasonEl.textContent = "-";
}

function renderPublicSummary(summary) {
  clearPublicSummary();
  if (!publicSummaryEl) return;
  const noteEl = document.createElement("p");
  noteEl.className = "public-summary-note";
  noteEl.textContent = "次は判定を見る";
  publicSummaryEl.append(noteEl);
  publicSummaryEl.hidden = false;
  publicSummaryEl.style.display = "";
  publicSummaryEl.setAttribute("aria-hidden", "false");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function sanitizeExternalUrl(value, options = {}) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw, window.location.origin);
    const protocol = String(parsed.protocol || "").toLowerCase();
    if (protocol !== "https:" && protocol !== "http:") return "";
    if (options.xOnly) {
      const host = String(parsed.hostname || "").toLowerCase();
      if (host !== "x.com" && host !== "www.x.com") return "";
    }
    return parsed.toString();
  } catch {
    return "";
  }
}

function safeSetExternalHref(element, value, options = {}) {
  if (!element) return "";
  const safeUrl = sanitizeExternalUrl(value, options);
  element.href = safeUrl || "#";
  element.setAttribute("rel", "noreferrer noopener");
  element.setAttribute("target", "_blank");
  element.hidden = !safeUrl;
  element.setAttribute("aria-hidden", safeUrl ? "false" : "true");
  return safeUrl;
}

function normalizeArrayValue(value) {
  if (Array.isArray(value)) {
    return value.map((item, index) => `${index + 1}. ${item}`).join("\n");
  }
  return String(value ?? "未生成");
}

function stringifyTurningPointValue(value) {
  if (typeof value === "string") return value.trim();
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  const candidates = [
    value.text,
    value.summary,
    value.explanation,
    value.reason,
    value.why,
    value.value,
  ].filter(Boolean).map((item) => String(item).trim()).filter(Boolean);
  return candidates[0] || "";
}

function fatalPhraseTextCandidate(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  return [
    value.text,
    value.quote_excerpt,
    value.quote,
    value.excerpt,
    value.raw_text,
    value.reason,
  ].filter(Boolean).map((item) => String(item).trim()).find(Boolean) || "";
}

function normalizeFatalPhrase(summary) {
  const value = summary?.fatal_phrase;
  const turning = normalizeTurningPoint(summary);
  if (!value) {
    return {
      turn: extractTurnNumber(turning.turn) || 3,
      speaker: "?",
      quote: "",
      why: "",
      structural_role: "",
      pick_reason: "",
      _debug_source: "blank",
      _debug_template_applied: false,
    };
  }
  if (typeof value === "string") {
    return {
      turn: extractTurnNumber(turning.turn) || 3,
      speaker: "?",
      quote: `「${value}」`,
      why: "",
      structural_role: "",
      pick_reason: "",
      _debug_source: "string",
      _debug_template_applied: false,
    };
  }
  const text = fatalPhraseTextCandidate(value);
  return {
    turn: Number(value.turn) || extractTurnNumber(turning.turn) || 3,
    speaker: value.speaker || "?",
    quote: text ? `「${text.replace(/^「|」$/g, "")}」` : "",
    why: String(value.reason || value.explanation || value.summary || "").trim(),
    role: String(value.role || "decisive_lock").trim(),
    axis_tag: String(value.axis_tag || "").trim(),
    structural_role: String(value.structural_role || "").trim(),
    pick_reason: String(value.pick_reason || "").trim(),
    _debug_source: text ? (value.quote || value.text ? "transcript_quote" : "backfilled") : "blank",
    _debug_template_applied: false,
  };
}

function formatCardRoleLabel(value) {
  const role = String(value || "").trim();
  const labels = {
    verdict_summary: "Verdict",
    first_crack: "Early break",
    decisive_lock: "Decisive line",
    frame_shift: "Turning point",
    failure_exposure: "Core weakness",
    clincher: "Closing turn",
    ai_framing: "Takeaway",
  };
  return labels[role] || "";
}

function formatStructuralRoleLabel(value) {
  const role = String(value || "").trim();
  const labels = isEnglishBattleView()
    ? {
        rule_capture: "Rules locked",
        definition_lock: "Definition locked",
        category_reframe: "Category shift",
        burden_shift: "Burden shifted",
        counterexample_land: "Counterexample landed",
        drift_exposure: "Claim drift exposed",
        decisive_frame: "Decisive frame",
      }
    : {
        rule_capture: "ルール奪取",
        definition_lock: "定義固定",
        category_reframe: "カテゴリ再定義",
        burden_shift: "立証責任固定",
        counterexample_land: "反例着地",
        drift_exposure: "条件後退露出",
        decisive_frame: "決定枠確定",
      };
  return labels[role] || "";
}

function formatAxisTagLabel(value) {
  const role = String(value || "").trim();
  const labels = isEnglishBattleView()
    ? {
        "Means for essence": "Means for essence",
        "Exception escape": "Exception escape",
        "Generalization shift": "Generalization shift",
        "Time shift": "Time shift",
        "Proof threshold shift": "Proof threshold shift",
        "Axis shift": "Axis shift",
        "Scope substitution": "Scope substitution",
        "Contract drift": "Contract drift",
        "Frame survival": "Frame survival",
        "Burden shift": "Burden shift",
        "Residue": "Residue",
      }
    : {
        "Means for essence": "手段→本質ずらし",
        "Exception escape": "例外逃避",
        "Generalization shift": "一般化ずらし",
        "Time shift": "時間軸ずらし",
        "Proof threshold shift": "立証閾値ずらし",
        "Axis shift": "比較軸ずらし",
        "Scope substitution": "問いの再発明",
        "Contract drift": "Contract drift",
        "Frame survival": "Frame survival",
        "Burden shift": "Burden shift",
        "Residue": "残差責任",
      };
  return labels[role] || role;
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
      role: String(raw.role || "failure_exposure").trim(),
      axis_tag: String(raw.axis_tag || "").trim(),
      label: isEnglishBattleView() ? polishEnglishWeakSpotLabel(raw.label || defaultLabel) : (raw.label || defaultLabel),
      quote_excerpt: raw.quote_excerpt || raw.quote || raw.text || "相手に最も刺された弱点がここで露出した。",
      why_one_sentence: raw.why_one_sentence || raw.why || defaultWhy,
      how_to_fix: raw.how_to_fix || defaultFix,
    };
  }
  return {
    side: defaultSide,
    turn: defaultTurn,
    speaker: defaultSpeaker,
    role: "failure_exposure",
    label: isEnglishBattleView() ? polishEnglishWeakSpotLabel(defaultLabel) : defaultLabel,
    quote_excerpt: summary?.contradiction_exposed || "相手に最も刺された弱点がここで露出した。",
    why_one_sentence: summary?.contradiction_exposed || defaultWhy,
    how_to_fix: defaultFix,
  };
}

function normalizeTurningPoint(value) {
  const raw = typeof value === "object" && !Array.isArray(value) && value?.turning_point ? value.turning_point : value;
  const winnerSide = typeof value === "object" && !Array.isArray(value) ? normalizeWinner(value).side : "Draw";
  const summary = stringifyTurningPointValue(raw);
  const turn = extractTurnNumber(summary || raw);
  return {
    turn: turn ? `Turn ${turn}` : "Turn ?",
    role: typeof raw === "object" && raw && !Array.isArray(raw) ? String(raw.role || "frame_shift").trim() : "frame_shift",
    axis_tag: typeof raw === "object" && raw && !Array.isArray(raw) ? String(raw.axis_tag || "").trim() : "",
    summary: summary || (typeof raw === "string" ? normalizeArrayValue(raw) : "") || (winnerSide === "Draw" ? "流れは動いたが、どちらも決定打を最後まで押し切れなかった。" : "流れが変わった場所は見えている。"),
    quote_excerpt: typeof raw === "object" && raw && !Array.isArray(raw) ? String(raw.quote_excerpt || "").trim() : "",
    _debug_source: summary ? "object" : (typeof raw === "string" && raw ? "string" : "template"),
  };
}

function normalizeTimelineQuote(value, fallbackRole) {
  const raw = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    turn: Number(raw.turn) || 0,
    speaker: String(raw.speaker || "").trim().toUpperCase(),
    quote: String(raw.quote || raw.text || "").trim(),
    reason: String(raw.reason || "").trim(),
    role: String(raw.role || fallbackRole || "").trim(),
  };
}

function normalizeFirstCrack(summary) {
  return normalizeTimelineQuote(summary?.first_crack, "first_crack");
}

function normalizeClincher(summary) {
  return normalizeTimelineQuote(summary?.clincher, "clincher");
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
  const stripped = quote.replace(/^["“”'「」]+|["“”'「」]+$/g, "");
  if (isEnglishBattleView()) return `"${stripped}"`;
  return `「${stripped}」`;
}

function normalizeGeminiQuote(summary) {
  const raw = summary?.gemini_quote;
  if (raw && typeof raw === "object" && String(raw.framing_text || raw.text || "").trim()) {
    const framingText = String(raw.framing_text || raw.text || "").trim();
    const evidenceQuote = String(raw.evidence_quote || raw.quote || "").trim();
    if (!looksLikeGenericGeminiQuote(framingText)) {
      return {
        framing_text: normalizeTakeawayQuote(framingText),
        role: "ai_framing",
        framing_role: String(raw.framing_role || raw.structural_role || "").trim(),
        framing_reason: String(raw.framing_reason || raw.pick_reason || "").trim(),
        evidence_quote: evidenceQuote,
        evidence_turn: Number(raw.evidence_turn || raw.source_turn) || 0,
        evidence_side: String(raw.evidence_side || raw.source_side || "").trim().toUpperCase(),
        evidence_match_confidence: Number(raw.evidence_match_confidence || raw.match_confidence) || 0,
        verdict_consistency: raw.verdict_consistency !== false,
        consistency_reason: String(raw.consistency_reason || "").trim(),
        structural_role: String(raw.framing_role || raw.structural_role || "").trim(),
        pick_reason: String(raw.framing_reason || raw.pick_reason || "").trim(),
        text: normalizeTakeawayQuote(framingText),
        quote: evidenceQuote,
        source_turn: Number(raw.evidence_turn || raw.source_turn) || 0,
        source_side: String(raw.evidence_side || raw.source_side || "").trim().toUpperCase(),
        match_confidence: Number(raw.evidence_match_confidence || raw.match_confidence) || 0,
        _debug_source: String(raw.debug_source || (evidenceQuote || framingText ? "transcript_quote" : "backfilled")),
      };
    }
  }
  const winner = normalizeWinner(summary);
  const weakSpot = normalizeWeakSpot(summary);
  const turning = normalizeTurningPoint(summary);
  const concepts = extractGeminiQuoteConcepts(summary, turning, weakSpot);
  const primary = concepts[0] || "";
  const secondary = concepts[1] || "";
  const label = String(weakSpot.label || "");
  if (label === "定義の後退" && primary && secondary) return { framing_text: normalizeTakeawayQuote(`${primary}を広げても、${secondary}は守れない。`), role: "ai_framing", framing_role: "definition_lock", framing_reason: "定義を固定した場面を要約した。", evidence_quote: "", evidence_turn: 0, evidence_side: "", evidence_match_confidence: 0, verdict_consistency: true, consistency_reason: "generated_fallback", structural_role: "definition_lock", pick_reason: "定義を固定した場面を要約した。", text: normalizeTakeawayQuote(`${primary}を広げても、${secondary}は守れない。`), quote: "", source_turn: 0, source_side: "", match_confidence: 0, _debug_source: "generated_fallback" };
  if (label === "循環論法" && primary) return { framing_text: normalizeTakeawayQuote(`${primary}の言い換えでは、穴は埋まらない。`), role: "ai_framing", framing_role: "burden_shift", framing_reason: "立証責任が残った点を要約した。", evidence_quote: "", evidence_turn: 0, evidence_side: "", evidence_match_confidence: 0, verdict_consistency: true, consistency_reason: "generated_fallback", structural_role: "burden_shift", pick_reason: "立証責任が残った点を要約した。", text: normalizeTakeawayQuote(`${primary}の言い換えでは、穴は埋まらない。`), quote: "", source_turn: 0, source_side: "", match_confidence: 0, _debug_source: "generated_fallback" };
  if (label === "未応答" && primary) return { framing_text: normalizeTakeawayQuote(`${primary}に答えないままでは、勝ちは作れない。`), role: "ai_framing", framing_role: "decisive_frame", framing_reason: "未応答のまま残った構造を要約した。", evidence_quote: "", evidence_turn: 0, evidence_side: "", evidence_match_confidence: 0, verdict_consistency: true, consistency_reason: "generated_fallback", structural_role: "decisive_frame", pick_reason: "未応答のまま残った構造を要約した。", text: normalizeTakeawayQuote(`${primary}に答えないままでは、勝ちは作れない。`), quote: "", source_turn: 0, source_side: "", match_confidence: 0, _debug_source: "generated_fallback" };
  if (winner.side === "Draw" && primary && secondary) return { framing_text: normalizeTakeawayQuote(`${primary}は揺れたが、${secondary}までは折れなかった。`), role: "ai_framing", framing_role: "decisive_frame", framing_reason: "流れは動いたが決め切れなかった構図を要約した。", evidence_quote: "", evidence_turn: 0, evidence_side: "", evidence_match_confidence: 0, verdict_consistency: true, consistency_reason: "generated_fallback", structural_role: "decisive_frame", pick_reason: "流れは動いたが決め切れなかった構図を要約した。", text: normalizeTakeawayQuote(`${primary}は揺れたが、${secondary}までは折れなかった。`), quote: "", source_turn: 0, source_side: "", match_confidence: 0, _debug_source: "generated_fallback" };
  if (winner.side === "A" && primary && secondary) return { framing_text: normalizeTakeawayQuote(`${primary}は残り、${secondary}が先に崩れた。`), role: "ai_framing", framing_role: "decisive_frame", framing_reason: "勝者の論旨が残った構図を要約した。", evidence_quote: "", evidence_turn: 0, evidence_side: "", evidence_match_confidence: 0, verdict_consistency: true, consistency_reason: "generated_fallback", structural_role: "decisive_frame", pick_reason: "勝者の論旨が残った構図を要約した。", text: normalizeTakeawayQuote(`${primary}は残り、${secondary}が先に崩れた。`), quote: "", source_turn: 0, source_side: "", match_confidence: 0, _debug_source: "generated_fallback" };
  if (winner.side === "B" && primary && secondary) return { framing_text: normalizeTakeawayQuote(`${primary}は残らず、${secondary}が最後まで刺さった。`), role: "ai_framing", framing_role: "decisive_frame", framing_reason: "勝者の論旨が最後まで刺さった構図を要約した。", evidence_quote: "", evidence_turn: 0, evidence_side: "", evidence_match_confidence: 0, verdict_consistency: true, consistency_reason: "generated_fallback", structural_role: "decisive_frame", pick_reason: "勝者の論旨が最後まで刺さった構図を要約した。", text: normalizeTakeawayQuote(`${primary}は残らず、${secondary}が最後まで刺さった。`), quote: "", source_turn: 0, source_side: "", match_confidence: 0, _debug_source: "generated_fallback" };
  if (primary) return { framing_text: normalizeTakeawayQuote(`${primary}を守れない理屈は、長く持たない。`), role: "ai_framing", framing_role: "decisive_frame", framing_reason: "核を守れなかった構図を要約した。", evidence_quote: "", evidence_turn: 0, evidence_side: "", evidence_match_confidence: 0, verdict_consistency: true, consistency_reason: "generated_fallback", structural_role: "decisive_frame", pick_reason: "核を守れなかった構図を要約した。", text: normalizeTakeawayQuote(`${primary}を守れない理屈は、長く持たない。`), quote: "", source_turn: 0, source_side: "", match_confidence: 0, _debug_source: "generated_fallback" };
  return { framing_text: "「その試合の穴を突いた側が残った。」", role: "ai_framing", framing_role: "decisive_frame", framing_reason: "勝敗を決めた構図を短く要約した。", evidence_quote: "", evidence_turn: 0, evidence_side: "", evidence_match_confidence: 0, verdict_consistency: true, consistency_reason: "generated_fallback", structural_role: "decisive_frame", pick_reason: "勝敗を決めた構図を短く要約した。", text: "「その試合の穴を突いた側が残った。」", quote: "", source_turn: 0, source_side: "", match_confidence: 0, _debug_source: "generated_fallback" };
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

function hasCompletedJudgePipeline(summary) {
  return Boolean(summary?.debug_pass1 && summary?.debug_pass2 && summary?.debug_story_align_report);
}

function providerStatusesForDisplay(providerStatuses, summary) {
  const next = {
    ...(providerStatuses || {}),
    openai: { ...(providerStatuses?.openai || {}) },
    anthropic: { ...(providerStatuses?.anthropic || {}) },
    gemini: { ...(providerStatuses?.gemini || {}) },
    judge: { ...(providerStatuses?.judge || {}) },
  };
  if (hasCompletedJudgePipeline(summary)) {
    next.judge = {
      ...(next.judge || {}),
      mode: "live",
      reason: "",
    };
  }
  return next;
}

function classifyProviderIssue(mode, reason, rawReason = "") {
  const text = String(reason || "").trim().toLowerCase();
  const raw = String(rawReason || reason || "").trim().toLowerCase();
  const normalizedCodes = new Set([
    "timeout",
    "provider_error",
    "schema_mismatch",
    "json_parse_error",
    "auth_error",
    "model_not_found",
    "model_access_error",
    "bad_request",
    "safety_block",
    "empty_response",
  ]);
  if (mode === "mock") return "mock";
  if (mode === "mock-fallback") {
    if (normalizedCodes.has(text)) return text;
    if (raw.includes("timeout")) return "timeout";
    if (raw.includes("provider_error")) return "provider_error";
    if (raw.includes("schema")) return "schema_mismatch";
    if (raw.includes("json")) return "json_parse_error";
    if (raw.includes("auth")) return "auth_error";
    if (raw.includes("model") && (raw.includes("access") || raw.includes("permission") || raw.includes("authorized") || raw.includes("forbidden"))) return "model_access_error";
    if (raw.includes("model")) return "model_not_found";
    if (raw.includes("400") || raw.includes("bad request") || raw.includes("invalid argument")) return "bad_request";
    return "fallback_generated";
  }
  if (mode === "live-ready") return "pending";
  return mode || "unknown";
}

function formatProviderToken(label, providerKey, providerStatuses) {
  const info = providerStatuses?.[providerKey] || {};
  const mode = info.mode || "mock";
  if (mode === "live") return `${label} live`;
  return `${label} ${classifyProviderIssue(mode, info.reason, info.raw_reason)}`;
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

function buildOutputMeta(providerStatuses, turnCount, mode, savedOutputMeta = "", options = {}) {
  const { preferSaved = false } = options;
  const normalizedSavedOutputMeta = normalizeSavedOutputMeta(savedOutputMeta);
  if (preferSaved && normalizedSavedOutputMeta) return normalizedSavedOutputMeta;
  const countText = `${turnCount} turns`;
  if (mode === "public-fixed") {
    return `${countText} · fixed demo · fixture`;
  }
  return countText;
}

function buildAbnormalHint(providerStatuses) {
  return "";
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

function composeEnglishVerdictHeadline(topic, winner) {
  const side = winner?.side || "Draw";
  if (side === "Draw") return "No clear winner";
  return `${formatBattleSideLabel(side)} had the stronger frame`;
}

function composeEnglishVerdictSubline(topic, winner, why) {
  const side = winner?.side || "Draw";
  if (side === "Draw") return "Neither side fully closed the case.";
  return `${formatBattleSideLabel(side)} came out ahead.`;
}

function composeEnglishFlipCondition(winner, weakSpot, why) {
  const loser = winner?.side === "A" ? "B" : winner?.side === "B" ? "A" : "Draw";
  const loserLabel = formatBattleSideLabel(loser);
  const weakLabel = polishEnglishWeakSpotLabel(weakSpot?.label || "key weakness");
  const fix = polishEnglishSurfaceText(weakSpot?.how_to_fix || weakSpot?.why_one_sentence || why || "");
  if (loser === "Draw") {
    return "To change the result, one side would need to turn the main weakness into a decisive point.";
  }
  if (weakLabel === "Shifting the Claim") {
    return `To flip the result, ${loserLabel} must stop shifting the claim and define it with concrete examples or criteria.`;
  }
  if (/less invasive|superior to/i.test(fix)) {
    return `To flip the result, ${loserLabel} must address "${weakLabel}" with concrete evidence and show why that case beats the main alternative.`;
  }
  if (fix) {
    return `To flip the result, ${loserLabel} must address "${weakLabel}" with concrete evidence or a tighter definition. ${fix}`;
  }
  return `To flip the result, ${loserLabel} must address "${weakLabel}" with concrete evidence or a tighter definition.`;
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

function canonicalHistoryCount() {
  return Array.isArray(historyRecordsCache) ? historyRecordsCache.length : 0;
}

function loadHistoryRecordsFromLocalStorage() {
  if (!storageAvailable()) return [];
  try {
    const raw = window.localStorage.getItem(historyStorageKey());
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeSavedRecordForPreview) : [];
  } catch {
    return [];
  }
}

function updateHistoryButton(count = loadHistoryRecords().length) {
  const normalizedCount = Number.isFinite(Number(count)) ? Number(count) : canonicalHistoryCount();
  historyButton.textContent = isBattleMode() ? `${battleCopy().historyBattleLabel} (${normalizedCount})` : `History (${normalizedCount})`;
  historyButton.dataset.historyTarget = isBattleMode() ? buildBattleGalleryUrl() : "drawer";
  historyCountEl.textContent = `${normalizedCount} match${normalizedCount === 1 ? "" : "es"}`;
}

function persistHistoryRecords(records) {
  if (!storageAvailable()) return;
  window.localStorage.setItem(historyStorageKey(), JSON.stringify(records));
}

async function fetchHistoryListFromServer(sort = "recent") {
  const query = sort === "likes" ? "?sort=likes" : "";
  const response = await fetch(endpointUrl(`/api/history/list${query}`), { method: "GET" });
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
    historyRecordsCache = await fetchHistoryListFromServer(historySortMode);
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

async function saveRunRecordToServer(record) {
  const response = await fetch(endpointUrl("/api/runs/save"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record),
  });
  const data = await parseResponse(response);
  if (!response.ok || !data.ok || !data.record) {
    throw new Error(normalizeApiError("run_save", response.status, data));
  }
  if (data.history_item) {
    const savedHistory = normalizeSavedRecordForPreview(data.history_item);
    const existingIndex = historyRecordsCache.findIndex((item) => item.id === savedHistory.id || item.fingerprint === savedHistory.fingerprint);
    if (existingIndex >= 0) historyRecordsCache[existingIndex] = savedHistory;
    else historyRecordsCache.unshift(savedHistory);
    persistHistoryRecords(historyRecordsCache);
    updateHistoryButton(historyRecordsCache.length);
    updateArchiveButton(historyRecordsCache.length);
    renderHistoryList();
    renderArchiveList();
  }
  return data.record;
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
  const transcriptJson = Array.isArray(record.transcript_json) ? record.transcript_json : [];
  const rawTurns = Array.isArray(record.raw_turns) && record.raw_turns.length ? record.raw_turns : transcriptJson;
  const displayTurns = Array.isArray(record.display_turns) && record.display_turns.length ? record.display_turns : transcriptJson;
  return {
    ...record,
    experience_mode: recordExperienceMode(record),
    canonical_lang: normalizeBattleLang(record.canonical_lang || "ja"),
    battle_lang: normalizeBattleLang(record.battle_lang || record.lang || "ja"),
    localized_views: normalizeLocalizedViews(record.localized_views),
    run_id: record.run_id || "",
    topic_hash: record.topic_hash || "",
    keyword: normalizeKeyword(record.keyword || ""),
    raw_turns: rawTurns,
    display_turns: displayTurns,
    transcript_json: transcriptJson,
    transcript_role: record.transcript_role || "display",
    provider_statuses: record.provider_statuses || {},
    output_meta: normalizeSavedOutputMeta(record.output_meta || ""),
    elapsed_seconds: Number.isFinite(Number(record.elapsed_seconds)) ? Math.max(0, Math.round(Number(record.elapsed_seconds))) : null,
    views: Number(record.views || 0),
    likes: Number(record.likes || 0),
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

function getRawTurns(recordOrDebate) {
  if (!recordOrDebate || typeof recordOrDebate !== "object") return [];
  if (Array.isArray(recordOrDebate.raw_turns) && recordOrDebate.raw_turns.length) return recordOrDebate.raw_turns;
  if (Array.isArray(recordOrDebate.transcript_json) && recordOrDebate.transcript_json.length) return recordOrDebate.transcript_json;
  if (Array.isArray(recordOrDebate.turns) && recordOrDebate.turns.length) return recordOrDebate.turns;
  return [];
}

function getDisplayTurns(recordOrDebate) {
  const localizedTurns = currentLocalizedBattleTurns();
  if (localizedTurns.length) return localizedTurns;
  if (!recordOrDebate || typeof recordOrDebate !== "object") return [];
  if (Array.isArray(recordOrDebate.display_turns) && recordOrDebate.display_turns.length) return recordOrDebate.display_turns;
  if (Array.isArray(recordOrDebate.transcript_json) && recordOrDebate.transcript_json.length) return recordOrDebate.transcript_json;
  if (Array.isArray(recordOrDebate.turns) && recordOrDebate.turns.length) return recordOrDebate.turns;
  return [];
}

async function incrementHistoryMetric(recordId, metric) {
  const response = await fetch(endpointUrl(`/api/history/${metric}/${encodeURIComponent(recordId)}`), {
    method: "POST",
  });
  const data = await parseResponse(response);
  if (!response.ok || !data.ok || !data.item) {
    throw new Error(normalizeApiError(`history_${metric}`, response.status, data));
  }
  const record = normalizeSavedRecordForPreview(data.item);
  const existingIndex = historyRecordsCache.findIndex((item) => item.id === record.id);
  if (existingIndex >= 0) historyRecordsCache[existingIndex] = record;
  else historyRecordsCache.unshift(record);
  if (currentRecordId === record.id) currentLoadedRecord = record;
  persistHistoryRecords(historyRecordsCache);
  renderHistoryList();
  renderArchiveList();
  syncDetailLikeButton();
  return record;
}

function sendBattleMetric(recordId, metric) {
  const id = String(recordId || "").trim();
  const action = String(metric || "").trim();
  if (!id || !action) return;
  fetch(endpointUrl(`/api/battle/${encodeURIComponent(id)}/${encodeURIComponent(action)}`), {
    method: "POST",
    keepalive: true,
  }).catch(() => {});
}

function matchFingerprint(result, payload) {
  const debate = result?.debate || {};
  const summary = debate.summary || {};
  return JSON.stringify({
    run_id: result?.run_id || debate?.run_id || "",
    topic_hash: result?.topic_hash || debate?.topic_hash || "",
    topic: debate.topic || payload?.topic || "",
    keyword: normalizeKeyword(payload?.keyword || ""),
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
  const rawTurns = getRawTurns(debate);
  const displayTurns = getDisplayTurns(debate);
  const record = {
    id: currentRecordId || result?.run_id || debate?.run_id || `match_${Date.now()}`,
    run_id: result?.run_id || debate?.run_id || "",
    topic_hash: result?.topic_hash || debate?.topic_hash || "",
    topic: debate.topic || payload?.topic || "",
    keyword: normalizeKeyword(payload?.keyword || ""),
    stance_a: payload?.side_a || "",
    stance_b: payload?.side_b || "",
    source_type: payload?.source_type || "",
    source_url: payload?.source_url || "",
    source_image: payload?.source_image || "",
    source_summary: payload?.source_summary || "",
    canonical_lang: "ja",
    battle_lang: normalizeBattleLang(payload?.battle_lang || currentBattleLang),
    localized_views: normalizeLocalizedViews(currentLoadedRecord?.localized_views),
    turn_count: debate.turn_count || payload?.turn_count || 0,
    mode: payload?.mode || "casual",
    experience_mode: currentExperienceMode,
    fighter_a_provider: currentFighters.a,
    fighter_b_provider: currentFighters.b,
    judge_provider: currentFighters.judge,
    fighter_a_model: modelLabelForProvider(currentFighters.a),
    fighter_b_model: modelLabelForProvider(currentFighters.b),
    judge_model: modelLabelForProvider(currentFighters.judge),
    transcript_json: displayTurns,
    transcript_role: "display",
    raw_turns: rawTurns,
    display_turns: displayTurns,
    judge_json: {
      ...summary,
      verdict_headline: composeVerdictHeadline(debate.topic || payload?.topic || "", winner),
      verdict_subline: composeVerdictSubline(debate.topic || payload?.topic || "", winner, why),
      momentum: normalizeMomentum(summary, winner, confidence),
      flip_condition: composeFlipCondition(winner, normalizeWeakSpot(summary), why),
      gemini_takeaway: normalizeGeminiTakeaway(summary, debate.topic || payload?.topic || ""),
      gemini_quote: summary?.gemini_quote || normalizeGeminiQuote(summary),
    },
    created_at: new Date().toISOString(),
    source_mode: result?.mode || "mock",
    provider_statuses: JSON.parse(JSON.stringify(providerStatuses)),
    output_meta: buildOutputMeta(providerStatuses, displayTurns.length, result?.mode || "mock"),
    elapsed_seconds: Number.isFinite(Number(result?.elapsed_seconds))
      ? Math.max(0, Math.round(Number(result.elapsed_seconds)))
      : (Number.isFinite(Number(currentElapsedSeconds)) ? Math.max(0, Math.round(Number(currentElapsedSeconds))) : null),
    saved_from_ui: true,
    fingerprint: matchFingerprint(result, payload),
  };
  return record;
}

function buildRunRecord(result, payload, status = "debate_complete") {
  const record = buildBattleRecord(result, payload);
  return {
    session_id: record.run_id || result?.session_id || "",
    run_id: record.run_id || result?.session_id || "",
    created_at: record.created_at,
    topic: record.topic,
    stance_a: record.stance_a,
    stance_b: record.stance_b,
    status,
    debate_result: {
      topic: record.topic,
      stance_a: record.stance_a,
      stance_b: record.stance_b,
      turn_count: record.turn_count,
      transcript_json: record.transcript_json,
      raw_turns: record.raw_turns,
      display_turns: record.display_turns,
      provider_statuses: record.provider_statuses,
      output_meta: record.output_meta,
      elapsed_seconds: record.elapsed_seconds,
      source_mode: record.source_mode,
      experience_mode: record.experience_mode,
      canonical_lang: record.canonical_lang,
      battle_lang: record.battle_lang,
      localized_views: record.localized_views,
      source_type: record.source_type,
      source_url: record.source_url,
      source_summary: record.source_summary,
      source_image: record.source_image,
    },
    judge_result: status === "judge_complete" ? record.judge_json : {},
    run_json: record,
  };
}

async function autosaveCurrentRun(status = "debate_complete") {
  if (!currentResult || !currentPayload) return null;
  try {
    return await saveRunRecordToServer(buildRunRecord(currentResult, currentPayload, status));
  } catch (error) {
    console.warn("autosave failed", error);
    return null;
  }
}

async function ensureBattleShareId() {
  const existing = currentBattleShareId();
  if (existing) return existing;
  if (!currentResult || !currentPayload) throw new Error("share_unavailable");
  const saved = await saveRunRecordToServer(buildRunRecord(currentResult, currentPayload, "debate_complete"));
  const nextId = String(saved?.run_id || saved?.session_id || "").trim();
  if (!nextId) throw new Error("share_unavailable");
  return nextId;
}

async function copyBattleShareLink() {
  try {
    const id = await ensureBattleShareId();
    const url = buildBattleShareUrl(id);
    await navigator.clipboard.writeText(url);
    sendBattleMetric(id, "share");
    setStatus("ok", currentBattleLang === "en" ? "Copied share link" : "共有リンクをコピーしました");
    setHint(url);
  } catch (error) {
    setStatus("error", currentBattleLang === "en" ? "Could not create share link" : "共有リンクを作れませんでした");
    setHint(String(error?.message || "share_unavailable"));
  }
}

function battleWinnerLabel(result = currentResult) {
  const winner = normalizeWinner(result?.debate?.summary || {});
  if (winner.side === "A" || winner.side === "B") return winner.side;
  return "保留";
}

function currentBattleIssue() {
  const localized = currentBattleDisplayView();
  return String(
    localized?.issue
      || currentResult?.debate?.topic
      || currentPayload?.topic
      || currentLoadedRecord?.topic
      || currentBattleSource?.issue
      || ""
  ).trim();
}

function buildBattleShareText(shareId = currentBattleShareId()) {
  if (!shareId) return "";
  const url = buildBattleShareUrl(shareId);
  const issue = currentBattleIssue();
  if (issue) {
    return currentBattleLang === "en"
      ? `${issue}\nVerdAIct shows the winner, turning point, and fatal phrase.\n${url}`
      : `AIバトル: ${issue}\n${url}`;
  }
  return `${battleCopy().shareFallback}\n${url}`;
}

function buildBattleXIntentUrl(text) {
  return `https://x.com/intent/post?text=${encodeURIComponent(String(text || "").trim())}`;
}

async function shareBattleOnX() {
  try {
    const id = await ensureBattleShareId();
    const shareText = buildBattleShareText(id) || `${battleCopy().shareFallback}\n${buildBattleShareUrl(id)}`;
    const intentUrl = buildBattleXIntentUrl(shareText);
    window.open(intentUrl, "_blank", "noopener,noreferrer");
    sendBattleMetric(id, "share");
    setStatus("ok", battleCopy().shareOpened);
    setHint(buildBattleShareUrl(id));
  } catch (error) {
    setStatus("error", battleCopy().shareFailed);
    setHint(String(error?.message || "share_unavailable"));
  }
}

function sharedBattleIdFromPath() {
  const match = window.location.pathname.match(/^\/battle\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function loadSharedBattleFromPath() {
  const sharedId = sharedBattleIdFromPath();
  if (!sharedId) return false;
  try {
    const response = await fetch(endpointUrl(`/api/battle/${encodeURIComponent(sharedId)}`), { method: "GET" });
    const data = await parseResponse(response);
    if (!response.ok || !data?.ok || !data?.record) {
      throw new Error(normalizeApiError("battle_item", response.status, data));
    }
    try {
      await fetch(endpointUrl(`/api/battle/${encodeURIComponent(sharedId)}/view`), { method: "POST" });
    } catch {}
    loadRecordIntoView(data.record, { saved: false });
    setStatus("ok", currentBattleLang === "en" ? "Showing shared battle" : "共有バトルを表示中");
    setHint("");
    return true;
  } catch (error) {
    setStatus("error", REQUESTED_BATTLE_LANG === "en" ? "Could not open shared battle" : "共有バトルを開けませんでした");
    setHint(String(error?.message || "not found"));
    return false;
  }
}

function currentMatchContextKey() {
  if (currentLoadedRecord?.run_id) return `run:${currentLoadedRecord.run_id}`;
  if (currentLoadedRecord?.id && !currentRecordId) return `viewer:${currentLoadedRecord.id}`;
  if (currentRecordId && currentLoadedRecord?.run_id) return `saved:${currentRecordId}:${currentLoadedRecord.run_id}`;
  if (currentRecordId) return `saved:${currentRecordId}`;
  if (currentResult?.run_id) return `run:${currentResult.run_id}`;
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
  currentAskReferences = [];
  if (askInputEl) askInputEl.value = "";
}

function shouldShowAskHint() {
  const key = currentMatchContextKey();
  return key !== "none" && !dismissedAskHints.has(key);
}

function askReferenceKey(reference) {
  return [
    reference?.kind || "",
    reference?.turn || "",
    reference?.speaker || "",
    normalizeSearchText(reference?.quote || reference?.summary || ""),
  ].join("|");
}

function truncateReferenceText(text, max = 72) {
  const value = String(text || "").trim().replace(/\s+/g, " ");
  if (!value) return "";
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function buildAskReferenceLabel(reference) {
  const kind = String(reference?.kind || "").trim();
  const turn = reference?.turn ? `Turn ${reference.turn}` : "";
  const speaker = String(reference?.speaker || "").trim();
  const title = String(reference?.title || "").trim();
  const quote = truncateReferenceText(reference?.quote || reference?.summary || "");
  const parts = [];
  if (title) parts.push(title);
  if (turn) parts.push(turn);
  if (speaker) parts.push(speaker);
  if (!title && kind && kind !== "transcript") parts.push(kind);
  const prefix = parts.join(" / ");
  return prefix && quote ? `${prefix} / 「${quote}」` : prefix || quote || "参照";
}

function renderAskReferences() {
  if (!askReferenceBarEl || !askReferenceChipsEl) return;
  if (!currentAskReferences.length) {
    askReferenceBarEl.hidden = true;
    askReferenceChipsEl.innerHTML = "";
    return;
  }
  askReferenceBarEl.hidden = false;
  askReferenceChipsEl.innerHTML = currentAskReferences.map((reference) => `
    <div class="ask-reference-chip" data-ask-reference-key="${escapeHtml(reference.key)}">
      <span class="ask-reference-chip-copy">${escapeHtml(buildAskReferenceLabel(reference))}</span>
      <button type="button" class="ask-reference-remove" data-ask-reference-remove="${escapeHtml(reference.key)}" aria-label="Remove reference">×</button>
    </div>
  `).join("");
}

function addAskReference(reference) {
  const normalized = {
    kind: String(reference?.kind || "transcript"),
    title: String(reference?.title || ""),
    turn: Number(reference?.turn) || 0,
    speaker: String(reference?.speaker || "").trim().toUpperCase(),
    quote: String(reference?.quote || "").trim(),
    summary: String(reference?.summary || "").trim(),
  };
  normalized.key = askReferenceKey(normalized);
  if (!normalized.quote && !normalized.summary) return;
  if (currentAskReferences.some((item) => item.key === normalized.key)) return;
  currentAskReferences = [...currentAskReferences, normalized];
  renderAskReferences();
}

function removeAskReference(key) {
  currentAskReferences = currentAskReferences.filter((item) => item.key !== key);
  renderAskReferences();
}

function askPayloadReferences() {
  return currentAskReferences.map((reference) => ({
    kind: reference.kind,
    title: reference.title,
    turn: reference.turn || undefined,
    speaker: reference.speaker || undefined,
    quote: reference.quote || undefined,
    summary: reference.summary || undefined,
    normalized_text: reference.quote ? normalizeSearchText(reference.quote) : undefined,
    source_kind: reference.kind === "sentence" ? "transcript" : reference.kind,
  }));
}

function buildReferenceButtonMarkup(reference) {
  return "";
}

function referenceFromDataset(dataset = {}) {
  return {
    kind: dataset.referenceKind || "transcript",
    title: dataset.referenceTitle || "",
    turn: Number(dataset.referenceTurn) || 0,
    speaker: dataset.referenceSpeaker || "",
    quote: dataset.referenceQuote || "",
    summary: dataset.referenceSummary || "",
  };
}

function syncSaveButton() {
  saveButton.hidden = true;
  saveButton.disabled = true;
  saveButton.textContent = "Save Match";
}

function syncAskButton() {
  return;
}

function syncDetailLikeButton() {
  if (!detailLikeButton) return;
  if (!currentRecordId) {
    detailLikeButton.hidden = true;
    detailLikeButton.disabled = true;
    detailLikeButton.textContent = "Like (0)";
    delete detailLikeButton.dataset.likeRecordId;
    return;
  }
  const saved = historyRecordsCache.find((item) => item.id === currentRecordId) || currentLoadedRecord;
  const likes = Number(saved?.likes || 0);
  detailLikeButton.hidden = false;
  detailLikeButton.disabled = false;
  detailLikeButton.dataset.likeRecordId = currentRecordId;
  detailLikeButton.textContent = `Like (${likes})`;
}

function formatCreatedAt(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "";
  return date.toLocaleString("ja-JP", { hour12: false });
}

function buildBattleCardPlaceholderImage(topicLabel = "") {
  const title = String(topicLabel || "AIバトル").trim() || "AIバトル";
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fff1e7"/>
      <stop offset="55%" stop-color="#f1d3c2"/>
      <stop offset="100%" stop-color="#c24e36"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="675" fill="url(#bg)"/>
  <circle cx="1020" cy="118" r="180" fill="rgba(255,255,255,0.18)"/>
  <circle cx="120" cy="594" r="220" fill="rgba(24,52,74,0.12)"/>
  <text x="72" y="124" fill="#8d2f21" font-size="34" font-family="Arial, Helvetica, sans-serif" font-weight="700">AIバトル</text>
  <foreignObject x="72" y="176" width="1056" height="360">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial, Helvetica, sans-serif;color:#23150f;font-size:56px;line-height:1.16;font-weight:800;">${escapeHtml(title)}</div>
  </foreignObject>
</svg>
  `.trim();
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function buildHistoryItemMarkup(record) {
  const preview = normalizeSavedRecordForPreview(record);
  const winner = preview.judge_json?.winner?.side || "Draw";
  const verdict = preview.judge_json?.verdict_headline || "Saved match";
  const excerpt = preview.excerpt || preview.tease || verdict;
  const elapsed = formatElapsedSeconds(preview.elapsed_seconds);
  const sourceMode = formatRunModeMeta(preview.source_mode || "", preview.provider_statuses || {}).toLowerCase();
  const topicLabel = formatTopicDisplay(preview.topic, preview.keyword || "");
  const experienceMode = preview.experience_mode === "battle" ? "battle" : "debate";
  const experienceLabel = experienceMode === "battle" ? "AIバトル" : "討論";
  const winnerLabel = winner === "Draw" ? "保留" : winner;
  const battleImage = String(preview.source_image || "").trim() || buildBattleCardPlaceholderImage(topicLabel);
  const metaParts = [
    formatCreatedAt(preview.created_at),
    winner,
    `${preview.turn_count} turns`,
  ];
  if (elapsed) metaParts.push(elapsed);
  if (sourceMode) metaParts.push(sourceMode);
  if (experienceMode === "battle") {
    return `
      <div class="history-item history-item-battle">
        <button type="button" class="history-item-main history-item-main-battle" data-record-id="${escapeHtml(preview.id)}">
          <div class="history-battle-image-wrap">
            <img class="history-battle-image" src="${escapeHtml(battleImage)}" alt="${escapeHtml(topicLabel)}" loading="lazy" />
            <span class="history-mode-badge history-mode-badge-${escapeHtml(experienceMode)}">${escapeHtml(experienceLabel)}</span>
          </div>
          <div class="history-battle-copy">
            <div class="history-battle-issue">${escapeHtml(topicLabel)}</div>
            <div class="history-battle-winner">勝者: ${escapeHtml(winnerLabel)}</div>
          </div>
        </button>
      </div>
    `;
  }
  return `
    <div class="history-item">
      <button type="button" class="history-item-main" data-record-id="${escapeHtml(preview.id)}">
      <div class="history-topic-row">
        <div class="history-topic">${escapeHtml(topicLabel)}</div>
        <span class="history-mode-badge history-mode-badge-${escapeHtml(experienceMode)}">${escapeHtml(experienceLabel)}</span>
      </div>
      <div class="history-meta">${escapeHtml(metaParts.join(" / "))}</div>
      <div class="history-submeta">${escapeHtml(`${preview.fighter_a_model} vs ${preview.fighter_b_model} / ${preview.judge_model}`)}</div>
      <div class="history-verdict">${escapeHtml(excerpt)}</div>
      </button>
      <div class="history-actions">
        <span class="history-stats">${escapeHtml(`Views ${preview.views || 0} · Likes ${preview.likes || 0}`)}</span>
      </div>
    </div>
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
  const records = historySortMode === "likes"
    ? [...historyRecordsCache].sort((a, b) => (Number(b.likes || 0) - Number(a.likes || 0)) || (Number(b.views || 0) - Number(a.views || 0)) || String(b.created_at).localeCompare(String(a.created_at)))
    : [...historyRecordsCache].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
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
  const normalizedCount = Number.isFinite(Number(count)) ? Number(count) : canonicalHistoryCount();
  archiveButton.textContent = `⚙️`;
  archiveButton.setAttribute("aria-label", `Open archive (${normalizedCount} matches)`);
  archiveCountEl.textContent = `${normalizedCount} match${normalizedCount === 1 ? "" : "es"}`;
}

function filteredArchiveRecords(records, query, modeFilter) {
  const normalizedQuery = normalizeSearchText(query);
  return records.filter((record) => {
    const matchesMode = modeFilter === "all" || recordExperienceMode(record) === modeFilter;
    if (!matchesMode) return false;
    if (!normalizedQuery) return true;
    return normalizeSearchText(record.topic).includes(normalizedQuery);
  });
}

function renderArchiveList() {
  const curated = filteredArchiveRecords(
    curatedViewerRecords.map(normalizeSavedRecordForPreview),
    archiveSearchEl.value,
    archiveModeFilter,
  );
  const records = [...historyRecordsCache].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  const filtered = filteredArchiveRecords(records, archiveSearchEl.value, archiveModeFilter);
  updateArchiveButton(records.length);
  archiveRecentCountEl.textContent = `${curated.length}`;
  archiveSavedCountEl.textContent = `${filtered.length}`;

  if (historyFetchInFlight && !historyRecordsHydrated) {
    archiveRecentListEl.classList.add("empty");
    archiveRecentListEl.innerHTML = '<div class="empty-state">履歴を読み込み中です。</div>';
    archiveListEl.classList.add("empty");
    archiveListEl.innerHTML = '<div class="empty-state">履歴を読み込み中です。</div>';
    return;
  }

  if (!curated.length) {
    archiveRecentListEl.classList.add("empty");
    archiveRecentListEl.innerHTML = '<div class="empty-state">公開用の試合はまだありません。</div>';
  } else {
    archiveRecentListEl.classList.remove("empty");
    archiveRecentListEl.innerHTML = curated.map(buildHistoryItemMarkup).join("");
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
  historyShellEl.hidden = true;
  toggleArchive(open);
}

function toggleArchive(open) {
  if (open) {
    toggleAskPanel(false);
  }
  archiveShellEl.hidden = !open;
  if (open) {
    archiveModeFilter = currentArchiveModeFilter();
    syncArchiveModeFilterButtons();
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
      ${Array.isArray(message.references) && message.references.length ? `<div class="ask-reference-chips">${message.references.map((reference) => `<span class="ask-reference-chip"><span class="ask-reference-chip-copy">${escapeHtml(buildAskReferenceLabel(reference))}</span></span>`).join("")}</div>` : ""}
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
    renderAskReferences();
    if (askRetryButton) askRetryButton.hidden = true;
    askInputEl.focus();
    if (currentResult && !analysisHidden) {
      renderSummary(currentResult.debate?.summary || {});
    }
  } else {
    setAskStatus("");
    if (askRetryButton) askRetryButton.hidden = true;
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
  debugPipelinePanelEl.hidden = true;
  if (debugConstraintReportEl) debugConstraintReportEl.textContent = "not available";
  if (debugJudgePass1El) debugJudgePass1El.textContent = "not available";
  if (debugJudgePass2El) debugJudgePass2El.textContent = "not available";
  if (debugStoryAlignReportEl) debugStoryAlignReportEl.textContent = "not available";
  return;
}

function buildResultFromRecord(record) {
  const preview = normalizeSavedRecordForPreview(record);
  return {
    ok: true,
    mode: preview.source_mode || "mock",
    output_meta: preview.output_meta || "",
    run_id: preview.run_id || "",
    topic_hash: preview.topic_hash || "",
    provider_statuses: Object.keys(preview.provider_statuses || {}).length
      ? preview.provider_statuses
      : {
          openai: { mode: preview.fighter_a_provider === "openai" || preview.fighter_b_provider === "openai" ? "live" : "mock", reason: "" },
          anthropic: { mode: preview.fighter_a_provider === "anthropic" || preview.fighter_b_provider === "anthropic" ? "live" : "mock", reason: "" },
          gemini: { mode: preview.fighter_a_provider === "gemini" || preview.fighter_b_provider === "gemini" ? "live" : "mock", reason: "" },
          judge: { mode: preview.judge_provider === "gemini" ? "live" : "mock", reason: "" },
        },
    debate: {
      topic: preview.topic,
      turn_count: preview.turn_count,
      run_id: preview.run_id || "",
      topic_hash: preview.topic_hash || "",
      participants: {
        a: preview.fighter_a_model,
        b: preview.fighter_b_model,
        judge: preview.judge_model,
      },
      turns: preview.display_turns,
      raw_turns: preview.raw_turns,
      display_turns: preview.display_turns,
      summary: preview.judge_json,
    },
    localized_views: preview.localized_views || {},
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
  const experienceMode = preview.experience_mode === "battle" ? "battle" : "debate";
  const resolvedBattleLang = experienceMode === "battle"
    ? resolveRequestedBattleLang(queryParams, { mode: experienceMode })
    : "ja";
  setBattleLanguage(resolvedBattleLang, { refresh: false });
  applyExperienceMode(experienceMode);
  currentLoadedRecord = preview;
  currentRecordId = saved ? preview.id : null;
  currentPayload = {
    topic: preview.topic,
    side_a: preview.stance_a,
    side_b: preview.stance_b,
    keyword: normalizeKeyword(preview.keyword || ""),
    turn_count: preview.turn_count,
    mode: preview.mode,
    fighter_a_provider: preview.fighter_a_provider,
    fighter_b_provider: preview.fighter_b_provider,
    source_type: preview.source_type || "",
    source_url: preview.source_url || "",
    source_image: preview.source_image || "",
    source_summary: preview.source_summary || "",
    battle_lang: resolvedBattleLang,
  };
  currentBattleSource = preview.source_url ? {
    source_type: preview.source_type || "x_post",
    source_url: preview.source_url || "",
    source_image: preview.source_image || "",
    source_summary: preview.source_summary || "",
    issue: preview.topic || "",
    lang: resolvedBattleLang,
  } : null;
  currentFighters = {
    a: preview.fighter_a_provider,
    b: preview.fighter_b_provider,
    judge: "gemini",
  };
  document.querySelector("#topic").value = preview.topic;
  document.querySelector("#side-a").value = preview.stance_a;
  document.querySelector("#side-b").value = preview.stance_b;
  if (keywordInput) keywordInput.value = normalizeKeyword(preview.keyword || "");
  setTurnCountSelection(preview.turn_count);
  document.querySelector(`input[name="debateMode"][value="${preview.mode}"]`)?.click();
  fighterAProviderInput.value = preview.fighter_a_provider;
  fighterBProviderInput.value = preview.fighter_b_provider;
  renderBattleSourceCard();
  currentResult = buildResultFromRecord(preview);
  currentConstraintReport = currentResult.debate?.summary?.debug_constraint_report || null;
  currentJudgePass1 = currentResult.debate?.summary?.debug_pass1 || null;
  currentJudgePass2 = currentResult.debate?.summary?.debug_pass2 || null;
  currentStoryAlignReport = currentResult.debate?.summary?.debug_story_align_report || null;
  setReadingMode(true);
  setRevealState(false);
  resetAskThreadForCurrentMatch();
  refreshOutput();
  syncDetailLikeButton();
  renderDebugPipeline();
  syncViewerReadOnlyControls();
  renderViewerList();
  syncShareButton();
  setStatus("ok", "Structure revealed");
  toggleHistory(false);
  toggleArchive(false);
  if (experienceMode === "battle" && resolvedBattleLang === "en") {
    void ensureLocalizedViewForCurrentBattle().catch(() => {});
  }
}

async function sendAskQuestion(question) {
  const trimmed = String(question || "").trim();
  const record = getCurrentBattleRecord();
  const references = askPayloadReferences();
  if ((!trimmed && !references.length) || !record) return;
  resetAskThreadForCurrentMatch();
  currentAskMessages.push({ role: "user", text: trimmed || "この参照について見てください。", references });
  renderAskThread();
  askSendButton.disabled = true;
  if (askRetryButton) askRetryButton.hidden = true;
  setAskStatus("Gemini に確認中…");
  try {
    const response = await fetch(endpointUrl("/api/ask_match"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: trimmed,
        references,
        summary: record?.judge_json || {},
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
    askInputEl.value = "";
  } catch (error) {
    currentAskMessages.push({ role: "assistant", text: `Geminiに接続できませんでした。キー設定を確認して再送してください。 (${error.message || "unknown"})` });
    renderAskThread();
    if (askRetryButton) askRetryButton.hidden = false;
  } finally {
    askSendButton.disabled = false;
    setAskStatus("");
  }
}

async function loadSavedMatch(recordId) {
  try {
    await incrementHistoryMetric(recordId, "view");
  } catch {}
  const record = await fetchHistoryRecordById(recordId);
  if (!record) return;
  loadRecordIntoView(record, { saved: true });
}

async function saveCurrentMatch() {
  if (!currentResult || analysisHidden || !currentPayload) return;
  const record = buildBattleRecord(currentResult, currentPayload);
  const saved = await saveHistoryRecordToServer(record);
  sendBattleMetric(record.run_id || saved.run_id || saved.session_id || currentBattleShareId(), "save");
  currentRecordId = saved.id;
  currentLoadedRecord = saved;
  renderHistoryList();
  renderArchiveList();
  syncSaveButton();
  syncAskButton();
  syncDetailLikeButton();
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
  document.querySelectorAll(".jump-highlight, .mmar-hit-flash").forEach((node) => {
    node.classList.remove("jump-highlight", "mmar-hit-flash");
  });
  activeSelectedTargets.forEach((node) => node.classList.remove("mmar-hit-selected"));
  activeSelectedTargets = [];
}

function pulseJumpTarget(targets) {
  const nodes = (Array.isArray(targets) ? targets : [targets]).filter(Boolean);
  if (!nodes.length) return;
  clearJumpHighlight();
  activeSelectedTargets = nodes;
  nodes.forEach((node) => node.classList.add("jump-highlight", "mmar-hit-flash", "mmar-hit-selected"));
  nodes[0].scrollIntoView({ behavior: "smooth", block: "center" });
  activeJumpTimer = window.setTimeout(() => {
    nodes.forEach((node) => node.classList.remove("jump-highlight", "mmar-hit-flash"));
    activeJumpTimer = null;
  }, 1800);
}

function resolveTurnCard(turnNumber) {
  return turnNumber ? document.querySelector(`#turn-${turnNumber}`) : null;
}

function resolveSpeakerBlock(turnNumber, speaker) {
  if (turnNumber && speaker && speaker !== "A/B") {
    return document.querySelector(`[data-turn="${turnNumber}"][data-speaker="${speaker}"]`);
  }
  if (speaker && speaker !== "A/B") {
    const blocks = [...document.querySelectorAll(`[data-speaker="${speaker}"]`)];
    return blocks[blocks.length - 1] || null;
  }
  return null;
}

function resolveSentenceHighlight(block, quote, fallbackText = "") {
  if (!block) return null;
  const sentences = [...block.querySelectorAll(".turn-copy-sentence")];
  if (!sentences.length) return null;
  const exact = normalizeSearchText(quote);
  const loose = normalizeSearchText(fallbackText);
  if (exact) {
    const direct = sentences.find((node) => {
      const normalized = node.dataset.normalized || normalizeSearchText(node.textContent);
      return normalized === exact || normalized.includes(exact) || exact.includes(normalized);
    });
    if (direct) return direct;
  }
  if (loose) {
    const hinted = sentences.find((node) => {
      const normalized = node.dataset.normalized || normalizeSearchText(node.textContent);
      return normalized.includes(loose) || loose.includes(normalized);
    });
    if (hinted) return hinted;
  }
  return null;
}

function jumpToFatalPhrase(summary) {
  const fatal = normalizeFatalPhrase(summary);
  const turnNumber = extractTurnNumber(summary?.fatal_phrase) || Number(fatal.turn) || null;
  const speaker = String(summary?.fatal_phrase?.speaker || fatal.speaker || "").trim().toUpperCase();
  const block = resolveSpeakerBlock(turnNumber, speaker);
  if (block) {
    const exactSentence = resolveSentenceHighlight(block, summary?.fatal_phrase?.quote || fatal.quote, summary?.fatal_phrase?.reason || fatal.why);
    if (exactSentence) {
      pulseJumpTarget([block, exactSentence]);
      return;
    }
    pulseJumpTarget(block);
    return;
  }
  const fallbackTurn = resolveTurnCard(turnNumber);
  if (fallbackTurn) pulseJumpTarget(fallbackTurn);
}

function jumpToTimelineQuote(item) {
  const turnNumber = extractTurnNumber(item?.turn);
  const speaker = String(item?.speaker || "").trim().toUpperCase();
  const block = resolveSpeakerBlock(turnNumber, speaker);
  if (block) {
    const exactSentence = resolveSentenceHighlight(block, item?.quote || "", item?.reason || "");
    pulseJumpTarget(exactSentence ? [block, exactSentence] : block);
    return;
  }
  const fallbackTurn = resolveTurnCard(turnNumber);
  if (fallbackTurn) pulseJumpTarget(fallbackTurn);
}

function jumpToTurningPoint(summary) {
  const turning = normalizeTurningPoint(summary);
  const turnNumber = extractTurnNumber(summary?.turning_point) || extractTurnNumber(turning.turn);
  const target = resolveTurnCard(turnNumber);
  if (!target) return;
  const likelySpeaker = String(summary?.fatal_phrase?.speaker || "").trim().toUpperCase();
  const block = resolveSpeakerBlock(turnNumber, likelySpeaker);
  const sentence = resolveSentenceHighlight(block, turning.quote_excerpt || "", turning.summary || summary?.turning_point);
  pulseJumpTarget(sentence ? [target, sentence] : target);
}

function jumpToWeakSpot(summary) {
  const weakSpot = normalizeWeakSpot(summary);
  const turnNumber = extractTurnNumber(weakSpot?.turn);
  const speaker = String(weakSpot?.speaker || "").trim().toUpperCase();
  const block = resolveSpeakerBlock(turnNumber, speaker);
  if (block) {
    const sentence = resolveSentenceHighlight(block, weakSpot?.quote_excerpt || "", weakSpot?.why_one_sentence || "");
    pulseJumpTarget(sentence ? [block, sentence] : block);
    return;
  }
  const fallback = resolveTurnCard(turnNumber) || [...document.querySelectorAll(".speaker-block")].pop();
  if (fallback) pulseJumpTarget(fallback);
}

function jumpToGeminiQuote(summary) {
  const geminiQuote = normalizeGeminiQuote(summary);
  const turnNumber = Number(geminiQuote?.evidence_turn || geminiQuote?.source_turn) || 0;
  const speaker = String(geminiQuote?.evidence_side || geminiQuote?.source_side || "").trim().toUpperCase();
  const block = resolveSpeakerBlock(turnNumber, speaker);
  if (block) {
    const sentence = resolveSentenceHighlight(block, geminiQuote?.evidence_quote || geminiQuote?.quote || "", geminiQuote?.framing_text || geminiQuote?.text || "");
    pulseJumpTarget(sentence ? [block, sentence] : block);
    return;
  }
  const fallback = resolveTurnCard(turnNumber);
  if (fallback) pulseJumpTarget(fallback);
}

function detectTurnMarkers(summary) {
  return {
    fatal: extractTurnNumber(summary?.fatal_phrase),
    turning: extractTurnNumber(summary?.turning_point),
    contradiction: extractTurnNumber(summary?.contradiction_exposed),
  };
}

function computeAxisTagVisibility(cards) {
  const priority = {
    fatal: 5,
    weak: 4,
    turning: 3,
    why: 2,
    winner: 1,
  };
  const grouped = new Map();
  cards.forEach((card) => {
    const tag = String(card?.axisTag || "").trim();
    if (!tag) return;
    const key = normalizeSearchText(tag);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(card);
  });
  const visibility = {};
  grouped.forEach((items) => {
    items.sort((a, b) => (priority[b.key] || 0) - (priority[a.key] || 0));
    items.forEach((item, index) => {
      visibility[item.key] = index === 0 ? "primary" : "hidden";
    });
  });
  cards.forEach((card) => {
    if (!visibility[card.key]) visibility[card.key] = card.axisTag ? "primary" : "hidden";
  });
  return visibility;
}

function apiBase() {
  const raw = apiBaseInput.value.trim().replace(/\/+$/, "");
  return raw || window.location.origin;
}

function endpointUrl(path) {
  return `${apiBase()}${path}`;
}

function renderSummary(summary) {
  ensureExpansionIntro();
  ensureAnalysisPanel();
  ensureGeminiQuote();
  ensureVerdictStrip();
  syncMobileAnalysisPanel();
  const localized = currentLocalizedBattleView();
  const uiCopy = battleSummaryCopy();
  const winner = normalizeWinner(summary);
  const fatal = normalizeFatalPhrase(summary);
  const firstCrack = normalizeFirstCrack(summary);
  const turning = normalizeTurningPoint(summary);
  const clincher = normalizeClincher(summary);
  const weakSpot = normalizeWeakSpot(summary);
  const turnCount = Number(currentResult?.debate?.turn_count || currentPayload?.turn_count || selectedTurnCount());
  const showClincher = turnCount >= 5 && Boolean(clincher.quote);
  const confidence = summary?.confidence || "Medium";
  const why = localized?.summary?.reason_one_liner || summary?.reason_one_liner || winner.reason;
  const topic = currentResult?.debate?.topic || "";
  const battleIssue = currentBattleIssue() || topic;
  const battleLabels = battleCopy();
  const headline = localized?.summary?.verdict_headline || (isEnglishBattleView() ? composeEnglishVerdictHeadline(topic, winner) : composeVerdictHeadline(topic, winner));
  const subline = localized?.summary?.verdict_subline || (isEnglishBattleView() ? composeEnglishVerdictSubline(topic, winner, why) : composeVerdictSubline(topic, winner, why));
  const momentum = normalizeMomentum(summary, winner, confidence);
  const flipCondition = localized?.summary?.flip_condition || (isEnglishBattleView()
    ? composeEnglishFlipCondition(winner, weakSpot, why)
    : composeFlipCondition(winner, weakSpot, why));
  const takeaway = normalizeGeminiTakeaway(summary, topic);
  const geminiQuote = normalizeGeminiQuote(summary);
  const displayWinnerReason = isEnglishBattleView() && looksLikeAdjacentEnglishDuplicate(localized?.summary?.winner?.reason || winner.reason, why)
    ? ""
    : (localized?.summary?.winner?.reason || winner.reason);
  const takeawayLines = dedupeEnglishSurfaceLines([
    takeaway.structural_explanation,
    takeaway.debate_dynamic,
  ].filter((line) => String(line || "").trim()));
  const takeawayQuote = isEnglishBattleView() && takeawayLines.some((line) => looksLikeAdjacentEnglishDuplicate(takeaway.quote, line))
    ? ""
    : String(takeaway.quote || "").trim();
  const geminiQuoteText = isEnglishBattleView() && (
    takeawayLines.some((line) => looksLikeAdjacentEnglishDuplicate(geminiQuote.framing_text || geminiQuote.text, line))
    || looksLikeAdjacentEnglishDuplicate(geminiQuote.framing_text || geminiQuote.text, takeawayQuote)
    || looksLikeAdjacentEnglishDuplicate(geminiQuote.framing_text || geminiQuote.text, why)
  )
    ? ""
    : String(geminiQuote.framing_text || geminiQuote.text || "").trim();
  const displayFatalQuote = localized?.summary?.fatal_phrase?.quote || fatal.quote;
  const displayFatalReason = localized?.summary?.fatal_phrase?.reason || fatal.why;
  const displayTurningSummary = localized?.summary?.turning_point?.summary || turning.summary;
  const displayWeakLabel = localized?.summary?.weak_spot?.label || weakSpot.label;
  const displayWeakQuote = localized?.summary?.weak_spot?.quote_excerpt || weakSpot.quote_excerpt;
  const displayFirstCrackQuote = localized?.summary?.first_crack?.quote || firstCrack.quote;
  const displayFirstCrackReason = localized?.summary?.first_crack?.reason || firstCrack.reason;
  const displayClincherQuote = localized?.summary?.clincher?.quote || clincher.quote;
  const displayClincherReason = localized?.summary?.clincher?.reason || clincher.reason;
  const safeBattleSourceUrl = sanitizeExternalUrl(currentBattleSource?.source_url, { xOnly: true });
  const battleSourceMarkup = isBattleMode() && currentBattleSourceSummary() && currentBattleSource?.source_url
    ? `
      <article class="summary-card summary-card-source">
        <div class="summary-label">${escapeHtml(battleLabels.sourceLabel)}</div>
        <div class="summary-kicker">${escapeHtml(uiCopy.sourceKicker)}</div>
        <div class="summary-value summary-source-copy">${escapeHtml(currentBattleSourceSummary())}</div>
        <div class="summary-subvalue">${safeBattleSourceUrl ? `<a class="summary-source-link" href="${escapeHtml(safeBattleSourceUrl)}" target="_blank" rel="noreferrer noopener">${escapeHtml(battleLabels.sourceLink)}</a>` : ""}</div>
      </article>
    `
    : "";
  const axisVisibility = computeAxisTagVisibility([
    { key: "winner", axisTag: summary?.winner_axis_tag || "" },
    { key: "why", axisTag: summary?.why_axis_tag || "" },
    { key: "fatal", axisTag: fatal.axis_tag || "" },
    { key: "turning", axisTag: turning.axis_tag || "" },
    { key: "weak", axisTag: weakSpot.axis_tag || "" },
  ]);
  if (currentStoryAlignReport) {
    currentStoryAlignReport.ui_normalization = {
      turning_point_source: turning._debug_source || "",
      fatal_phrase_source: fatal._debug_source || "",
      fatal_phrase_template_applied: Boolean(fatal._debug_template_applied),
    };
  }
  const keyDisagreements = normalizeDetailList(summary?.key_disagreement_top3);
  const unresolvedResidue = normalizeDetailList(summary?.unresolved_residue);
  const fullRationale = summary?.full_rationale || summary?.provisional_judgment || "";
  const askHint = shouldShowAskHint()
    ? uiCopy.askHint
    : "";
  destroyExpansionIntro();

  verdictStripEl.innerHTML = `
    <article class="verdict-strip-card">
      <div class="verdict-strip-main">${escapeHtml(headline)}</div>
      <div class="verdict-strip-meta">
        <span class="verdict-pill">${escapeHtml(uiCopy.winnerPill)} ${escapeHtml(formatBattleSideLabel(winner.side))}</span>
        <span class="verdict-pill">${escapeHtml(confidence)}</span>
      </div>
      <div class="verdict-strip-subline">${escapeHtml(subline)}</div>
      <div class="verdict-strip-why">${escapeHtml(why)}</div>
      <div class="verdict-strip-aux">
        <section class="momentum-card">
          <div class="momentum-head">
            <span>A ${escapeHtml(momentum.a)}</span>
            <span>${escapeHtml(uiCopy.momentumLabel)}</span>
            <span>B ${escapeHtml(momentum.b)}</span>
          </div>
          <div class="momentum-bar" aria-label="momentum bar">
            <div class="momentum-fill momentum-fill-a" style="width:${escapeHtml(momentum.a)}%"></div>
            <div class="momentum-fill momentum-fill-b" style="width:${escapeHtml(momentum.b)}%"></div>
          </div>
          <div class="momentum-note">${escapeHtml(uiCopy.momentumNote)}</div>
        </section>
        <section class="flip-card">
          <div class="summary-label">${escapeHtml(uiCopy.flipConditionLabel)}</div>
          <div class="flip-copy">${escapeHtml(flipCondition)}</div>
        </section>
      </div>
      ${PUBLIC_ASK_DISABLED ? "" : `
      <div class="verdict-strip-actions">
        <div class="ask-cta-copy">
          <div class="ask-cta-title">${escapeHtml(uiCopy.askTitle)}</div>
          ${askHint ? `<div class="ask-cta-hint">${escapeHtml(askHint)}</div>` : ""}
        </div>
        <button type="button" id="ask-match-button" class="secondary-button ask-cta-button">${escapeHtml(uiCopy.askButton)}</button>
      </div>`}
    </article>
  `;

  if (geminiQuoteText) {
    geminiQuoteEl.hidden = false;
    geminiQuoteEl.innerHTML = `
      <article class="gemini-quote-card summary-jump-card" data-jump-target="gemini-quote" title="${escapeHtml(geminiQuote.framing_reason || geminiQuote.pick_reason || "")}">
        <div class="summary-label">${escapeHtml(uiCopy.geminiQuoteLabel)}</div>
        <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(geminiQuote.role || "ai_framing"))}</div>
        ${geminiQuote.framing_role || geminiQuote.structural_role ? `<div class="summary-role">${escapeHtml(formatStructuralRoleLabel(geminiQuote.framing_role || geminiQuote.structural_role))}</div>` : ""}
        <div class="gemini-quote-copy">${escapeHtml(geminiQuoteText)}</div>
        ${geminiQuote.evidence_quote ? `<div class="gemini-quote-evidence">${escapeHtml(normalizeTakeawayQuote(geminiQuote.evidence_quote))}</div>` : ""}
        ${(geminiQuote.evidence_turn || geminiQuote.source_turn) ? `<div class="summary-subvalue">${escapeHtml(`Turn ${geminiQuote.evidence_turn || geminiQuote.source_turn} / ${geminiQuote.evidence_side || geminiQuote.source_side || "?"}`)}</div>` : ""}
      </article>
    `;
  } else {
    geminiQuoteEl.hidden = true;
    geminiQuoteEl.innerHTML = "";
  }

  verdictGridEl.classList.remove("empty");
  spotlightGridEl.classList.remove("empty");
  if (isBattleMode()) {
    verdictGridEl.innerHTML = `
      <article class="summary-card summary-card-issue">
        <div class="summary-label">${escapeHtml(battleLabels.issueLabel)}</div>
        <div class="summary-value summary-issue-copy">${escapeHtml(battleIssue)}</div>
      </article>
      ${battleSourceMarkup}
      <button type="button" class="summary-card tone-fatal summary-jump-card" data-jump-target="fatal">
        <div class="summary-label">${escapeHtml(battleLabels.decisiveLabel)}</div>
        <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(fatal.role || "decisive_lock"))}</div>
        <div class="summary-meta summary-turn-badge">${escapeHtml(`Turn ${fatal.turn} / ${fatal.speaker}`)}</div>
        <div class="summary-value summary-quote">${escapeHtml(displayFatalQuote)}</div>
        <div class="summary-subvalue summary-reason">${escapeHtml(displayFatalReason)}</div>
      </button>
      <button type="button" class="summary-card tone-turning summary-jump-card" data-jump-target="turning">
        <div class="summary-label">${escapeHtml(battleLabels.turningLabel)}</div>
        <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(turning.role || "frame_shift"))}</div>
        <div class="summary-meta summary-turn-badge">${escapeHtml(turning.turn)}</div>
        <div class="summary-value summary-turning-copy">${escapeHtml(displayTurningSummary)}</div>
      </button>
      <article class="summary-card summary-card-why">
        <div class="summary-label">${escapeHtml(battleLabels.summaryLabel)}</div>
        <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(summary?.why_role || "verdict_summary"))}</div>
        <div class="summary-value summary-why-copy">${escapeHtml(why)}</div>
      </article>
      <article class="summary-card gemini-takeaway-card">
        <div class="summary-label">${escapeHtml(uiCopy.geminiTakeawayLabel)}</div>
        ${takeawayLines.map((line) => `<div class="gemini-takeaway-line">${escapeHtml(line)}</div>`).join("")}
        ${takeawayQuote ? `<div class="gemini-takeaway-quote">${escapeHtml(takeawayQuote)}</div>` : ""}
      </article>
    `;
    spotlightGridEl.innerHTML = `
      <button type="button" class="summary-card tone-contradiction summary-jump-card" data-jump-target="weak">
        <div class="summary-label">${escapeHtml(battleLabels.weakLabel)}</div>
        <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(weakSpot.role || "failure_exposure"))}</div>
        <div class="summary-meta">${escapeHtml(`${formatBattleSideLabel(weakSpot.side)} / Turn ${weakSpot.turn} / ${weakSpot.speaker}`)}</div>
        <div class="summary-value summary-weak-label">${escapeHtml(displayWeakLabel)}</div>
        <div class="summary-subvalue summary-quote">${escapeHtml(normalizeTakeawayQuote(displayWeakQuote))}</div>
      </button>
      <button type="button" class="summary-card tone-first-crack summary-jump-card" data-jump-target="first-crack">
        <div class="summary-label">${escapeHtml(uiCopy.firstCrackLabel)}</div>
        <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(firstCrack.role || "first_crack"))}</div>
        <div class="summary-meta">${escapeHtml(firstCrack.turn ? `Turn ${firstCrack.turn} / ${firstCrack.speaker || "?"}` : "Turn ?")}</div>
        <div class="summary-value">${escapeHtml(displayFirstCrackQuote || uiCopy.firstCrackEmptyQuote)}</div>
        <div class="summary-subvalue">${escapeHtml(displayFirstCrackReason || uiCopy.firstCrackEmptyReason)}</div>
      </button>
      <article class="summary-card summary-card-confidence">
        <div class="summary-label">${escapeHtml(uiCopy.confidenceLabel)}</div>
        <div class="summary-value summary-emphasis">${escapeHtml(confidence)}</div>
      </article>
      ${showClincher ? `
        <button type="button" class="summary-card tone-clincher summary-jump-card" data-jump-target="clincher">
          <div class="summary-label">${escapeHtml(uiCopy.clincherLabel)}</div>
          <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(clincher.role || "clincher"))}</div>
          <div class="summary-meta">${escapeHtml(`Turn ${clincher.turn} / ${clincher.speaker || "?"}`)}</div>
          <div class="summary-value">${escapeHtml(displayClincherQuote)}</div>
          <div class="summary-subvalue">${escapeHtml(displayClincherReason)}</div>
        </button>
      ` : ""}
    `;
    detailPanelEl.innerHTML = `
      <details class="analysis-details" open>
        <summary>${escapeHtml(uiCopy.detailSummary)}</summary>
        <div class="analysis-detail-copy">${escapeHtml(localized?.summary?.full_rationale || fullRationale || uiCopy.detailEmpty)}</div>
      </details>
    `;
    return;
  }
  verdictGridEl.innerHTML = `
    <article class="summary-card summary-card-verdict tone-winner">
      <div class="summary-label">Winner</div>
      <div class="summary-kicker">Verdict</div>
      ${summary?.winner_axis_tag && axisVisibility.winner === "primary" ? `<div class="summary-axis-tag">${escapeHtml(formatAxisTagLabel(summary.winner_axis_tag))}</div>` : ""}
      <div class="summary-value summary-emphasis">${escapeHtml(winner.side)}</div>
      <div class="summary-subvalue summary-winner-reason">${escapeHtml(winner.reason)}</div>
    </article>
    <article class="summary-card summary-card-why">
      <div class="summary-label">Why in 1 sentence</div>
      <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(summary?.why_role || "verdict_summary"))}</div>
      ${summary?.why_axis_tag && axisVisibility.why === "primary" ? `<div class="summary-axis-tag">${escapeHtml(formatAxisTagLabel(summary.why_axis_tag))}</div>` : ""}
      <div class="summary-value summary-why-copy">${escapeHtml(why)}</div>
    </article>
    <article class="summary-card summary-card-confidence">
      <div class="summary-label">Confidence</div>
      <div class="summary-value summary-emphasis">${escapeHtml(confidence)}</div>
    </article>
  `;
  spotlightGridEl.innerHTML = `
    <button type="button" class="summary-card tone-first-crack summary-jump-card" data-jump-target="first-crack">
      <div class="summary-label">First Crack</div>
      <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(firstCrack.role || "first_crack"))}</div>
      <div class="summary-meta">${escapeHtml(firstCrack.turn ? `Turn ${firstCrack.turn} / ${firstCrack.speaker || "?"}` : "Turn ?")}</div>
      <div class="summary-value">${escapeHtml(firstCrack.quote || "まだ最初のヒビは特定されていない。")}</div>
      <div class="summary-subvalue">${escapeHtml(firstCrack.reason || "どこで最初の傷が入ったかを追う。")}</div>
    </button>
    <button type="button" class="summary-card tone-fatal summary-jump-card" data-jump-target="fatal">
      <div class="summary-label">Fatal Phrase</div>
      <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(fatal.role || "decisive_lock"))}</div>
      <div class="summary-meta summary-turn-badge">${escapeHtml(`Turn ${fatal.turn} / ${fatal.speaker}`)}</div>
      ${fatal.axis_tag && axisVisibility.fatal === "primary" ? `<div class="summary-axis-tag">${escapeHtml(formatAxisTagLabel(fatal.axis_tag))}</div>` : ""}
      ${fatal.structural_role ? `<div class="summary-role">${escapeHtml(formatStructuralRoleLabel(fatal.structural_role))}</div>` : ""}
      <div class="summary-value summary-quote">${escapeHtml(fatal.quote)}</div>
      <div class="summary-subvalue summary-reason" title="${escapeHtml(fatal.pick_reason || "")}">${escapeHtml(fatal.why)}</div>
    </button>
    <button type="button" class="summary-card tone-turning summary-jump-card" data-jump-target="turning">
      <div class="summary-label">Turning Point</div>
      <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(turning.role || "frame_shift"))}</div>
      <div class="summary-meta summary-turn-badge">${escapeHtml(turning.turn)}</div>
      ${turning.axis_tag && axisVisibility.turning === "primary" ? `<div class="summary-axis-tag">${escapeHtml(formatAxisTagLabel(turning.axis_tag))}</div>` : ""}
      <div class="summary-value summary-turning-copy">${escapeHtml(turning.summary)}</div>
    </button>
    <button type="button" class="summary-card tone-contradiction summary-jump-card" data-jump-target="weak">
      <div class="summary-label">Weak Spot / Foul</div>
      <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(weakSpot.role || "failure_exposure"))}</div>
      <div class="summary-meta">${escapeHtml(`${weakSpot.side} / Turn ${weakSpot.turn} / ${weakSpot.speaker} / ${weakSpot.label}`)}</div>
      ${weakSpot.axis_tag && axisVisibility.weak === "primary" ? `<div class="summary-axis-tag">${escapeHtml(formatAxisTagLabel(weakSpot.axis_tag))}</div>` : ""}
      <div class="summary-value summary-weak-label">${escapeHtml(weakSpot.label)}</div>
      <div class="summary-subvalue summary-quote">${escapeHtml(`「${weakSpot.quote_excerpt}」`)}</div>
      <div class="summary-subvalue summary-reason">${escapeHtml(`${weakSpot.why_one_sentence} / ${weakSpot.how_to_fix}`)}</div>
    </button>
    ${showClincher ? `
      <button type="button" class="summary-card tone-clincher summary-jump-card" data-jump-target="clincher">
        <div class="summary-label">Clincher</div>
        <div class="summary-kicker">${escapeHtml(formatCardRoleLabel(clincher.role || "clincher"))}</div>
        <div class="summary-meta">${escapeHtml(`Turn ${clincher.turn} / ${clincher.speaker || "?"}`)}</div>
        <div class="summary-value">${escapeHtml(clincher.quote)}</div>
        <div class="summary-subvalue">${escapeHtml(clincher.reason)}</div>
      </button>
    ` : ""}
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

function ensureExpansionIntro() {
  if (expansionIntroEl) return;
  expansionIntroEl = document.createElement("section");
  expansionIntroEl.id = "judge-expansion-intro";
  expansionIntroEl.className = "output-block judge-expansion-intro-block";
  if (verdictStripEl && verdictStripEl.parentNode === outputPanelEl) {
    outputPanelEl.insertBefore(expansionIntroEl, verdictStripEl);
    return;
  }
  outputPanelEl.appendChild(expansionIntroEl);
}

function destroyExpansionIntro() {
  if (expansionIntroEl) {
    expansionIntroEl.remove();
  }
  expansionIntroEl = null;
}

function ensureVerdictStrip() {
  if (verdictStripEl) return;
  verdictStripEl = document.createElement("section");
  verdictStripEl.id = "verdict-strip";
  verdictStripEl.className = "output-block verdict-strip-block";
  if (geminiQuoteEl && geminiQuoteEl.parentNode === outputPanelEl) {
    outputPanelEl.insertBefore(verdictStripEl, geminiQuoteEl.nextSibling);
    return;
  }
  if (analysisPanelEl && analysisPanelEl.parentNode === outputPanelEl) {
    outputPanelEl.insertBefore(verdictStripEl, analysisPanelEl.nextSibling);
    return;
  }
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
    outputPanelEl.insertBefore(geminiQuoteEl, analysisPanelEl.nextSibling);
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
  const uiCopy = battleSummaryCopy();
  analysisPanelEl = document.createElement("section");
  analysisPanelEl.id = "analysis-panel";
  analysisPanelEl.className = "output-block";
  analysisPanelEl.innerHTML = `
    <div class="section-title-row">
      <h3>${escapeHtml(uiCopy.judgeNotesTitle)}</h3>
      <div class="analysis-head-actions">
        <button type="button" id="analysis-toggle-button" class="chip-button analysis-toggle-button" hidden>${escapeHtml(uiCopy.analysisOpen)}</button>
        <span class="meta-chip">Judge</span>
      </div>
    </div>
    <div id="analysis-content">
      <div id="verdict-grid" class="verdict-grid empty"></div>
      <div id="spotlight-grid" class="summary-grid empty"></div>
      <div id="detail-panel" class="detail-panel"></div>
    </div>
  `;
  outputPanelEl.appendChild(analysisPanelEl);
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
  const uiCopy = battleSummaryCopy();
  if (!toggleButton || !content) return;
  if (isMobileLayout()) {
    toggleButton.hidden = false;
    analysisPanelEl.classList.toggle("mobile-analysis-collapsed", mobileAnalysisCollapsed);
    content.hidden = mobileAnalysisCollapsed;
    toggleButton.textContent = mobileAnalysisCollapsed ? uiCopy.analysisOpen : uiCopy.analysisClose;
    return;
  }
  toggleButton.hidden = true;
  analysisPanelEl.classList.remove("mobile-analysis-collapsed");
  content.hidden = false;
}

function renderTurns(turns, summary = {}, reveal = false) {
  const markers = reveal ? detectTurnMarkers(summary) : {};
  const uiCopy = battleSummaryCopy();
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
      const aText = String(turn.a || "");
      const bText = String(turn.b || "");
      const aMarkup = sentenceMarkup(aText, turn.turn, "A");
      const bMarkup = sentenceMarkup(bText, turn.turn, "B");
      const aRefButton = buildReferenceButtonMarkup({
        kind: "transcript",
        title: "Transcript",
        turn: turn.turn,
        speaker: "A",
        quote: aText,
        summary: `${stageLabel} / A`,
      });
      const bRefButton = buildReferenceButtonMarkup({
        kind: "transcript",
        title: "Transcript",
        turn: turn.turn,
        speaker: "B",
        quote: bText,
        summary: `${stageLabel} / B`,
      });
      const bodyMarkup = isRally
        ? `
          <div class="rally-stack">
            <section id="turn-${escapeHtml(turn.turn)}-a" class="speaker-block rally-block rally-first" data-turn="${escapeHtml(turn.turn)}" data-speaker="A">
              <div class="speaker-label">
                <span class="speaker-role">${escapeHtml(uiCopy.sideALabel)}</span>
                <span class="speaker-side">A</span>
              </div>
              <div class="turn-copy">${aMarkup}</div>
              ${aRefButton}
            </section>
            <section id="turn-${escapeHtml(turn.turn)}-b" class="speaker-block rally-block rally-second" data-turn="${escapeHtml(turn.turn)}" data-speaker="B">
              <div class="speaker-label">
                <span class="speaker-role">${escapeHtml(uiCopy.sideBLabel)}</span>
                <span class="speaker-side">B</span>
              </div>
              <div class="turn-copy">${bMarkup}</div>
              ${bRefButton}
            </section>
          </div>
        `
        : `
          <div class="turn-pair">
            <section id="turn-${escapeHtml(turn.turn)}-a" class="speaker-block" data-turn="${escapeHtml(turn.turn)}" data-speaker="A">
              <div class="speaker-label">A</div>
              <div class="turn-copy">${aMarkup}</div>
              ${aRefButton}
            </section>
            <section id="turn-${escapeHtml(turn.turn)}-b" class="speaker-block" data-turn="${escapeHtml(turn.turn)}" data-speaker="B">
              <div class="speaker-label">B</div>
              <div class="turn-copy">${bMarkup}</div>
              ${bRefButton}
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
  const parts = splitTranscriptSentences(value);
  const turnNumber = Number(arguments[1]) || 0;
  const speaker = String(arguments[2] || "").trim().toUpperCase();
  if (!parts.length) return escapeHtml(value);
  return parts.map((part, index) => {
    const normalized = normalizeSearchText(part);
    return `<span class="turn-copy-sentence-wrap" data-turn="${escapeHtml(turnNumber)}" data-speaker="${escapeHtml(speaker)}" data-sentence-index="${escapeHtml(index + 1)}"><span class="turn-copy-sentence" data-turn="${escapeHtml(turnNumber)}" data-speaker="${escapeHtml(speaker)}" data-sentence-index="${escapeHtml(index + 1)}" data-normalized="${escapeHtml(normalized)}" title="${escapeHtml(part)}">${escapeHtml(part)}</span>${buildReferenceButtonMarkup({
      kind: "sentence",
      title: "Transcript",
      turn: turnNumber,
      speaker,
      quote: part,
      summary: `Sentence ${index + 1}`,
      tag: "span",
      className: "sentence-reference-action",
      label: "質問に追加",
    })}</span>`;
  }).join("");
}

function splitTranscriptSentences(text) {
  const raw = String(text || "").replace(/\s+/g, " ").trim();
  if (!raw) return [];
  const chunks = raw
    .split(/(?<=[。！？!?])|(?<=\n)/)
    .map((part) => part.trim())
    .filter(Boolean);
  const merged = [];
  for (const chunk of chunks) {
    if (!merged.length) {
      merged.push(chunk);
      continue;
    }
    if (chunk.length <= 6 || /^[。！？!?]+$/.test(chunk)) {
      merged[merged.length - 1] += chunk;
      continue;
    }
    merged.push(chunk);
  }
  return merged;
}

function describePhase(turnNumber, stageLabel, totalTurns) {
  const uiCopy = battleSummaryCopy();
  if (turnNumber === 1) return { phase: "Turn 1", stage: uiCopy.turnOneStage };
  if (turnNumber === 2) return { phase: "Turn 2", stage: uiCopy.turnTwoStage };
  if (turnNumber === 3) return { phase: "Turn 3", stage: uiCopy.turnThreeStage };
  if (turnNumber === totalTurns) return { phase: `Turn ${turnNumber}`, stage: uiCopy.finalStage };
  return { phase: `Turn ${turnNumber}`, stage: uiCopy.continueStage };
}

function refreshOutput() {
  if (!currentResult) return;
  const debate = currentResult.debate || {};
  const turns = getDisplayTurns(debate);
  const displaySummary = summaryForDisplay(debate.summary || {});
  const mode = currentResult.mode || "unknown";
  const providerStatuses = providerStatusesForDisplay(currentResult.provider_statuses || {}, displaySummary);
  topicDisplayEl.textContent = formatTopicDisplay(
    isBattleMode() ? currentBattleIssue() : (debate.topic || currentPayload?.topic || ""),
    currentPayload?.keyword || currentLoadedRecord?.keyword || "",
  );
  outputMetaEl.textContent = buildOutputMeta(
    providerStatuses,
    turns.length,
    mode,
    currentLoadedRecord ? currentResult.output_meta || "" : "",
    { preferSaved: Boolean(currentLoadedRecord) && !hasCompletedJudgePipeline(debate.summary || {}) },
  );
  outputMetaEl.hidden = false;
  outputMetaEl.style.display = "";
  renderRuntimeFingerprint();
  renderResultHeroMedia();
  renderTurns(turns, displaySummary, !analysisHidden);
  syncDetailLikeButton();

  if (analysisHidden) {
    renderPublicSummary(displaySummary);
    judgeButton.hidden = false;
    judgeButton.disabled = false;
    setHint("");
    return;
  }

  clearPublicSummary();
  judgeButton.hidden = false;
  judgeButton.disabled = true;
  renderSummary(displaySummary);
  setHint(buildAbnormalHint(providerStatuses));
}

function renderResult(result) {
  currentResult = result;
  if (currentResult?.debate?.summary && !currentResult.debate.raw_summary) {
    currentResult.debate.raw_summary = JSON.parse(JSON.stringify(currentResult.debate.summary));
  }
  currentConstraintReport = currentResult?.debate?.summary?.debug_constraint_report || null;
  currentJudgePass1 = currentResult?.debate?.summary?.debug_pass1 || null;
  currentJudgePass2 = currentResult?.debate?.summary?.debug_pass2 || null;
  currentStoryAlignReport = currentResult?.debate?.summary?.debug_story_align_report || null;
  currentRecordId = null;
  currentLoadedRecord = null;
  resetAskThreadForCurrentMatch();
  setRevealState(true);
  setReadingMode(true);
  renderRuntimeFingerprint();
  refreshOutput();
  renderDebugPipeline();
  syncSaveButton();
  syncAskButton();
  syncViewerReadOnlyControls();
  syncShareButton();
}

function exitReaderModeToEdit() {
  if (shouldUsePublicFixedDemo()) {
    startNextMatch();
    return;
  }
  setReadingMode(false);
  document.querySelector("#topic")?.focus();
}

function resetJudgeState() {
  judgeButton.hidden = true;
  judgeButton.disabled = true;
}

function startNextMatch() {
  clearCurrentResultView();
  resetJudgeState();
  currentPayload = null;
  currentBattleSource = null;
  currentLocalizedViewFetchToken += 1;
  clearBattleXSourceError();
  const topicInput = document.querySelector("#topic");
  const sideAInput = document.querySelector("#side-a");
  const sideBInput = document.querySelector("#side-b");
  if (topicInput) topicInput.value = "";
  if (sideAInput) sideAInput.value = "";
  if (sideBInput) sideBInput.value = "";
  if (keywordInput) keywordInput.value = "";
  if (battleXUrlInput) battleXUrlInput.value = "";
  renderBattleSourceCard();
  setReadingMode(false);
  setStatus("idle", "Ready");
  setHint("");
  document.querySelector("#topic")?.focus();
}

function collectPayload() {
  const topic = document.querySelector("#topic").value.trim();
  const sideA = document.querySelector("#side-a").value.trim();
  const sideB = document.querySelector("#side-b").value.trim();
  const keyword = normalizeKeyword(keywordInput?.value || "");
  const turnCount = selectedTurnCount();
  const mode = document.querySelector('input[name="debateMode"]:checked')?.value || "casual";

  return {
    topic,
    side_a: sideA,
    side_b: sideB,
    experience_mode: currentExperienceMode,
    keyword,
    turn_count: turnCount,
    mode,
    fighter_a_provider: fighterAProviderInput?.value || "openai",
    fighter_b_provider: fighterBProviderInput?.value || "openai",
    api_keys: {
      openai: document.querySelector("#openai-key").value.trim(),
      anthropic: document.querySelector("#anthropic-key").value.trim(),
      gemini: document.querySelector("#gemini-key").value.trim(),
    },
    source_type: isBattleMode() ? currentBattleSource?.source_type || "" : "",
    source_url: isBattleMode() ? currentBattleSource?.source_url || "" : "",
    source_image: isBattleMode() ? currentBattleSource?.source_image || "" : "",
    source_summary: isBattleMode() ? currentBattleSource?.source_summary || "" : "",
    battle_lang: isBattleMode() ? currentBattleLang : "ja",
  };
}

async function checkApiHealth() {
  const healthUrl = endpointUrl("/api/health");
  try {
    const response = await fetch(healthUrl, { method: "GET" });
    if (response.status === 404) {
      currentHealthInfo = { status: "error", data: null, message: "health unavailable" };
      renderRuntimeFingerprint();
      if (!analysisHidden) setHint(publicFacingOperationalHint("API health unavailable", ""));
      return;
    }
    if (!response.ok) {
      currentHealthInfo = { status: "error", data: null, message: "health unavailable" };
      renderRuntimeFingerprint();
      if (!analysisHidden) setHint(publicFacingOperationalHint("API unavailable", ""));
      return;
    }
    const data = await response.json();
    currentHealthInfo = { status: "ok", data, message: "" };
    renderRuntimeFingerprint();
    syncBattleAccessControls();
    return data;
  } catch {
    currentHealthInfo = { status: "error", data: null, message: "health unavailable" };
    renderRuntimeFingerprint();
    syncBattleAccessControls();
    if (!analysisHidden) setHint(publicFacingOperationalHint("API unavailable", ""));
  }
}

async function ensureApiHealthBeforeRun() {
  const healthUrl = endpointUrl("/api/health");
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 1000);
  try {
    const response = await fetch(healthUrl, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error("Server unavailable (port 8912)");
    }
    const data = await response.json();
    currentHealthInfo = { status: "ok", data, message: "" };
    renderRuntimeFingerprint();
    return data;
  } catch (error) {
    currentHealthInfo = { status: "error", data: null, message: "health unavailable" };
    renderRuntimeFingerprint();
    if (error?.name === "AbortError") {
      throw new Error(publicFacingOperationalHint("Backend not responding", "接続に失敗しました"));
    }
    throw new Error(publicFacingOperationalHint("Server unavailable (port 8912)", "接続に失敗しました"));
  } finally {
    window.clearTimeout(timeoutId);
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

turnCountButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setTurnCountSelection(button.dataset.turnCountOption || "3");
  });
});
setTurnCountSelection(selectedTurnCount());
applyPublicFixedDemoDefaults();
applyPublicInteractiveDefaults();
clearPublicSummary();
void loadSharedBattleFromPath();

keywordInput?.addEventListener("blur", () => {
  keywordInput.value = normalizeKeyword(keywordInput.value);
});

swapSidesButton?.addEventListener("click", () => {
  const sideAInput = document.querySelector("#side-a");
  const sideBInput = document.querySelector("#side-b");
  if (!sideAInput || !sideBInput) return;
  const nextA = sideBInput.value;
  sideBInput.value = sideAInput.value;
  sideAInput.value = nextA;
});

readerBackButton?.addEventListener("click", () => {
  exitReaderModeToEdit();
});

readerNextButton?.addEventListener("click", () => {
  startNextMatch();
});

function explainHttpError(endpointLabel, status) {
  if (status === 404) return `${endpointLabel} endpoint unavailable`;
  if (status === 400) return "request rejected";
  if (status >= 500) return "API error";
  return `HTTP ${status}`;
}

function normalizeApiError(endpointLabel, status, data) {
  const raw = String(data?.error || "").trim();
  const reason = String(data?.reason || "").trim();
  const normalized = raw.toLowerCase();
  const normalizedReason = reason.toLowerCase();
  const publicReason = (() => {
    const code = normalizedReason || normalized;
    if (code === "invalid_x_url") {
      return currentBattleLang === "en" ? "Only X post URLs are supported." : "Xの投稿URLだけ使えます";
    }
    if (code === "missing_xai_key") {
      return currentBattleLang === "en" ? "X import is not configured on this preview." : "この preview では X import が未設定です";
    }
    if (code === "x_fetch_failed") {
      return currentBattleLang === "en" ? "Could not fetch that X post. Try another post URL." : "そのX投稿を取得できませんでした。別の投稿URLで試してください";
    }
    if (code === "provider_401") {
      return currentBattleLang === "en" ? "The X provider key was rejected." : "X provider のキーが拒否されました";
    }
    if (code === "provider_403") {
      return currentBattleLang === "en" ? "The X provider rejected this request." : "X provider にリクエストを拒否されました";
    }
    if (code === "provider_429") {
      return currentBattleLang === "en" ? "The X provider is rate-limiting right now." : "X provider 側でレート制限されています";
    }
    if (code === "provider_5xx") {
      return currentBattleLang === "en" ? "The X provider is temporarily unavailable." : "X provider が一時的に不安定です";
    }
    if (code === "timeout") {
      return currentBattleLang === "en" ? "The X provider took too long to respond." : "X provider の応答がタイムアウトしました";
    }
    if (code === "parse_failed") {
      return currentBattleLang === "en" ? "The post was fetched but could not be turned into a battle seed." : "投稿は読めましたが battle seed に変換できませんでした";
    }
    if (code === "empty_extraction") {
      return currentBattleLang === "en" ? "The post did not return enough material to build a battle." : "battle 化に十分な抽出結果が返りませんでした";
    }
    return "";
  })();
  const debugReasonSuffix = publicFacingOperationalHint(
    reason ? ` [reason=${reason}]` : "",
    "",
  );
  if (normalized === "invalid_x_url") {
    return currentBattleLang === "en" ? "Only X post URLs are supported." : "Xの投稿URLだけ使えます";
  }
  if (normalized === "battle_source_unavailable" || normalized === "internal_error") {
    const fallback = currentBattleLang === "en" ? "Could not read that post. Try another X post URL." : "読み込みに失敗しました。別のX投稿URLで試してください";
    const message = publicReason || fallback;
    return `${message}${debugReasonSuffix}`;
  }
  if (publicReason) return `${publicReason}${debugReasonSuffix}`;
  if (normalized === "invalid_fighter_provider") return "The selected model combination is not available.";
  if (normalized === "invalid_judge_provider") return "The selected judge model is not available.";
  if (normalized === "provider_error") return "The selected model could not be reached.";
  if (normalized === "auth_error") return "The model key was rejected.";
  if (normalized === "timeout") return "The model took too long to respond.";
  if (normalized === "model_access_error" || normalized === "model_not_found") return "The selected model is not available right now.";
  if (
    status === 404
    || status === 405
    || status === 501
    || raw === "not found"
    || /unsupported method/i.test(raw)
  ) {
    return `${endpointLabel} endpoint unavailable`;
  }
  if (raw) return raw;
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

function createSyntheticResponse(status, contentType = "application/json") {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get(name) {
        if (String(name || "").toLowerCase() === "content-type") return contentType;
        return null;
      },
    },
  };
}

function postJsonViaXhr(url, payload) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.responseType = "text";
    xhr.onload = () => {
      const rawText = typeof xhr.responseText === "string" ? xhr.responseText : "";
      const contentType = xhr.getResponseHeader("Content-Type") || "application/json";
      let data = { ok: false, error: rawText };
      if ((contentType || "").includes("application/json")) {
        try {
          data = rawText ? JSON.parse(rawText) : {};
        } catch {
          data = { ok: false, error: rawText || "invalid_json" };
        }
      }
      resolve({ response: createSyntheticResponse(xhr.status || 0, contentType), data });
    };
    xhr.onerror = () => reject(new Error("NetworkError"));
    xhr.onabort = () => reject(new Error("NetworkAborted"));
    xhr.send(JSON.stringify(payload));
  });
}

async function postJsonWithBrowserFallback(url, payload) {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
      credentials: "same-origin",
    });
    const data = await parseResponse(response);
    return { response, data };
  } catch (error) {
    const message = String(error?.message || "");
    if (!/Failed to fetch|NetworkError|Load failed/i.test(message)) {
      throw error;
    }
    return postJsonViaXhr(url, payload);
  }
}

function shouldRetryDebateResponse(response) {
  const status = Number(response?.status || 0);
  return status === 502 || status === 503 || status === 504;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function postDebateWithTransientRetry(url, payload) {
  const firstAttempt = await postJsonWithBrowserFallback(url, payload);
  if (!shouldRetryDebateResponse(firstAttempt.response)) {
    return { ...firstAttempt, retried: false };
  }
  setStatus("running", "Retrying debate...");
  await sleep(1200);
  const secondAttempt = await postJsonWithBrowserFallback(url, payload);
  return { ...secondAttempt, retried: true };
}

function isDebateSuccessResponse(response, data) {
  if (!response?.ok) return false;
  const turns = data?.debate?.turns;
  if (!Array.isArray(turns) || turns.length < 1) return false;
  if (data?.ok === true) return true;
  return data?.mode === "live" || data?.mode === "blocked" || data?.mode === "public-fixed";
}

async function runProviderPreflight(payload) {
  const endpoint = endpointUrl("/api/provider_preflight");
  const { response, data } = await postJsonWithBrowserFallback(endpoint, payload);
  if (!response.ok || !data.ok) {
    throw new Error(String(data?.error || "provider preflight failed"));
  }
  return data;
}

async function runDebate(event) {
  publicFixedDemoLog("run_click_received");
  event.preventDefault();
  if (READ_ONLY_DEMO) {
    setStatus("warn", "Demo mode / read-only");
    return;
  }
  if (isPublicBattleReadOnly()) {
    setStatus("warn", "Preview/Admin only");
    setHint("公開環境ではAIバトルは閲覧専用です。");
    return;
  }
  if (shouldUsePublicFixedDemo()) {
    await runPublicFixedDemo();
    return;
  }
  publicFixedDemoLog("provider_path_entered_unexpected");
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

  try {
    setStatus("running", "開始準備中");
    setHint(publicFacingOperationalHint("接続を確認しています。通常は数秒で始まります。", "開始を準備しています。"));
    await ensureApiHealthBeforeRun();
  } catch (error) {
    setStatus("error", "Connection failed");
    const message = String(error?.message || publicFacingOperationalHint("Backend not responding", "接続に失敗しました"));
    setHint(message);
    setRunMetaForImmediateFailure(message);
    outputMetaEl.textContent = `${payload.turn_count} turns · failed`;
    outputMetaEl.hidden = false;
    outputMetaEl.style.display = "";
    return;
  }

  try {
    setStatus("running", "モデル確認中");
    setHint(publicFacingOperationalHint("3ターンの討論を始める前に利用可能なモデルを確認しています。", "開始条件を確認しています。"));
    const preflight = await runProviderPreflight(payload);
    if (!preflight.ok) {
      setStatus("error", "Model check failed");
      setHint(publicFacingOperationalHint(String(preflight.error || "Model check failed"), "開始条件の確認に失敗しました。"));
      return;
    }
  } catch (error) {
    setStatus("error", "Model check failed");
    setHint(publicFacingOperationalHint(String(error?.message || "Model check failed"), "開始条件の確認に失敗しました。"));
    return;
  }

  const endpoint = endpointUrl(DEBATE_API_PATH);
  const runToken = ++currentRunToken;
  window.__lastDebateApiData = null;
  window.__lastDebateApiText = "";
  clearCurrentResultView();
  topicDisplayEl.textContent = formatTopicDisplay(payload.topic, payload.keyword || "");
  setReadingMode(false);
  judgeButton.hidden = true;
  judgeButton.disabled = true;
  runButton.disabled = true;
  setStatus("running", "3ターンの討論を生成中");
  setHint("議論を順番に組み立てています。完了まで約60〜120秒かかることがあります。");
  beginDebateTimer("3ターンの討論を生成中", "約60〜120秒");
  outputMetaEl.textContent = `${payload.turn_count} turns · pending`;
  outputMetaEl.hidden = false;
  outputMetaEl.style.display = "";

  try {
    const { response, data } = await postDebateWithTransientRetry(endpoint, payload);
    if (!isDebateSuccessResponse(response, data)) {
      throw new Error(normalizeApiError("debate", response.status, data));
    }
    if (runToken !== currentRunToken) return;
    window.__lastDebateApiData = data;
    try {
      window.__lastDebateApiText = JSON.stringify(data);
    } catch {
      window.__lastDebateApiText = "";
    }
    data.elapsed_seconds = finishDebateTimer("completed");
    renderResult(data);
    setStatus("ok", "Debate complete");
    setHint("");
    setRunMetaForResult("Completed in", data.elapsed_seconds, data.mode, data.provider_statuses || {});
    const savePromise = autosaveCurrentRun("debate_complete");
    if (isBattleMode() && currentBattleLang === "en") {
      void savePromise.then((saved) => {
        if (saved) {
          const normalized = normalizeSavedRecordForPreview(saved);
          currentLoadedRecord = normalized;
          currentRecordId = normalized.id || currentRecordId;
        }
        return ensureLocalizedViewForCurrentBattle();
      }).catch(() => {});
    }
  } catch (error) {
    if (VIEWER_MODE) {
      const fallback = await loadStaticFixture();
      fallback.elapsed_seconds = finishDebateTimer("completed");
      setRunMetaForResult("Completed in", fallback.elapsed_seconds, fallback.mode, fallback.provider_statuses || {});
      renderResult(fallback);
      setStatus("warn", "Debate complete");
    } else {
      if (currentResult?.debate?.turns?.length) {
        const message = String(error?.message || "");
        console.warn("post-success debate warning", message);
        setStatus("ok", "Debate complete");
        setHint("");
        return;
      }
      clearCurrentResultView();
      outputMetaEl.textContent = `${payload.turn_count} turns · failed`;
      outputMetaEl.hidden = false;
      outputMetaEl.style.display = "";
      const failedSeconds = finishDebateTimer("failed");
      const message = String(error?.message || "The debate could not be generated. Please check the selected models and API keys, then try again.");
      setRunMetaForResult("Failed after", failedSeconds, "failed", {});
      if (/Failed to fetch|Backend not responding|Server unavailable|NetworkError/i.test(message)) {
        setStatus("error", "Connection failed");
      } else {
        setStatus("error", "Debate failed");
      }
      setHint(message);
    }
  } finally {
    runButton.disabled = false;
    checkApiHealth();
    syncSaveButton();
  }
}

async function loadViewerArchive() {
  if (!VIEWER_MODE && !shouldUsePublicFixedDemo()) return;
  try {
    const response = await fetch(VIEWER_ARCHIVE_URL, { cache: "no-store" });
    const data = await response.json();
    curatedViewerRecords = Array.isArray(data) ? data : [];
    renderViewerList();
    renderArchiveList();
    updateHistoryButton();
    updateArchiveButton();
    if (curatedViewerRecords.length) {
      if (VIEWER_MODE) {
        loadRecordIntoView(curatedViewerRecords[0], { saved: false });
      }
    }
  } catch {
    curatedViewerRecords = [];
    renderViewerList();
    renderArchiveList();
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

async function performJudgeDebate() {
  if (!currentResult) return;
  judgeButton.disabled = true;
  setStatus("running", "判定を生成中");
  setRunMeta("判定を生成中 · 約5〜15秒", true, "running");
  setHint("討論ログを読み直して、勝敗と理由をまとめています。");
  try {
    await new Promise((resolve) => window.setTimeout(resolve, 150));
    const debate = currentResult.debate || {};
    const turns = getRawTurns(debate);
    const transcript = buildCanonicalTranscript(turns);
    const payload = {
      topic: debate.topic || currentPayload?.topic || "",
      side_a: currentPayload?.side_a || "",
      side_b: currentPayload?.side_b || "",
      turn_count: debate.turn_count || currentPayload?.turn_count || selectedTurnCount(),
      mode: currentPayload?.mode || "casual",
      fighter_a_provider: currentPayload?.fighter_a_provider || "openai",
      fighter_b_provider: currentPayload?.fighter_b_provider || "anthropic",
      api_keys: {
        openai: document.querySelector("#openai-key").value.trim(),
        anthropic: document.querySelector("#anthropic-key").value.trim(),
        gemini: document.querySelector("#gemini-key").value.trim(),
      },
      turns,
      transcript,
    };
    const { response, data } = await postJsonWithBrowserFallback(endpointUrl("/api/judge"), payload);
    if (!response.ok || !data.ok) {
      throw new Error(normalizeApiError("judge", response.status, data));
    }
    currentConstraintReport = null;
    currentJudgePass1 = null;
    currentJudgePass2 = null;
    currentStoryAlignReport = null;
    currentResult.provider_statuses = data.provider_statuses || currentResult.provider_statuses || {};
    currentResult.debate.summary = data.summary || {};
    setRevealState(false);
    refreshOutput();
    renderDebugPipeline();
    await autosaveCurrentRun("judge_complete");
    setStatus("ok", "Judge complete");
    setRunMeta("", false);
  } catch (error) {
    setStatus("error", "Judge failed");
    setHint(String(error?.message || "The judge result could not be generated. Please try again."));
    judgeButton.disabled = false;
    setRunMeta("", false);
  }
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

function applyReadOnlyDemoMode() {
  if (!READ_ONLY_DEMO) return;
  if (demoModeBadgeEl) demoModeBadgeEl.hidden = true;
  document.body.classList.add("demo-read-only");
  runButton.hidden = true;
  runButton.disabled = true;
  saveButton.hidden = true;
  saveButton.disabled = true;
}

modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    applyExperienceMode(button.dataset.experienceMode || "debate");
  });
});

battleLangButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setBattleLanguage(button.dataset.battleLang || "ja");
  });
});

[topicInputEl, sideAInputEl, sideBInputEl, keywordInput].forEach((field) => {
  field?.addEventListener("input", () => {
    if (!isBattleMode()) return;
    clearBattleXSourceError();
  });
});

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("#battle-x-build-button");
  if (!trigger) return;
  void createBattleFromXUrl();
});

shareBattleButton?.addEventListener("click", () => {
  void copyBattleShareLink();
});

shareBattleXButton?.addEventListener("click", () => {
  void shareBattleOnX();
});

form.addEventListener("submit", runDebate);
runButton.addEventListener("click", (event) => {
  if (!shouldUsePublicFixedDemo()) return;
  publicFixedDemoLog("run_click_received");
  event.preventDefault();
  event.stopPropagation();
  void runPublicFixedDemo();
});
judgeButton.addEventListener("click", () => {
  if (!currentResult) return;
  void performJudgeDebate();
});
saveButton.addEventListener("click", () => {
  if (READ_ONLY_DEMO) return;
  saveCurrentMatch();
});
historyButton.addEventListener("click", () => {
  if (isBattleMode()) {
    window.location.href = buildBattleGalleryUrl();
    return;
  }
  toggleHistory(true);
});
archiveButton.addEventListener("click", () => toggleArchive(true));
archiveCloseButton.addEventListener("click", () => toggleArchive(false));
archiveBackdrop.addEventListener("click", () => toggleArchive(false));
detailLikeButton?.addEventListener("click", () => {
  const recordId = detailLikeButton?.dataset.likeRecordId;
  if (!recordId) return;
  void incrementHistoryMetric(recordId, "like");
});
askCloseButton?.addEventListener("click", () => toggleAskPanel(false));
historyListEl?.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-record-id]");
  if (!trigger) return;
  void loadSavedMatch(trigger.dataset.recordId);
});
historyPanelEl?.addEventListener("click", (event) => {
  const sortTrigger = event.target.closest("[data-history-sort]");
  if (!sortTrigger) return;
  historySortMode = sortTrigger.dataset.historySort || "recent";
  historyPanelEl.querySelectorAll("[data-history-sort]").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.historySort === historySortMode);
  });
  void refreshHistoryRecords();
});
viewerListEl?.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-viewer-record-id]");
  if (!trigger) return;
  const record = curatedViewerRecords.find((item) => item.id === trigger.dataset.viewerRecordId);
  if (!record) return;
  loadRecordIntoView(record, { saved: false });
});
archivePanelEl?.addEventListener("click", (event) => {
  const filterTrigger = event.target.closest("[data-mode-filter]");
  if (filterTrigger) {
    archiveModeFilter = filterTrigger.dataset.modeFilter || "all";
    syncArchiveModeFilterButtons();
    renderArchiveList();
    return;
  }
  const recordTrigger = event.target.closest("[data-record-id]");
  if (!recordTrigger) return;
  const curated = curatedViewerRecords.find((item) => item.id === recordTrigger.dataset.recordId);
  if (curated) {
    loadRecordIntoView(curated, { saved: false });
    return;
  }
  void loadSavedMatch(recordTrigger.dataset.recordId);
});
archiveSearchEl?.addEventListener("input", () => {
  renderArchiveList();
});
askPanelEl?.addEventListener("click", (event) => {
  const removeTrigger = event.target.closest("[data-ask-reference-remove]");
  if (removeTrigger) {
    removeAskReference(removeTrigger.dataset.askReferenceRemove || "");
    return;
  }
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
  const addReferenceTrigger = event.target.closest("[data-ask-reference-add]");
  if (addReferenceTrigger) {
    event.preventDefault();
    event.stopPropagation();
    addAskReference(referenceFromDataset(addReferenceTrigger.dataset));
    toggleAskPanel(true);
    askInputEl.focus();
    return;
  }
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
  if (target === "first-crack") jumpToTimelineQuote(normalizeFirstCrack(summary));
  if (target === "turning") jumpToTurningPoint(summary);
  if (target === "weak") jumpToWeakSpot(summary);
  if (target === "clincher") jumpToTimelineQuote(normalizeClincher(summary));
  if (target === "gemini-quote") jumpToGeminiQuote(summary);
});
askFormEl?.addEventListener("submit", (event) => {
  event.preventDefault();
  sendAskQuestion(askInputEl.value);
});
askRetryButton?.addEventListener("click", () => {
  sendAskQuestion(askInputEl.value);
});
viewerFeedbackButton?.addEventListener("click", () => copyViewerFeedback("feedback"));
viewerTopicButton?.addEventListener("click", () => copyViewerFeedback("theme"));
apiBaseInput?.addEventListener("input", scheduleHealthCheck);

setStatus("idle", "Ready");
checkApiHealth();
void refreshHistoryRecords();
renderAskThread();
renderDebugPipeline();
setupViewerMode();
applyReadOnlyDemoMode();
applyExperienceMode(REQUESTED_EXPERIENCE_MODE);
document.documentElement.removeAttribute("data-first-paint-pending");
if (shouldUsePublicFixedDemo()) {
  void loadViewerArchive();
}
