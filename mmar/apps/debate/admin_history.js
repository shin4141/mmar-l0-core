const runListEl = document.querySelector("#admin-run-list");
const detailMetaEl = document.querySelector("#admin-detail-meta");
const detailBodyEl = document.querySelector("#admin-detail-json");
const detailModeBadgeEl = document.querySelector("#admin-detail-mode-badge");
const detailStateBadgeEl = document.querySelector("#admin-detail-state-badge");
const promoteButton = document.querySelector("#admin-promote");
const removeButton = document.querySelector("#admin-remove");
const archiveButton = document.querySelector("#admin-archive");
const deleteButton = document.querySelector("#admin-delete");
const restoreButton = document.querySelector("#admin-restore");
const refreshButton = document.querySelector("#admin-refresh");
const logoutButton = document.querySelector("#admin-logout");
const statusEl = document.querySelector("#admin-history-status");
const actionNoteEl = document.querySelector("#admin-action-note");
const xCardPanelEl = document.querySelector("#admin-x-card-panel");
const xCardUrlEl = document.querySelector("#admin-x-card-url");
const xCardStatusEl = document.querySelector("#admin-x-card-status");
const xCardPreviewEl = document.querySelector("#admin-x-card-preview");
const xCardFetchButton = document.querySelector("#admin-x-card-fetch");
const filterButtons = Array.from(document.querySelectorAll("[data-state-filter]"));
const ADMIN_HISTORY_ADD_PATH = "/api/admin/history/add";
const ADMIN_HISTORY_REMOVE_PATH = "/api/admin/history/remove";
const ADMIN_RUN_DELETE_PATH = "/api/admin/runs/delete";
const ADMIN_RUN_ARCHIVE_PATH = "/api/admin/runs/archive";
const ADMIN_RUN_RESTORE_PATH = "/api/admin/runs/restore";
const initialSessionId = new URLSearchParams(window.location.search).get("session_id") || "";

let runs = [];
let activeSessionId = "";
let activeRun = null;
let activeStateFilter = "all";

function hasRequiredDom() {
  return Boolean(
    runListEl &&
    detailMetaEl &&
    detailBodyEl &&
    detailModeBadgeEl &&
    detailStateBadgeEl &&
    promoteButton &&
    removeButton &&
    archiveButton &&
    deleteButton &&
    restoreButton &&
    refreshButton &&
    logoutButton &&
    statusEl &&
    actionNoteEl &&
    xCardPanelEl &&
    xCardUrlEl &&
    xCardStatusEl &&
    xCardPreviewEl &&
    xCardFetchButton
  );
}

function setStatus(text) {
  if (!statusEl) return;
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
}

function setActionNote(text) {
  if (!actionNoteEl) return;
  actionNoteEl.textContent = text || "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isEmbeddableXPostUrl(value) {
  try {
    const parsed = new URL(String(value || "").trim());
    const host = (parsed.hostname || "").toLowerCase();
    if (!["x.com", "www.x.com", "twitter.com", "www.twitter.com"].includes(host)) return false;
    return /\/status\/\d+/.test(parsed.pathname || "");
  } catch {
    return false;
  }
}

function clearXOEmbedPreview() {
  xCardPreviewEl.innerHTML = "";
  xCardPreviewEl.classList.add("is-empty");
}

function setXOEmbedStatus(text) {
  xCardStatusEl.textContent = text || "";
}

function renderXOEmbedFallback(text) {
  xCardPreviewEl.innerHTML = `<div class="admin-x-card-fallback">${escapeHtml(text || "Post unavailable")}</div>`;
  xCardPreviewEl.classList.remove("is-empty");
}

function xOEmbedFailureLabel(errorCode) {
  if (errorCode === "x_forbidden") return "X側の制限により埋め込めません（403）";
  if (errorCode === "invalid_x_post_url" || errorCode === "missing_url") return "URL無効";
  return "一時的に取得できませんでした";
}

function xOEmbedFailureFallback(errorCode) {
  if (errorCode === "x_forbidden") return "X側の制限により埋め込めません（403）";
  if (errorCode === "invalid_x_post_url" || errorCode === "missing_url") return "URL無効";
  return "一時的に取得できませんでした";
}

function syncXOEmbedPanel(run) {
  const sourceUrl = String(run?.source_url || "").trim();
  clearXOEmbedPreview();
  if (!run || !sourceUrl) {
    xCardPanelEl.hidden = true;
    xCardFetchButton.hidden = true;
    xCardFetchButton.disabled = true;
    xCardFetchButton.dataset.sourceUrl = "";
    xCardUrlEl.textContent = "";
    setXOEmbedStatus("");
    return;
  }
  xCardPanelEl.hidden = false;
  xCardUrlEl.textContent = sourceUrl;
  if (!isEmbeddableXPostUrl(sourceUrl)) {
    xCardFetchButton.hidden = true;
    xCardFetchButton.disabled = true;
    xCardFetchButton.dataset.sourceUrl = "";
    setXOEmbedStatus("URL無効");
    renderXOEmbedFallback("Post unavailable");
    return;
  }
  xCardFetchButton.hidden = false;
  xCardFetchButton.disabled = false;
  xCardFetchButton.dataset.sourceUrl = sourceUrl;
  xCardFetchButton.textContent = "Xカード取得";
  setXOEmbedStatus("未取得");
}

let xWidgetsPromise = null;
function ensureXWidgetsScript() {
  if (window.twttr?.widgets?.load) return Promise.resolve(window.twttr);
  if (xWidgetsPromise) return xWidgetsPromise;
  xWidgetsPromise = new Promise((resolve, reject) => {
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
  return xWidgetsPromise;
}

async function fetchXOEmbedPreview() {
  const sourceUrl = String(xCardFetchButton.dataset.sourceUrl || activeRun?.source_url || "").trim();
  if (!isEmbeddableXPostUrl(sourceUrl)) return;
  xCardFetchButton.disabled = true;
  setXOEmbedStatus("取得中...");
  try {
    const response = await fetch(`/api/x/oembed?url=${encodeURIComponent(sourceUrl)}`, { credentials: "same-origin" });
    const data = await response.json();
    if (!response.ok || !data?.ok || !data?.html) {
      const errorCode = String(data?.error || "");
      setXOEmbedStatus(xOEmbedFailureLabel(errorCode));
      renderXOEmbedFallback(xOEmbedFailureFallback(errorCode));
      return;
    }
    xCardPreviewEl.innerHTML = data.html;
    xCardPreviewEl.classList.remove("is-empty");
    await ensureXWidgetsScript();
    window.twttr?.widgets?.load?.(xCardPreviewEl);
    xCardFetchButton.textContent = "Xカード再取得";
    setXOEmbedStatus("取得済み");
  } catch (error) {
    console.error("[admin-history] x oembed fetch failed", error);
    setXOEmbedStatus("一時的に取得できませんでした");
    renderXOEmbedFallback("一時的に取得できませんでした");
  } finally {
    xCardFetchButton.disabled = false;
  }
}

function getTurns(run) {
  if (!run || typeof run !== "object") return [];
  if (Array.isArray(run.display_turns) && run.display_turns.length) return run.display_turns;
  if (Array.isArray(run.raw_turns) && run.raw_turns.length) return run.raw_turns;
  if (Array.isArray(run.transcript_json) && run.transcript_json.length) return run.transcript_json;
  return [];
}

function excerpt(run) {
  const turns = getTurns(run);
  for (const turn of turns) {
    if (!turn || typeof turn !== "object") continue;
    const text = String(turn.a || turn.b || turn.text || "").trim();
    if (text) return text.slice(0, 96);
  }
  return "";
}

function normalizeExperienceMode(run) {
  return String(run?.experience_mode || "").trim().toLowerCase() === "battle" ? "battle" : "debate";
}

function experienceModeLabel(run) {
  return normalizeExperienceMode(run) === "battle" ? "AIバトル" : "討論";
}

function experienceModeBadgeMarkup(run) {
  const mode = normalizeExperienceMode(run);
  return `<span class="admin-badge admin-mode-badge admin-mode-badge-${escapeHtml(mode)}">${escapeHtml(experienceModeLabel(run))}</span>`;
}

function normalizeRecordState(run) {
  const raw = String(run?.record_state || "").trim().toLowerCase();
  if (["published", "candidate", "failed", "archived", "deleted"].includes(raw)) return raw;
  return "candidate";
}

function recordStateLabel(run) {
  const state = normalizeRecordState(run);
  if (state === "published") return "Published";
  if (state === "failed") return "Failed";
  if (state === "archived") return "Archived";
  if (state === "deleted") return "Deleted";
  return "Candidate";
}

function isPublishedState(run) {
  return normalizeRecordState(run) === "published";
}

function isDeleteAllowed(run) {
  return ["candidate", "failed"].includes(normalizeRecordState(run));
}

function isRestoreAllowed(run) {
  return ["archived", "deleted"].includes(normalizeRecordState(run));
}

function actionNoteForRun(run) {
  if (!run) return "";
  const state = normalizeRecordState(run);
  if (state === "published") return "Published は直接削除できません。先に Candidate へ戻すか Archive してください。";
  if (state === "deleted") return "この run は削除済みです。Restore で Candidate に戻せます。";
  if (state === "archived") return "この run は Archive 済みです。Restore で Candidate に戻せます。";
  if (state === "failed") return "Failed run は Delete できます。あとで Restore 可能です。";
  return "Candidate run は Delete できます。あとで Restore 可能です。";
}

function syncActionButtons(run) {
  const disabled = !run;
  promoteButton.disabled = disabled || normalizeRecordState(run) !== "candidate";
  removeButton.disabled = disabled || !isPublishedState(run);
  archiveButton.disabled = disabled || !isPublishedState(run);
  deleteButton.disabled = disabled || !isDeleteAllowed(run);
  restoreButton.disabled = disabled || !isRestoreAllowed(run);
  setActionNote(actionNoteForRun(run));
}

function recordStateBadgeMarkup(run) {
  const state = normalizeRecordState(run);
  return `<span class="admin-badge admin-state-badge admin-state-badge-${escapeHtml(state)}">${escapeHtml(recordStateLabel(run))}</span>`;
}

function filteredRuns() {
  if (activeStateFilter === "all") {
    return runs.filter((run) => ["candidate", "published", "failed"].includes(normalizeRecordState(run)));
  }
  if (activeStateFilter === "trash") {
    return runs.filter((run) => ["archived", "deleted"].includes(normalizeRecordState(run)));
  }
  return runs.filter((run) => normalizeRecordState(run) === activeStateFilter);
}

function syncFilterButtons() {
  filterButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.stateFilter === activeStateFilter);
  });
}

function renderRuns() {
  const visibleRuns = filteredRuns();
  syncFilterButtons();
  if (!visibleRuns.length) {
    runListEl.classList.add("empty");
    runListEl.innerHTML = '<div class="empty-state">No runs in this state yet.</div>';
    return;
  }
  runListEl.classList.remove("empty");
  runListEl.innerHTML = visibleRuns.map((run) => `
    <button type="button" class="admin-run-item${run.session_id === activeSessionId ? " is-active" : ""}" data-session-id="${escapeHtml(run.session_id)}">
      <div class="admin-run-topic-row">
        <div class="admin-run-topic">${escapeHtml(run.topic || "(no topic)")}</div>
        <div class="admin-run-badge-row">
          ${recordStateBadgeMarkup(run)}
          ${experienceModeBadgeMarkup(run)}
        </div>
      </div>
      <div class="admin-run-meta">${escapeHtml(run.created_at || "")} / ${escapeHtml(run.status || "")} / ${escapeHtml(`${run.turn_count || 0} turns`)}</div>
      <div class="admin-run-snippet">${escapeHtml(excerpt(run) || "No excerpt yet.")}</div>
    </button>
  `).join("");
  const runItems = Array.from(runListEl.querySelectorAll(".admin-run-item"));
  runItems.forEach((itemEl) => {
    itemEl.addEventListener("click", async () => {
      const sessionId = itemEl.dataset.sessionId || "";
      if (!sessionId) return;
      activeSessionId = sessionId;
      renderRuns();
      setStatus("Loading detail...");
      const detail = await loadRunDetail(activeSessionId);
      renderDetail(detail);
      setStatus("");
    });
  });
}

function renderTurns(run) {
  const turns = getTurns(run);
  if (!turns.length) {
    return '<div class="empty-state">No turns saved.</div>';
  }
  return turns.map((turn, index) => `
    <section class="admin-turn-card">
      <div class="admin-turn-head">Turn ${escapeHtml(turn.turn || index + 1)}</div>
      <div class="admin-turn-grid">
        <article class="admin-turn-side">
          <div class="admin-turn-label">A</div>
          <div class="admin-turn-text">${escapeHtml(turn.a || "")}</div>
        </article>
        <article class="admin-turn-side">
          <div class="admin-turn-label">B</div>
          <div class="admin-turn-text">${escapeHtml(turn.b || "")}</div>
        </article>
      </div>
    </section>
  `).join("");
}

function renderJudge(run) {
  const judge = run?.judge_json || {};
  const winner = judge?.winner?.side || judge?.winner || "";
  const reason = judge?.reason_one_liner || judge?.verdict_headline || "";
  const quote = judge?.gemini_quote?.text || judge?.clincher_quote || "";
  if (!winner && !reason && !quote) {
    return '<div class="empty-state">No judge result saved.</div>';
  }
  return `
    <section class="admin-judge-card">
      <div><strong>Winner:</strong> ${escapeHtml(winner || "n/a")}</div>
      <div><strong>Reason:</strong> ${escapeHtml(reason || "n/a")}</div>
      <div><strong>Quote:</strong> ${escapeHtml(quote || "n/a")}</div>
    </section>
  `;
}

function renderLifecycleMeta(run) {
  const lines = [];
  if (run.deleted_at) {
    lines.push(`<div class="admin-section-copy"><strong>Deleted:</strong> ${escapeHtml(run.deleted_at)} ${escapeHtml(run.deleted_by ? `/ ${run.deleted_by}` : "")}</div>`);
  }
  if (run.archived_at) {
    lines.push(`<div class="admin-section-copy"><strong>Archived:</strong> ${escapeHtml(run.archived_at)} ${escapeHtml(run.archived_by ? `/ ${run.archived_by}` : "")}</div>`);
  }
  if (!lines.length) return "";
  return `
    <section class="admin-section">
      <div class="admin-section-title">Lifecycle</div>
      ${lines.join("")}
    </section>
  `;
}

function renderSourceUrl(run) {
  const sourceUrl = String(run?.source_url || "").trim();
  return `
    <section class="admin-section">
      <div class="admin-section-title">Source URL</div>
      <div class="admin-section-copy admin-source-url">${escapeHtml(sourceUrl || "—")}</div>
    </section>
  `;
}

function renderDetail(run) {
  activeRun = run || null;
  if (!run) {
    detailMetaEl.textContent = "Select a run.";
    detailBodyEl.innerHTML = "Select a run.";
    detailModeBadgeEl.hidden = true;
    detailStateBadgeEl.hidden = true;
    syncActionButtons(null);
    syncXOEmbedPanel(null);
    return;
  }
  const turnCount = run.turn_count || getTurns(run).length || 0;
  const mode = normalizeExperienceMode(run);
  const state = normalizeRecordState(run);
  detailModeBadgeEl.textContent = experienceModeLabel(run);
  detailModeBadgeEl.className = `admin-badge admin-mode-badge admin-mode-badge-${mode}`;
  detailModeBadgeEl.hidden = false;
  detailStateBadgeEl.textContent = recordStateLabel(run);
  detailStateBadgeEl.className = `admin-badge admin-state-badge admin-state-badge-${state}`;
  detailStateBadgeEl.hidden = false;
  detailMetaEl.textContent = `${run.created_at || ""} / ${run.status || ""} / ${turnCount} turns / ${run.session_id || ""}`;
  detailBodyEl.innerHTML = `
    <section class="admin-section">
      <div class="admin-section-title">Topic</div>
      <div class="admin-section-copy">${escapeHtml(run.topic || "")}</div>
    </section>
    <section class="admin-section">
      <div class="admin-section-title">Stances</div>
      <div class="admin-section-copy"><strong>A:</strong> ${escapeHtml(run.stance_a || "")}</div>
      <div class="admin-section-copy"><strong>B:</strong> ${escapeHtml(run.stance_b || "")}</div>
    </section>
    ${renderSourceUrl(run)}
    ${renderLifecycleMeta(run)}
    <section class="admin-section">
      <div class="admin-section-title">Turns</div>
      ${renderTurns(run)}
    </section>
    <section class="admin-section">
      <div class="admin-section-title">Judge</div>
      ${renderJudge(run)}
    </section>
  `;
  syncActionButtons(run);
  syncXOEmbedPanel(run);
}

async function requireSession() {
  const response = await fetch("/api/admin/session", { credentials: "same-origin" });
  const data = await response.json();
  if (!data?.authenticated) {
    window.location.href = "/admin/login";
    return false;
  }
  return true;
}

async function loadRunDetail(sessionId) {
  const response = await fetch(`/api/admin/runs/${encodeURIComponent(sessionId)}`, { credentials: "same-origin" });
  if (response.status === 401) {
    window.location.href = "/admin/login";
    return null;
  }
  const data = await response.json();
  return data?.item || null;
}

async function loadRuns() {
  setStatus("Loading...");
  const response = await fetch(`/api/admin/runs?state=${encodeURIComponent(activeStateFilter)}`, { credentials: "same-origin" });
  if (response.status === 401) {
    window.location.href = "/admin/login";
    return;
  }
  const data = await response.json();
  runs = Array.isArray(data.items) ? data.items : [];
  const visibleRuns = filteredRuns();
  const visibleSessionIds = new Set(visibleRuns.map((run) => run.session_id));
  if (initialSessionId && visibleSessionIds.has(initialSessionId)) {
    activeSessionId = initialSessionId;
  }
  if (!activeSessionId || !visibleSessionIds.has(activeSessionId)) {
    activeSessionId = visibleRuns[0]?.session_id || "";
  }
  renderRuns();
  if (activeSessionId) {
    const detail = await loadRunDetail(activeSessionId);
    renderDetail(detail);
  } else {
    renderDetail(null);
  }
  setStatus("");
}

async function postAdminAction(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  return { response, data };
}

async function handlePublish() {
  if (!activeRun || normalizeRecordState(activeRun) !== "candidate") return;
  setStatus("Publishing...");
  const { response, data } = await postAdminAction(ADMIN_HISTORY_ADD_PATH, { session_id: activeRun.session_id });
  if (!response.ok || !data.ok) {
    setStatus("Publish failed.");
    return;
  }
  setStatus("Published.");
  await loadRuns();
}

async function handleMoveToCandidate() {
  if (!activeRun || !isPublishedState(activeRun)) return;
  if (!window.confirm("Published を Candidate に戻します。public 側からは非表示になります。")) return;
  setStatus("Moving to candidate...");
  const { response, data } = await postAdminAction(ADMIN_HISTORY_REMOVE_PATH, { session_id: activeRun.session_id });
  if (!response.ok || !data.ok) {
    setStatus("Move failed.");
    return;
  }
  setStatus("Moved to candidate.");
  await loadRuns();
}

async function handleArchive() {
  if (!activeRun || !isPublishedState(activeRun)) return;
  if (!window.confirm("Published を Archive します。あとで Restore できます。")) return;
  setStatus("Archiving...");
  const { response, data } = await postAdminAction(ADMIN_RUN_ARCHIVE_PATH, { session_id: activeRun.session_id });
  if (!response.ok || !data.ok) {
    setStatus("Archive failed.");
    return;
  }
  setStatus("Archived.");
  activeStateFilter = "trash";
  await loadRuns();
}

async function handleDelete() {
  if (!activeRun || !isDeleteAllowed(activeRun)) return;
  if (!window.confirm("この run を削除します。あとで Restore できます。")) return;
  setStatus("Deleting...");
  const { response, data } = await postAdminAction(ADMIN_RUN_DELETE_PATH, { session_id: activeRun.session_id });
  if (!response.ok || !data.ok) {
    setStatus(data?.error === "published_delete_forbidden" ? "Published cannot be deleted directly." : "Delete failed.");
    return;
  }
  setStatus("Deleted.");
  activeStateFilter = "trash";
  await loadRuns();
}

async function handleRestore() {
  if (!activeRun || !isRestoreAllowed(activeRun)) return;
  if (!window.confirm("この run を Restore して Candidate に戻します。")) return;
  setStatus("Restoring...");
  const { response, data } = await postAdminAction(ADMIN_RUN_RESTORE_PATH, { session_id: activeRun.session_id });
  if (!response.ok || !data.ok) {
    setStatus("Restore failed.");
    return;
  }
  setStatus("Restored to candidate.");
  activeStateFilter = "candidate";
  await loadRuns();
}

function bindUi() {
  if (!hasRequiredDom()) {
    console.error("[admin-history] required DOM missing");
    return false;
  }
  promoteButton.addEventListener("click", () => void handlePublish());
  removeButton.addEventListener("click", () => void handleMoveToCandidate());
  archiveButton.addEventListener("click", () => void handleArchive());
  deleteButton.addEventListener("click", () => void handleDelete());
  restoreButton.addEventListener("click", () => void handleRestore());

  filterButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const nextFilter = button.dataset.stateFilter || "all";
      if (nextFilter === activeStateFilter) return;
      activeStateFilter = nextFilter;
      activeSessionId = "";
      await loadRuns();
    });
  });

  refreshButton.addEventListener("click", () => {
    void loadRuns();
  });

  logoutButton.addEventListener("click", async () => {
    await fetch("/api/admin/logout", {
      method: "POST",
      credentials: "same-origin",
    });
    window.location.href = "/admin/login";
  });
  xCardFetchButton.addEventListener("click", () => {
    void fetchXOEmbedPreview();
  });
  return true;
}

try {
  if (bindUi() && await requireSession()) {
    await loadRuns();
  }
} catch (error) {
  console.error("[admin-history] bootstrap failed", error);
  setStatus("Admin page failed to load.");
}
