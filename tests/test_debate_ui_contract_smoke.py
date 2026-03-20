import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "mmar" / "apps" / "debate" / "debate.html"
JS_PATH = ROOT / "mmar" / "apps" / "debate" / "debate.js"
FIXTURE_PATH = ROOT / "mmar" / "apps" / "debate" / "fixtures" / "debate_demo.json"
VIEWER_ARCHIVE_PATH = ROOT / "mmar" / "apps" / "debate" / "fixtures" / "viewer_archive.json"
SCHEMA_PATH = ROOT / "schemas" / "debate_response.public.json"
DEV_API_PATH = ROOT / "tools" / "dev_api.py"
RENDER_PATH = ROOT / "render.yaml"
REQUIREMENTS_PATH = ROOT / "requirements.txt"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json(path: Path):
    return json.loads(_read(path))


def test_fixture_matches_public_contract_shape():
    fixture = _load_json(FIXTURE_PATH)
    schema = _load_json(SCHEMA_PATH)

    assert all(key in fixture for key in schema["required"])
    assert sorted(fixture["provider_statuses"].keys()) == ["anthropic", "gemini", "openai"]

    assert "debate" in fixture
    assert "turns" in fixture["debate"]
    assert "summary" in fixture["debate"]
    assert isinstance(fixture["debate"]["turns"], list)
    assert fixture["debate"]["turns"]

    required_turn_keys = schema["$defs"]["debateTurn"]["required"]
    assert all(all(key in turn for key in required_turn_keys) for turn in fixture["debate"]["turns"])

    summary = fixture["debate"]["summary"]
    for key in schema["$defs"]["debateSummary"]["required"]:
      assert key in summary

    assert "fatal_phrase" in summary
    assert "winner" in summary
    assert "reason_one_liner" in summary
    assert "weak_spot" in summary
    assert "turning_point" in summary
    assert "contradiction_exposed" in summary
    assert "provisional_judgment" in summary
    assert "key_disagreement_top3" in summary
    for turn in fixture["debate"]["turns"]:
        assert "Aは" not in turn["a"]
        assert "Bは" not in turn["b"]
        assert "冒頭で" not in turn["a"]
        assert "最後に" not in turn["a"]


def test_viewer_archive_has_curated_records():
    archive = _load_json(VIEWER_ARCHIVE_PATH)
    assert isinstance(archive, list)
    assert len(archive) >= 3
    first = archive[0]
    for key in ["id", "topic", "stance_a", "stance_b", "turn_count", "mode", "transcript_json", "judge_json", "tease"]:
        assert key in first
    assert first["judge_json"]["verdict_headline"]
    assert first["judge_json"]["winner"]["side"] in {"A", "B", "Draw"}


def test_html_starts_without_structure_result_panel():
    html = _read(HTML_PATH)

    assert "Structure Detector Result" not in html
    assert 'id="verdict-strip"' not in html
    assert 'id="judge-button"' in html
    assert 'id="save-button"' in html
    assert 'id="history-button"' in html
    assert 'id="archive-button"' in html
    assert 'id="history-shell"' in html
    assert 'id="history-panel"' in html
    assert 'id="archive-shell"' in html
    assert 'id="archive-panel"' in html
    assert 'id="viewer-library"' in html
    assert 'id="viewer-list"' in html
    assert 'id="viewer-feedback-button"' in html
    assert 'id="viewer-topic-button"' in html
    assert 'id="archive-search"' in html
    assert 'data-mode-filter="all"' in html
    assert 'data-mode-filter="casual"' in html
    assert 'data-mode-filter="pro"' in html
    assert 'id="ask-shell"' in html
    assert 'この試合についてGeminiに聞く' in html
    assert "History Viewer" not in html
    assert "History (0)" in html
    assert 'id="api-health"' not in html
    assert 'id="source-mode"' not in html
    assert 'hidden disabled' in html or 'disabled hidden' in html
    assert 'id="turn-log"' in html
    assert 'placeholder="空欄なら same-origin"' in html
    assert 'id="demo-mode-badge"' in html
    assert 'id="debug-pipeline-panel"' in html
    assert 'id="debug-constraint-report"' in html
    assert 'id="debug-judge-pass1"' in html
    assert 'id="debug-judge-pass2"' in html
    assert 'id="debug-story-align-report"' in html


def test_js_uses_fixture_fallback_and_public_contract_keys():
    js = _read(JS_PATH)

    assert 'fetch("./fixtures/debate_demo.json"' in js
    assert "currentResult.provider_statuses" in js
    assert "debate.topic" in js
    assert "debate.turns" in js
    assert "debate.summary" in js
    assert "summary?.winner" in js
    assert "summary?.reason_one_liner" in js
    assert "summary?.weak_spot" in js
    assert "raw.why_one_sentence" in js
    assert "raw.how_to_fix" in js
    assert "raw.quote_excerpt" in js
    assert "summary?.fatal_phrase" in js
    assert "summary?.turning_point" in js
    assert "function stringifyTurningPointValue(value)" in js
    assert "function fatalPhraseTextCandidate(value)" in js
    assert "summary?.gemini_takeaway" in js
    assert "summary?.gemini_quote" in js
    assert "summary?.contradiction_exposed" in js
    assert "normalizeWinner(summary)" in js
    assert "normalizeWeakSpot(summary)" in js
    assert "normalizeFatalPhrase(summary)" in js
    assert "normalizeTurningPoint(summary)" in js
    assert "summary?.provisional_judgment" in js
    assert "summary?.key_disagreement_top3" in js
    assert 'HISTORY_STORAGE_KEY' in js
    assert 'localStorage' in js
    assert "function renderArchiveList()" in js
    assert "function toggleArchive(open)" in js
    assert "function filteredArchiveRecords(records, query, modeFilter)" in js
    assert "function buildOutputMeta(providerStatuses, turnCount, mode, savedOutputMeta = \"\", options = {})" in js
    assert "function hasCompletedJudgePipeline(summary)" in js
    assert "function providerStatusesForDisplay(providerStatuses, summary)" in js
    assert "const { preferSaved = false } = options;" in js
    assert "if (preferSaved && normalizedSavedOutputMeta) return normalizedSavedOutputMeta;" in js
    assert "const providerStatuses = providerStatusesForDisplay(currentResult.provider_statuses || {}, debate.summary || {});" in js
    assert "currentLoadedRecord ? currentResult.output_meta || \"\" : \"\"" in js
    assert "{ preferSaved: Boolean(currentLoadedRecord) && !hasCompletedJudgePipeline(debate.summary || {}) }" in js
    assert 'endpointUrl("/api/ask_match")' in js
    assert 'return raw || window.location.origin;' in js
    assert 'normalizeApiError("ask_match", response.status, data)' in js
    assert 'normalizeApiError("debate", response.status, data)' in js
    assert 'return `${endpointLabel} endpoint unavailable`;' in js
    assert 'savedOutputMeta && typeof savedOutputMeta === "object"' in js
    assert 'judgeRaw = savedOutputMeta.judge_raw_received === true ? "raw:yes" : "raw:no"' in js
    assert 'judgeParse = savedOutputMeta.judge_parse_success === true ? "parse:yes" : "parse:no"' in js
    assert "status === 405" in js
    assert "status === 501" in js
    assert "判定理由が短く返っていません" not in js
    assert 'const VIEWER_MODE = queryParams.get("viewer") === "1" || queryParams.get("demo") === "1";' in js
    assert 'const READ_ONLY_DEMO = /(^|\\\\.)onrender\\\\.com$/i.test(window.location.hostname);' in js
    assert 'const VIEWER_ARCHIVE_URL = "./fixtures/viewer_archive.json";' in js
    assert "function renderViewerList()" in js
    assert "function loadViewerArchive()" in js
    assert "function loadRecordIntoView(record, options = {})" in js
    assert "function setupViewerMode()" in js
    assert "function applyReadOnlyDemoMode()" in js
    assert "function renderDebugPipeline()" in js
    assert "currentConstraintReport" in js
    assert "currentJudgePass1" in js
    assert "currentJudgePass2" in js
    assert "currentStoryAlignReport" in js
    assert "currentStoryAlignReport.ui_normalization" in js
    assert "currentConstraintReport = currentResult?.debate?.summary?.debug_constraint_report || null;" in js
    assert "currentJudgePass1 = currentResult?.debate?.summary?.debug_pass1 || null;" in js
    assert "currentJudgePass2 = currentResult?.debate?.summary?.debug_pass2 || null;" in js
    assert "currentStoryAlignReport = currentResult?.debate?.summary?.debug_story_align_report || null;" in js
    assert 'setStatus("warn", "Demo mode / read-only");' in js
    assert "runButton.hidden = true;" in js
    assert "saveButton.hidden = true;" in js
    assert 'debug_constraint_report' in js
    assert 'debug_pass1' in js
    assert 'debug_pass2' in js
    assert 'debug_story_align_report' in js


def test_js_preserves_judge_before_after_flow():
    js = _read(JS_PATH)

    assert "destroyVerdictStrip();" in js
    assert "ensureVerdictStrip();" in js
    assert "destroyAnalysisPanel();" in js
    assert "ensureAnalysisPanel();" in js
    assert "setRevealState(true);" in js
    assert "setRevealState(false);" in js
    assert "judgeButton.hidden = false;" in js
    assert "renderSummary(debate.summary || {});" in js
    assert 'id = "verdict-strip"' in js or 'id="verdict-strip"' in js
    assert 'Structure Detector Result' in js
    assert 'Gemini Takeaway' in js
    assert 'Gemini Quote' in js
    assert 'setStatus("ok", "Debate ready")' in js
    assert 'setStatus("ok", "Structure revealed")' in js
    assert "saveButton.hidden = false;" in js
    assert 'id="ask-match-button"' in js
    assert 'setRunMeta("Generating...", true);' in js
    assert 'setRunMeta("Judging...", true);' in js
    assert 'data-jump-target="fatal"' in js
    assert 'data-jump-target="turning"' in js
    assert 'data-jump-target="weak"' in js
    assert 'Turn ${weakSpot.turn}' in js
    assert 'weakSpot.quote_excerpt' in js
    assert 'weakSpot.how_to_fix' in js
    assert 'id="analysis-toggle-button"' in js
    assert '▼ 分析を見る' in js
    assert '▲ 分析を閉じる' in js


def test_js_exposes_phase_and_provider_status_ui():
    js = _read(JS_PATH)

    assert 'return { phase: "Turn 1", stage: "主張" };' in js
    assert 'return { phase: "Turn 2", stage: "反論" };' in js
    assert 'return { phase: "Turn 3", stage: "討論開始" };' in js
    assert 'stage: "討論継続"' in js
    assert 'stage: "締め"' in js

    assert 'let currentFighters = { a: "openai", b: "anthropic", judge: "gemini" };' in js
    assert "formatProviderToken(\"A\", currentFighters.a, providerStatuses)" in js
    assert "formatProviderToken(\"B\", currentFighters.b, providerStatuses)" in js
    assert "formatProviderToken(\"J\", currentFighters.judge, providerStatuses)" in js
    assert "return [countText, ...tokens].join(\" · \");" in js
    assert "provider_error" in js
    assert "fallback" in js
    assert "mock" in js


def test_mobile_layout_hooks_exist():
    html = _read(HTML_PATH)
    js = _read(JS_PATH)
    css = _read(ROOT / "mmar" / "apps" / "debate" / "debate.css")

    assert 'meta name="viewport" content="width=device-width,initial-scale=1"' in html
    assert 'const mobileMedia = window.matchMedia("(max-width: 768px)");' in js
    assert 'document.body.classList.toggle("mobile-ui", isMobileLayout())' in js
    assert 'mobileAnalysisCollapsed = true' in js
    assert 'syncMobileAnalysisPanel()' in js
    assert '@media (max-width: 760px)' in css
    assert 'body.mobile-ui #run-button' in css
    assert 'min-height: 60px;' in css
    assert 'width: 100%;' in css
    assert 'body.mobile-ui .topline,' in css
    assert 'body.mobile-ui .session-box' in css
    assert 'display: none;' in css
    assert 'body.mobile-ui .gemini-quote-copy' in css
    assert 'font-size: 20px;' in css
    assert 'text-align: center;' in css
    assert 'body.mobile-ui #analysis-panel.mobile-analysis-collapsed #analysis-content' in css


def test_dev_api_exposes_server_history_routes():
    dev_api = _read(DEV_API_PATH)

    assert '"/api/history/list"' in dev_api
    assert 'query = parse_qs(parsed_url.query or "")' in dev_api
    assert 'sort = str(query.get("sort", ["recent"])[0] or "recent")' in dev_api
    assert 'list_history_records(sort=sort)' in dev_api
    assert '"/api/history/save"' in dev_api
    assert '"/api/history/view/"' in dev_api
    assert '"/api/history/like/"' in dev_api
    assert 'if path.startswith("/api/history/")' in dev_api
    assert 'GET  /api/history/list' in dev_api
    assert 'GET  /api/history/{{id}}' in dev_api
    assert 'POST /api/history/save' in dev_api
    assert 'POST /api/history/view/{{id}}' in dev_api
    assert 'POST /api/history/like/{{id}}' in dev_api
    assert 'HOST = os.getenv("HOST", "0.0.0.0")' in dev_api
    assert 'candidate = "/mmar/apps/debate/debate.html"' in dev_api
    assert 'static_path = _safe_static_path(path)' in dev_api
    assert 'forwarded_proto = handler.headers.get("X-Forwarded-Proto", "").strip()' in dev_api
    assert 'return f"{proto}://{request_host}"' in dev_api


def test_render_files_exist_for_same_origin_deploy():
    render_yaml = _read(RENDER_PATH)
    requirements = _read(REQUIREMENTS_PATH)

    assert "type: web" in render_yaml
    assert "runtime: python" in render_yaml
    assert "startCommand: python tools/dev_api.py" in render_yaml
    assert "healthCheckPath: /api/health" in render_yaml
    assert "key: HISTORY_DB_PATH" in render_yaml
    assert "value: /var/data/mmar/history.sqlite" in render_yaml
    assert "mountPath: /var/data" in render_yaml
    assert requirements.strip() == ""


def test_js_composes_human_verdict_strip_from_summary():
    js = _read(JS_PATH)

    assert "composeVerdictHeadline(topic, winner)" in js
    assert "composeVerdictSubline(topic, winner, why)" in js
    assert "function normalizeMomentum(summary, winner, confidence)" in js
    assert "const raw = summary?.momentum;" in js
    assert "momentum: normalizeMomentum(summary, winner, confidence)," in js
    assert "composeFlipCondition(winner, weakSpot, why)" in js
    assert "normalizeGeminiTakeaway(summary, topic)" in js
    assert "normalizeGeminiQuote(summary)" in js
    assert "looksLikeGenericGeminiQuote" in js
    assert "extractGeminiQuoteConcepts" in js
    assert "Winner ${escapeHtml(winner.side)}" in js
    assert "Momentum Bar" in js
    assert "Flip Condition" in js
    assert "gemini-takeaway-card" in js
    assert "gemini-quote-card" in js
    assert "Turn ${fatal.turn} / ${fatal.speaker}" in js
    assert '少なくとも今回は' in js


def test_js_supports_save_history_and_load_flow():
    js = _read(JS_PATH)
    html = _read(HTML_PATH)

    assert "function buildBattleRecord(result, payload)" in js
    assert "function normalizeSavedRecordForPreview(record)" in js
    assert 'function fetchHistoryListFromServer(sort = "recent")' in js
    assert "function fetchHistoryRecordById(recordId)" in js
    assert "function refreshHistoryRecords()" in js
    assert "function saveHistoryRecordToServer(record)" in js
    assert "let historyRecordsHydrated = false;" in js
    assert "let historyFetchInFlight = false;" in js
    assert "function saveCurrentMatch()" in js
    assert "function renderHistoryList()" in js
    assert "function renderArchiveList()" in js
    assert "function loadSavedMatch(recordId)" in js
    assert "function updateHistoryButton" in js
    assert "function updateArchiveButton" in js
    assert 'let historySortMode = "recent";' in js
    assert 'endpointUrl(`/api/history/list${query}`)' in js
    assert 'const query = sort === "likes" ? "?sort=likes" : "";' in js
    assert 'await fetchHistoryListFromServer(historySortMode);' in js
    assert 'data-history-sort="recent"' in html
    assert 'data-history-sort="likes"' in html
    assert 'historyPanelEl.addEventListener("click", (event) => {' in js
    assert 'sortTrigger.dataset.historySort' in js
    assert 'endpointUrl(`/api/history/${encodeURIComponent(recordId)}`)' in js
    assert 'endpointUrl("/api/history/save")' in js
    assert 'endpointUrl(`/api/history/${metric}/${encodeURIComponent(recordId)}`)' in js
    assert "historyFetchInFlight = true;" in js
    assert "historyRecordsHydrated = true;" in js
    assert "履歴を読み込み中です。" in js
    assert 'saveButton.addEventListener("click", () => {' in js
    assert 'if (READ_ONLY_DEMO) return;' in js
    assert 'saveCurrentMatch();' in js
    assert 'outputPanelEl.addEventListener("click", (event) => {' in js
    assert 'event.target.closest("#ask-match-button")' in js
    assert 'historyButton.addEventListener("click", () => toggleHistory(true));' in js
    assert 'archiveButton.addEventListener("click", () => toggleArchive(true));' in js
    assert 'historyBackdrop.addEventListener("click", () => toggleHistory(false));' in js
    assert 'archiveBackdrop.addEventListener("click", () => toggleArchive(false));' in js
    assert "loadSavedMatch(trigger.dataset.recordId);" in js
    assert 'data-like-record-id' in js
    assert 'Views ${preview.views || 0} · Likes ${preview.likes || 0}' in js
    assert 'incrementHistoryMetric(likeTrigger.dataset.likeRecordId, "like")' in js
    assert 'await incrementHistoryMetric(recordId, "view");' in js
    assert "function getCurrentBattleRecord()" in js
    assert "function sendAskQuestion(question)" in js
    assert "const preview = normalizeSavedRecordForPreview(record);" in js
    assert "return Array.isArray(parsed) ? parsed.map(normalizeSavedRecordForPreview) : [];" in js
    assert 'const fill = trigger.dataset.fill || "";' in js
    assert "const dismissedAskHints = new Set();" in js
    assert 'viewerListEl.addEventListener("click", (event) => {' in js
    assert 'viewerFeedbackButton.addEventListener("click", () => copyViewerFeedback("feedback"));' in js
    assert 'void refreshHistoryRecords();' in js


def test_js_supports_jump_from_judge_cards_to_turn_log():
    js = _read(JS_PATH)
    css = _read(ROOT / "mmar" / "apps" / "debate" / "debate.css")

    assert 'id="turn-${escapeHtml(turn.turn)}"' in js
    assert 'data-turn="${escapeHtml(turn.turn)}"' in js
    assert 'data-speaker="A"' in js
    assert 'data-speaker="B"' in js
    assert "function jumpToFatalPhrase(summary)" in js
    assert "function jumpToTurningPoint(summary)" in js
    assert "function jumpToWeakSpot(summary)" in js
    assert 'event.target.closest(".summary-jump-card")' in js
    assert "scrollIntoView({ behavior: \"smooth\", block: \"center\" })" in js
    assert ".summary-jump-card" in css
    assert ".jump-highlight" in css
    assert "@keyframes jumpPulse" in css
