const runListEl = document.querySelector("#admin-run-list");
const detailMetaEl = document.querySelector("#admin-detail-meta");
const detailJsonEl = document.querySelector("#admin-detail-json");
const promoteButton = document.querySelector("#admin-promote");
const refreshButton = document.querySelector("#admin-refresh");
const logoutButton = document.querySelector("#admin-logout");
const statusEl = document.querySelector("#admin-history-status");

let runs = [];
let activeSessionId = "";

function setStatus(text) {
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
}

function renderRuns() {
  if (!runs.length) {
    runListEl.classList.add("empty");
    runListEl.innerHTML = '<div class="empty-state">No runs yet.</div>';
    return;
  }
  runListEl.classList.remove("empty");
  runListEl.innerHTML = runs.map((run) => `
    <button type="button" class="admin-run-item${run.session_id === activeSessionId ? " is-active" : ""}" data-session-id="${run.session_id}">
      <div class="admin-run-topic">${run.topic || "(no topic)"}</div>
      <div class="admin-run-meta">${run.created_at || ""} / ${run.status || ""}</div>
    </button>
  `).join("");
}

function renderDetail(run) {
  if (!run) {
    detailMetaEl.textContent = "Select a run.";
    detailJsonEl.textContent = "Select a run.";
    promoteButton.disabled = true;
    return;
  }
  detailMetaEl.textContent = `${run.created_at || ""} / ${run.status || ""} / ${run.session_id || ""}`;
  detailJsonEl.textContent = JSON.stringify(run, null, 2);
  promoteButton.disabled = false;
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
  renderDetail(runs.find((item) => item.session_id === activeSessionId) || runs[0] || null);
  setStatus("");
}

runListEl.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-session-id]");
  if (!trigger) return;
  activeSessionId = trigger.dataset.sessionId || "";
  renderRuns();
  renderDetail(runs.find((item) => item.session_id === activeSessionId) || null);
});

promoteButton.addEventListener("click", async () => {
  if (!activeSessionId) return;
  setStatus("Promoting...");
  const response = await fetch("/api/admin/history/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ session_id: activeSessionId }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    setStatus("Promote failed.");
    return;
  }
  setStatus("Added to History.");
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
