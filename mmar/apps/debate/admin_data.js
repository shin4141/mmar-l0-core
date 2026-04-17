const tableBodyEl = document.querySelector("#admin-data-table-body");
const totalsEl = document.querySelector("#admin-data-totals");
const statusEl = document.querySelector("#admin-data-status");
const refreshButton = document.querySelector("#admin-data-refresh");
const logoutButton = document.querySelector("#admin-data-logout");
const rangeButtons = Array.from(document.querySelectorAll("[data-range-filter]"));
const statusButtons = Array.from(document.querySelectorAll("[data-status-filter]"));
const audienceButtons = Array.from(document.querySelectorAll("[data-audience-filter]"));
const sortButtons = Array.from(document.querySelectorAll("[data-sort-key]"));

let activeRange = "7d";
let activeStatus = "all";
let activeAudience = "external";
let activeSort = "views";

function setStatus(text) {
  if (!statusEl) return;
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

function syncButtons() {
  rangeButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.rangeFilter === activeRange));
  statusButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.statusFilter === activeStatus));
  audienceButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.audienceFilter === activeAudience));
  sortButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.sortKey === activeSort));
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function renderTotals(totals = {}) {
  totalsEl.innerHTML = `
    <div class="admin-total-card"><span class="admin-total-label">Views</span><strong>${formatNumber(totals.views)}</strong></div>
    <div class="admin-total-card"><span class="admin-total-label">Opens</span><strong>${formatNumber(totals.opens)}</strong></div>
    <div class="admin-total-card"><span class="admin-total-label">Shares</span><strong>${formatNumber(totals.shares)}</strong></div>
    <div class="admin-total-card"><span class="admin-total-label">Saves</span><strong>${formatNumber(totals.saves)}</strong></div>
  `;
}

function renderRows(items = []) {
  if (!items.length) {
    tableBodyEl.innerHTML = '<tr><td colspan="6" class="admin-table-empty">No cards in this range yet.</td></tr>';
    return;
  }
  tableBodyEl.innerHTML = items.map((item) => `
    <tr class="admin-data-row" data-session-id="${escapeHtml(item.session_id || item.id || "")}">
      <td>
        <button type="button" class="admin-data-link" data-session-id="${escapeHtml(item.session_id || item.id || "")}">
          ${escapeHtml(item.title || "(no title)")}
        </button>
      </td>
      <td><span class="admin-badge admin-state-badge admin-state-badge-${escapeHtml(item.status || "candidate")}">${escapeHtml(item.status || "candidate")}</span></td>
      <td>${formatNumber(item.views)}</td>
      <td>${formatNumber(item.opens)}</td>
      <td>${formatNumber(item.shares)}</td>
      <td>${formatNumber(item.saves)}</td>
    </tr>
  `).join("");
  tableBodyEl.querySelectorAll("[data-session-id]").forEach((node) => {
    node.addEventListener("click", () => {
      const sessionId = node.dataset.sessionId || "";
      if (!sessionId) return;
      window.location.href = `/admin/history?session_id=${encodeURIComponent(sessionId)}`;
    });
  });
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

async function loadSummary() {
  syncButtons();
  setStatus("Loading data...");
  const response = await fetch(
    `/api/admin/data/summary?range=${encodeURIComponent(activeRange)}&status=${encodeURIComponent(activeStatus)}&audience=${encodeURIComponent(activeAudience)}&sort=${encodeURIComponent(activeSort)}`,
    { credentials: "same-origin" },
  );
  if (response.status === 401) {
    window.location.href = "/admin/login";
    return;
  }
  const data = await response.json();
  renderTotals(data?.totals || {});
  renderRows(Array.isArray(data?.top_cards) ? data.top_cards : []);
  setStatus("");
}

function bindUi() {
  rangeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const next = button.dataset.rangeFilter || "7d";
      if (next === activeRange) return;
      activeRange = next;
      void loadSummary();
    });
  });
  statusButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const next = button.dataset.statusFilter || "all";
      if (next === activeStatus) return;
      activeStatus = next;
      void loadSummary();
    });
  });
  audienceButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const next = button.dataset.audienceFilter || "external";
      if (next === activeAudience) return;
      activeAudience = next;
      void loadSummary();
    });
  });
  sortButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const next = button.dataset.sortKey || "views";
      if (next === activeSort) return;
      activeSort = next;
      void loadSummary();
    });
  });
  refreshButton?.addEventListener("click", () => void loadSummary());
  logoutButton?.addEventListener("click", async () => {
    await fetch("/api/admin/logout", {
      method: "POST",
      credentials: "same-origin",
    });
    window.location.href = "/admin/login";
  });
}

try {
  bindUi();
  if (await requireSession()) {
    await loadSummary();
  }
} catch (error) {
  console.error("[admin-data] bootstrap failed", error);
  setStatus("Data panel failed to load.");
}
