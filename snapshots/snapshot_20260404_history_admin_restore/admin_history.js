const runListEl = document.querySelector("#admin-run-list");
const detailMetaEl = document.querySelector("#admin-detail-meta");
const detailBodyEl = document.querySelector("#admin-detail-json");
const promoteButton = document.querySelector("#admin-promote");
const removeButton = document.querySelector("#admin-remove");
const refreshButton = document.querySelector("#admin-refresh");
const logoutButton = document.querySelector("#admin-logout");
const statusEl = document.querySelector("#admin-history-status");

let runs = [];
let activeSessionId = "";
let activeRun = null;

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

function renderRuns() {
  if (!runs.length) {
    runListEl.classList.add("empty");
    runListEl.innerHTML = '<div class="empty-state">No runs yet.</div>';
    return;
  }
  runListEl.classList.remove("empty");
  runListEl.innerHTML = runs.map((run) => `
    <button type="button" class="admin-run-item${run.session_id === activeSessionId ? " is-active" : ""}" data-session-id="${escapeHtml(run.session_id)}">
      <div class="admin-run-topic">${escapeHtml(run.topic || "(no topic)")}</div>
      <div class="admin-run-meta">${escapeHtml(run.created_at || "")} / ${escapeHtml(run.status || "")} / ${escapeHtml(`${run.turn_count || 0} turns`)}</div>
      <div class="admin-run-snippet">${escapeHtml(excerpt(run) || "No excerpt yet.")}</div>
      <div class="admin-run-badges">${run.curated ? '<span class="admin-badge">Curated</span>' : ""}</div>
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
    promoteButton.disabled = true;
    removeButton.disabled = true;
    return;
  }
  const turnCount = run.turn_count || getTurns(run).length || 0;
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
  promoteButton.disabled = !!run.curated;
  removeButton.disabled = !run.curated;
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
  if (!activeSessionId && runs.length) activeSessionId = runs[0].session_id || "";
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

promoteButton.addEventListener("click", async () => {
  if (!activeSessionId) return;
  setStatus("Adding to History...");
  const response = await fetch("/api/admin/history/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ session_id: activeSessionId }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    setStatus("Add failed.");
    return;
  }
  setStatus("Added to History.");
  await loadRuns();
});

removeButton.addEventListener("click", async () => {
  if (!activeSessionId) return;
  setStatus("Removing from History...");
  const response = await fetch("/api/admin/history/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ session_id: activeSessionId }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    setStatus("Remove failed.");
    return;
  }
  setStatus("Removed from History.");
  await loadRuns();
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
