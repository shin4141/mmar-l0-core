const tableBodyEl = document.querySelector("#admin-data-table-body");
const totalsEl = document.querySelector("#admin-data-totals");
const statusEl = document.querySelector("#admin-data-status");
const refreshButton = document.querySelector("#admin-data-refresh");
const logoutButton = document.querySelector("#admin-data-logout");
const dailyChartEl = document.querySelector("#admin-daily-chart");
const dailyStatsEl = document.querySelector("#admin-daily-stats");
const dailySelectedEl = document.querySelector("#admin-daily-selected");
const rangeButtons = Array.from(document.querySelectorAll("[data-range-filter]"));
const statusButtons = Array.from(document.querySelectorAll("[data-status-filter]"));
const audienceButtons = Array.from(document.querySelectorAll("[data-audience-filter]"));
const sortButtons = Array.from(document.querySelectorAll("[data-sort-key]"));
const dailyRangeButtons = Array.from(document.querySelectorAll("[data-daily-range]"));

let activeRange = "7d";
let activeStatus = "all";
let activeAudience = "external";
let activeSort = "views";
let activeDailyRange = 7;

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
  dailyRangeButtons.forEach((button) => button.classList.toggle("is-active", Number(button.dataset.dailyRange || 0) === activeDailyRange));
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function formatRate(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatDelta(value, formatter = formatNumber) {
  const number = Number(value || 0);
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${formatter(number)}`;
}

function renderComparison(label, comparison = {}, metric, formatter = formatNumber) {
  const entry = comparison?.[metric] || {};
  return `${label} ${formatDelta(entry.delta, formatter)}`;
}

function renderTotals(totals = {}, meta = {}) {
  const rangeLabel = activeRange === "all" ? "All-time events" : `${activeRange} events`;
  const today = meta.today || {};
  const comparisons = meta.comparisons || {};
  totalsEl.innerHTML = `
    <div class="admin-total-card"><span class="admin-total-label">${escapeHtml(rangeLabel)} views</span><strong>${formatNumber(totals.views)}</strong><small>${escapeHtml(renderComparison("7d vs prev 7d", comparisons.last_7d_vs_previous_7d, "views"))}</small></div>
    <div class="admin-total-card"><span class="admin-total-label">${escapeHtml(rangeLabel)} opens</span><strong>${formatNumber(totals.opens)}</strong><small>${escapeHtml(renderComparison("7d vs prev 7d", comparisons.last_7d_vs_previous_7d, "opens"))}</small></div>
    <div class="admin-total-card"><span class="admin-total-label">Open rate</span><strong>${formatRate(totals.open_rate)}</strong><small>${escapeHtml(renderComparison("7d vs prev 7d", comparisons.last_7d_vs_previous_7d, "open_rate", formatRate))}</small></div>
    <div class="admin-total-card"><span class="admin-total-label">Today</span><strong>${formatNumber(today.views)} views</strong><small>${formatNumber(today.opens)} opens · ${formatRate(today.open_rate)} open rate · ${escapeHtml(renderComparison("vs yesterday", comparisons.today_vs_yesterday, "views"))}</small></div>
  `;
}

function renderRows(items = []) {
  if (!items.length) {
    tableBodyEl.innerHTML = '<tr><td colspan="9" class="admin-table-empty">No cards in this range yet.</td></tr>';
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
      <td>${formatRate(item.open_rate)}</td>
      <td>${formatNumber(item.views_today)}</td>
      <td>${formatNumber(item.opens_today)}</td>
      <td>${formatNumber(item.shares_today)}</td>
      <td>${formatRate(item.open_rate_today)}</td>
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

function renderDailyEmpty(text) {
  if (dailySelectedEl) dailySelectedEl.textContent = "All published battles · daily deltas from event logs";
  if (dailyChartEl) dailyChartEl.innerHTML = `<div class="admin-daily-empty">${escapeHtml(text)}</div>`;
  if (dailyStatsEl) dailyStatsEl.innerHTML = "";
}

function metricPoint(row, key) {
  return Number(row?.[key] || 0);
}

function renderDailyMetrics(rows = []) {
  syncButtons();
  if (!dailyChartEl || !dailyStatsEl) return;
  if (dailySelectedEl) dailySelectedEl.textContent = "All published battles";
  if (!rows.length) {
    renderDailyEmpty("No daily metrics yet.");
    return;
  }
  const width = 720;
  const height = 210;
  const padX = 36;
  const padY = 24;
  const values = rows.map((row) => metricPoint(row, "views"));
  const maxValue = Math.max(1, ...values);
  const points = rows.map((row, index) => {
    const x = rows.length === 1 ? width / 2 : padX + (index * (width - padX * 2)) / (rows.length - 1);
    const y = height - padY - (metricPoint(row, "views") / maxValue) * (height - padY * 2);
    return { x, y, row };
  });
  const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const last = rows[rows.length - 1] || {};
  dailyChartEl.innerHTML = `
    <svg class="admin-daily-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily views line chart">
      <line x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}" class="admin-daily-axis"></line>
      <line x1="${padX}" y1="${padY}" x2="${padX}" y2="${height - padY}" class="admin-daily-axis"></line>
      <polyline class="admin-daily-line" points="${line}"></polyline>
      ${points.map((point) => `<circle class="admin-daily-point" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="4"><title>${escapeHtml(`${point.row.date}: ${point.row.views || 0} views, ${point.row.opens || 0} opens`)}</title></circle>`).join("")}
      <text x="${padX}" y="${padY - 8}" class="admin-daily-label">${formatNumber(maxValue)}</text>
      <text x="${width - padX}" y="${height - 6}" class="admin-daily-label admin-daily-label-end">${escapeHtml(String(last.date || ""))}</text>
    </svg>
  `;
  dailyStatsEl.innerHTML = `
    <span>Views <strong>${formatNumber(last.views)}</strong></span>
    <span>Opens <strong>${formatNumber(last.opens)}</strong></span>
    <span>Open rate <strong>${formatRate(last.open_rate)}</strong></span>
    <span>Shares <strong>${formatNumber(last.shares)}</strong></span>
    <span>Saves <strong>${formatNumber(last.saves)}</strong></span>
  `;
}

async function loadDailyMetrics() {
  syncButtons();
  if (dailyChartEl) dailyChartEl.innerHTML = '<div class="admin-daily-empty">Loading daily metrics...</div>';
  const response = await fetch(
    `/api/admin/metrics/daily?days=${encodeURIComponent(activeDailyRange)}&audience=${encodeURIComponent(activeAudience)}`,
    { credentials: "same-origin" },
  );
  if (response.status === 401) {
    window.location.href = "/admin/login";
    return;
  }
  const data = await response.json();
  renderDailyMetrics(Array.isArray(data?.rows) ? data.rows : []);
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
  renderTotals(data?.totals || {}, data || {});
  renderRows(Array.isArray(data?.top_cards) ? data.top_cards : []);
  await loadDailyMetrics();
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
  dailyRangeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const next = Number(button.dataset.dailyRange || 7) || 7;
      if (next === activeDailyRange) return;
      activeDailyRange = next;
      void loadDailyMetrics();
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
