const runListEl = document.querySelector("#admin-run-list");
const detailMetaEl = document.querySelector("#admin-detail-meta");
const detailBodyEl = document.querySelector("#admin-detail-json");
const detailModeBadgeEl = document.querySelector("#admin-detail-mode-badge");
const detailStateBadgeEl = document.querySelector("#admin-detail-state-badge");
let promoteButton = document.querySelector("#admin-promote");
const removeButton = document.querySelector("#admin-remove");
const refreshButton = document.querySelector("#admin-refresh");
const logoutButton = document.querySelector("#admin-logout");
const statusEl = document.querySelector("#admin-history-status");
const filterButtons = Array.from(document.querySelectorAll("[data-state-filter]"));
const ADMIN_HISTORY_ADD_PATH = "/api/admin/history/add";
const ADMIN_HISTORY_REMOVE_PATH = "/api/admin/history/remove";

let runs = [];
let activeSessionId = "";
let activeRun = null;
let activeStateFilter = "all";

function setStatus(text) {
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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
  return String(run?.record_state || "").trim().toLowerCase() === "published" ? "published" : "candidate";
}

function recordStateLabel(run) {
  return normalizeRecordState(run) === "published" ? "Published" : "Candidate";
}

function isPublishedState(run) {
  return normalizeRecordState(run) === "published";
}

function isCandidateState(run) {
  return !isPublishedState(run);
}

function syncActionButtons(run) {
  if (!run) {
    promoteButton.disabled = true;
    promoteButton.setAttribute("aria-disabled", "true");
    removeButton.disabled = true;
    return;
  }
  const publishEnabled = isCandidateState(run);
  promoteButton.disabled = !publishEnabled;
  promoteButton.setAttribute("aria-disabled", publishEnabled ? "false" : "true");
  removeButton.disabled = !isPublishedState(run);
}

async function handlePromoteClick(run) {
  if (!run || !run.session_id || !isCandidateState(run)) return;
  console.log("clicked publish");
  setStatus("Publishing...");
  const response = await fetch(ADMIN_HISTORY_ADD_PATH, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ session_id: run.session_id }),
  });
  const text = await response.text();
  console.log("[admin-promote]", response.status, text);
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  if (!response.ok || !data.ok) {
    setStatus("Publish failed.");
    return;
  }
  setStatus("Published.");
  await loadRuns();
}

function rebuildPromoteButton(run) {
  const oldButton = promoteButton;
  const nextButton = oldButton.cloneNode(true);
  oldButton.replaceWith(nextButton);
  promoteButton = nextButton;
  syncActionButtons(run);
  promoteButton.addEventListener("click", async () => {
    if (!isCandidateState(run)) return;
    await handlePromoteClick(run);
  });
}

function recordStateBadgeMarkup(run) {
  const state = normalizeRecordState(run);
  return `<span class="admin-badge admin-state-badge admin-state-badge-${escapeHtml(state)}">${escapeHtml(recordStateLabel(run))}</span>`;
}

function filteredRuns() {
  if (activeStateFilter === "all") return runs;
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

function renderDetail(run) {
  activeRun = run || null;
  if (!run) {
    detailMetaEl.textContent = "Select a run.";
    detailBodyEl.innerHTML = "Select a run.";
    if (detailModeBadgeEl) detailModeBadgeEl.hidden = true;
    if (detailStateBadgeEl) detailStateBadgeEl.hidden = true;
    rebuildPromoteButton(null);
    return;
  }
  const turnCount = run.turn_count || getTurns(run).length || 0;
  if (detailModeBadgeEl) {
    const mode = normalizeExperienceMode(run);
    detailModeBadgeEl.textContent = experienceModeLabel(run);
    detailModeBadgeEl.className = `admin-badge admin-mode-badge admin-mode-badge-${mode}`;
    detailModeBadgeEl.hidden = false;
  }
  if (detailStateBadgeEl) {
    const state = normalizeRecordState(run);
    detailStateBadgeEl.textContent = recordStateLabel(run);
    detailStateBadgeEl.className = `admin-badge admin-state-badge admin-state-badge-${state}`;
    detailStateBadgeEl.hidden = false;
  }
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
    <section class="admin-section">
      <div class="admin-section-title">Turns</div>
      ${renderTurns(run)}
    </section>
    <section class="admin-section">
      <div class="admin-section-title">Judge</div>
      ${renderJudge(run)}
    </section>
  `;
  rebuildPromoteButton(run);
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
  const response = await fetch("/api/admin/runs", { credentials: "same-origin" });
  if (response.status === 401) {
    window.location.href = "/admin/login";
    return;
  }
  const data = await response.json();
  runs = Array.isArray(data.items) ? data.items : [];
  const visibleRuns = filteredRuns();
  const visibleSessionIds = new Set(visibleRuns.map((run) => run.session_id));
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

runListEl.addEventListener("click", async (event) => {
  const trigger = event.target.closest("[data-session-id]");
  if (!trigger) return;
  activeSessionId = trigger.dataset.sessionId || "";
  renderRuns();
  setStatus("Loading detail...");
  const detail = await loadRunDetail(activeSessionId);
  renderDetail(detail);
  setStatus("");
});

removeButton.addEventListener("click", async () => {
  if (!activeSessionId) return;
  setStatus("Moving to candidate...");
  const response = await fetch(ADMIN_HISTORY_REMOVE_PATH, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ session_id: activeSessionId }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    setStatus("Move failed.");
    return;
  }
  setStatus("Moved to candidate.");
  await loadRuns();
});

filterButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const nextFilter = button.dataset.stateFilter || "all";
    if (nextFilter === activeStateFilter) return;
    activeStateFilter = nextFilter;
    renderRuns();
    const visibleRuns = filteredRuns();
    activeSessionId = visibleRuns[0]?.session_id || "";
    if (activeSessionId) {
      setStatus("Loading detail...");
      const detail = await loadRunDetail(activeSessionId);
      renderDetail(detail);
      setStatus("");
      return;
    }
    renderDetail(null);
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

if (await requireSession()) {
  await loadRuns();
}
