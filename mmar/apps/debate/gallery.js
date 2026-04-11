const galleryGridEl = document.querySelector("#gallery-grid");
const galleryCountEl = document.querySelector("#gallery-count");
const galleryTitleEl = document.querySelector("#gallery-title");
const galleryCopyEl = document.querySelector("#gallery-copy");
const galleryCreateLinkEl = document.querySelector("#gallery-create-link");
const galleryRuntimeEl = document.querySelector("#gallery-runtime");
const queryParams = new URLSearchParams(window.location.search);
let currentHealthInfo = null;

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

function resolveGalleryLang(params = queryParams) {
  if (params?.has("lang")) return normalizeBattleLang(params.get("lang") || "");
  return storedBattleLang();
}

const currentLang = resolveGalleryLang(queryParams);

const GALLERY_COPY = {
  ja: {
    title: "VerdAIct",
    copy: "気になるAIバトルを選ぶ",
    action: "バトルを作る",
    badge: "AIバトル",
    count: (count) => `${count} cards`,
    empty: "AIバトルはまだありません。",
    loading: "AIバトルを読み込み中です。",
    error: "AIバトルを読み込めませんでした。",
  },
  en: {
    title: "VerdAIct",
    copy: "Pick an AI battle that grabs you",
    action: "Create a battle",
    badge: "AI Battle",
    count: (count) => `${count} cards`,
    empty: "No English AI battles yet.",
    loading: "Loading AI battles.",
    error: "Could not load AI battles.",
  },
};

function galleryCopy() {
  return GALLERY_COPY[currentLang] || GALLERY_COPY.ja;
}

function endpointUrl(path) {
  return path;
}

function shouldShowGalleryRuntime(health = currentHealthInfo) {
  void health;
  return queryParams.get("debug") === "1";
}

function renderGalleryRuntime() {
  if (!galleryRuntimeEl) return;
  const health = currentHealthInfo;
  if (!health || typeof health !== "object" || !shouldShowGalleryRuntime(health)) {
    galleryRuntimeEl.hidden = true;
    galleryRuntimeEl.textContent = "";
    return;
  }
  const parts = [
    String(health.env_tag || "").trim(),
    String(health.history_store_id || "").trim(),
    String(health.build_sha || "").trim(),
    String(health.boot_at || "").trim(),
  ].filter(Boolean);
  galleryRuntimeEl.hidden = parts.length === 0;
  galleryRuntimeEl.textContent = parts.join(" · ");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeExperienceMode(value) {
  return String(value || "").trim().toLowerCase() === "battle" ? "battle" : "debate";
}

function buildPlaceholderImage(issue = "") {
  const title = String(issue || galleryCopy().badge).trim() || galleryCopy().badge;
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
  <text x="72" y="124" fill="#8d2f21" font-size="34" font-family="Arial, Helvetica, sans-serif" font-weight="700">${escapeHtml(galleryCopy().badge)}</text>
  <foreignObject x="72" y="176" width="1056" height="360">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial, Helvetica, sans-serif;color:#23150f;font-size:56px;line-height:1.16;font-weight:800;">${escapeHtml(title)}</div>
  </foreignObject>
</svg>
  `.trim();
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function localizedViewForRecord(record) {
  if (!record || typeof record !== "object") return null;
  const views = record.localized_views;
  if (!views || typeof views !== "object" || Array.isArray(views)) return null;
  const langView = views[currentLang];
  return langView && typeof langView === "object" && !Array.isArray(langView) ? langView : null;
}

function sortRecords(records) {
  return [...records].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

function buildCardMarkup(record) {
  const localized = localizedViewForRecord(record);
  const issue = String(localized?.issue || record.topic || "").trim() || galleryCopy().badge;
  const image = String(record.source_image || "").trim() || buildPlaceholderImage(issue);
  const id = String(record.id || record.run_id || "").trim();
  if (!id) {
    return "";
  }
  const href = currentLang === "en"
    ? `/battle/${encodeURIComponent(id)}?lang=en`
    : `/battle/${encodeURIComponent(id)}`;
  return `
    <a class="gallery-card" href="${escapeHtml(href)}">
      <div class="gallery-card-media">
        <img class="gallery-card-image" src="${escapeHtml(image)}" alt="${escapeHtml(issue)}" loading="lazy" />
        <span class="gallery-card-badge">${escapeHtml(galleryCopy().badge)}</span>
      </div>
      <div class="gallery-card-copy">
        <div class="gallery-card-issue">${escapeHtml(issue)}</div>
      </div>
    </a>
  `;
}

function renderGallery(records) {
  const rawFetchedCount = Array.isArray(records) ? records.length : 0;
  const allBattleRecords = records.filter((record) =>
    normalizeExperienceMode(record?.experience_mode) === "battle"
  );
  const langMatchedRecords = allBattleRecords;
  const battleRecords = sortRecords(langMatchedRecords);
  window.__MMAR_GALLERY_DEBUG__ = {
    rawFetchedCount,
    battleFilteredCount: allBattleRecords.length,
    langFilteredCount: langMatchedRecords.length,
    currentLang,
  };
  try {
    console.info("[gallery-counts]", window.__MMAR_GALLERY_DEBUG__);
  } catch {}
  galleryCountEl.textContent = galleryCopy().count(battleRecords.length);
  if (!battleRecords.length) {
    galleryGridEl.innerHTML = `<div class="gallery-empty">${escapeHtml(galleryCopy().empty)}</div>`;
    return;
  }
  const markup = battleRecords.map((record) => {
    try {
      return buildCardMarkup(record);
    } catch {
      return "";
    }
  }).filter(Boolean);
  if (!markup.length) {
    galleryGridEl.innerHTML = `<div class="gallery-empty">${escapeHtml(galleryCopy().empty)}</div>`;
    return;
  }
  galleryGridEl.innerHTML = markup.join("");
}

async function loadGallery() {
  galleryGridEl.innerHTML = `<div class="gallery-empty">${escapeHtml(galleryCopy().loading)}</div>`;
  try {
    const response = await fetch(endpointUrl("/api/history/list"), { method: "GET" });
    const data = await response.json();
    if (!response.ok || !data?.ok || !Array.isArray(data.items)) {
      throw new Error("history_list_failed");
    }
    currentHealthInfo = {
      env_tag: data.env_tag,
      history_store_id: data.history_store_id,
      build_sha: data.build_sha,
      boot_at: data.boot_at,
    };
    renderGalleryRuntime();
    renderGallery(data.items);
  } catch {
    renderGalleryRuntime();
    galleryGridEl.innerHTML = `<div class="gallery-empty">${escapeHtml(galleryCopy().error)}</div>`;
  }
}

function applyGalleryLanguage() {
  const copy = galleryCopy();
  if (galleryTitleEl) galleryTitleEl.textContent = copy.title;
  if (galleryCopyEl) galleryCopyEl.textContent = copy.copy;
  if (galleryCreateLinkEl) {
    galleryCreateLinkEl.textContent = copy.action;
    galleryCreateLinkEl.href = currentLang === "en"
      ? "./debate.html?mode=battle&focus=x_url&lang=en"
      : "./debate.html?mode=battle&focus=x_url";
  }
}

applyGalleryLanguage();
void loadGallery();
