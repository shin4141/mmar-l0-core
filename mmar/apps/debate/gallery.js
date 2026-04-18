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
    missingTitle: "English preview not ready yet",
    missingExcerpt: "Open the card to view details.",
  },
};

function galleryCopy() {
  return GALLERY_COPY[currentLang] || GALLERY_COPY.ja;
}

function endpointUrl(path) {
  return path;
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

function englishViewReady(record, localized) {
  if (currentLang !== "en") return false;
  if (!localized || typeof localized !== "object") return false;
  const status = String(localized.status || record?.localized_en_status || "").trim().toLowerCase();
  const viewHash = String(localized.source_hash || "").trim();
  const recordHash = String(record?.localized_en_source_hash || "").trim();
  const viewVersion = String(localized.generator_version || "").trim();
  const recordVersion = String(record?.localized_en_generator_version || "").trim();
  return (
    status === "ready"
    && (!recordHash || !viewHash || recordHash === viewHash)
    && (!recordVersion || !viewVersion || recordVersion === viewVersion)
  );
}

function firstNonEmpty(...values) {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function xEmbedFailureLabel(errorCode) {
  if (errorCode === "x_forbidden") return "X側の制限により埋め込めません（403）";
  if (errorCode === "invalid" || errorCode === "invalid_x_post_url" || errorCode === "missing_url") return "URL無効";
  return "一時的に取得できませんでした";
}

function xEmbedStateForRecord(record) {
  if (!record || typeof record !== "object") return null;
  const currentSourceUrl = String(record.source_url || "").trim();
  const savedSourceUrl = String(record.x_embed_source_url || "").trim();
  if (!currentSourceUrl || !savedSourceUrl || currentSourceUrl !== savedSourceUrl) return null;
  const status = String(record.x_embed_status || "").trim();
  if (!status) return null;
  if (status === "success") {
    const html = String(record.x_embed_html || "").trim();
    if (!html || !html.includes("twitter-tweet")) return null;
    return { status, html };
  }
  return {
    status,
    error: String(record.x_embed_error || status).trim(),
  };
}

function normalizeCompareText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[「」"'`.,!?()[\]{}:;/-]/g, "")
    .trim();
}

function extractXEmbedText(html) {
  const markup = String(html || "").trim();
  if (!markup) return "";
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(markup, "text/html");
    const blockquote = doc.querySelector("blockquote.twitter-tweet");
    const text = String(blockquote?.textContent || doc.body?.textContent || "")
      .replace(/https?:\/\/\S+/g, " ")
      .replace(/pic\.twitter\.com\/\S+/gi, " ")
      .replace(/\s+/g, " ")
      .trim();
    return text;
  } catch {
    return "";
  }
}

function sourceLinkLabel() {
  return currentLang === "en" ? "Open original" : "元URLを開く";
}

function gallerySummaryText(record, issue, localized) {
  const englishCard = currentLang === "en" ? englishCardCopy(record, localized) : null;
  const summary = currentLang === "en"
    ? firstNonEmpty(
      localized?.source_summary,
      englishCard?.ready ? englishCard.excerpt : "",
      record.source_summary,
      record.excerpt,
      record.tease,
    )
    : firstNonEmpty(
      localized?.source_summary,
      record.source_summary,
      record.excerpt,
      record.tease,
    );
  const cleanSummary = String(summary || "").trim();
  if (!cleanSummary) return "";
  const issueKey = normalizeCompareText(issue);
  const summaryKey = normalizeCompareText(cleanSummary);
  if (!summaryKey) return "";
  if (summaryKey === issueKey || summaryKey.includes(issueKey) || issueKey.includes(summaryKey)) {
    return "";
  }
  return cleanSummary;
}

function englishCardCopy(record, localized) {
  const copy = galleryCopy();
  if (!englishViewReady(record, localized)) {
    return {
      issue: copy.missingTitle,
      excerpt: copy.missingExcerpt,
      ready: false,
    };
  }
  const summary = localized.summary && typeof localized.summary === "object" ? localized.summary : {};
  const takeaway = summary.gemini_takeaway && typeof summary.gemini_takeaway === "object"
    ? summary.gemini_takeaway
    : {};
  return {
    issue: firstNonEmpty(
      localized.issue,
      summary.issue,
      summary.verdict_headline,
      copy.missingTitle,
    ),
    excerpt: firstNonEmpty(
      summary.verdict_subline,
      takeaway.structural_explanation,
      takeaway.debate_dynamic,
      summary.flip_condition,
      localized.source_summary,
      copy.missingExcerpt,
    ),
    ready: true,
  };
}

function sortRecords(records) {
  return [...records].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

function buildCardMarkup(record) {
  const localized = localizedViewForRecord(record);
  const xEmbed = xEmbedStateForRecord(record);
  const copy = galleryCopy();
  const englishCard = currentLang === "en" ? englishCardCopy(record, localized) : null;
  const issue = currentLang === "en"
    ? englishCard.issue
    : (String(localized?.issue || record.topic || "").trim() || copy.badge);
  const excerpt = currentLang === "en"
    ? englishCard.excerpt
    : firstNonEmpty(record.excerpt, record.tease, "");
  const summary = gallerySummaryText(record, issue, localized);
  const image = String(record.source_image || "").trim() || buildPlaceholderImage(issue);
  const sourceUrl = String(record.source_url || "").trim();
  const xEmbedText = xEmbed?.status === "success" ? extractXEmbedText(xEmbed.html) : "";
  const id = String(record.id || record.run_id || "").trim();
  if (!id) {
    return "";
  }
  const href = currentLang === "en"
    ? `/battle/${encodeURIComponent(id)}?lang=en`
    : `/battle/${encodeURIComponent(id)}`;
  const mediaMarkup = xEmbed?.status === "success"
    ? (
      String(record.source_image || "").trim()
        ? `
          <div class="gallery-card-media gallery-card-media-fixed">
            <img class="gallery-card-image" src="${escapeHtml(String(record.source_image || "").trim())}" alt="${escapeHtml(issue)}" loading="lazy" />
            <span class="gallery-card-badge">${escapeHtml(galleryCopy().badge)}</span>
          </div>
        `
        : `
          <div class="gallery-card-media gallery-card-media-fixed gallery-card-media-textonly">
            <span class="gallery-card-badge">${escapeHtml(galleryCopy().badge)}</span>
            <div class="gallery-x-media-faux">
              <div class="gallery-x-media-mark">X POST</div>
              <div class="gallery-x-media-text">${escapeHtml(xEmbedText || issue)}</div>
            </div>
          </div>
        `
    )
    : xEmbed
      ? `
        <div class="gallery-card-media gallery-card-media-fixed gallery-card-media-fallback">
          <span class="gallery-card-badge">${escapeHtml(galleryCopy().badge)}</span>
          <div class="gallery-x-media-fallback">${escapeHtml(xEmbedFailureLabel(xEmbed.error || xEmbed.status))}</div>
        </div>
      `
      : `
        <div class="gallery-card-media gallery-card-media-fixed">
          <img class="gallery-card-image" src="${escapeHtml(image)}" alt="${escapeHtml(issue)}" loading="lazy" />
          <span class="gallery-card-badge">${escapeHtml(galleryCopy().badge)}</span>
        </div>
      `;
  return `
    <article class="gallery-card" data-record-id="${escapeHtml(id)}" data-href="${escapeHtml(href)}">
      ${mediaMarkup}
      <div class="gallery-card-copy">
        <a class="gallery-card-title-link" href="${escapeHtml(href)}">${escapeHtml(issue)}</a>
        ${summary ? `<div class="gallery-card-summary">${escapeHtml(summary)}</div>` : (excerpt ? `<div class="gallery-card-excerpt">${escapeHtml(excerpt)}</div>` : "")}
        ${sourceUrl ? `<a class="gallery-card-source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceLinkLabel())}</a>` : ""}
      </div>
    </article>
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
  galleryGridEl.querySelectorAll(".gallery-card[data-record-id]").forEach((card) => {
    const recordId = card.dataset.recordId || "";
    const href = card.dataset.href || "";
    const handleMetric = () => sendBattleMetric(recordId, "open");
    card.querySelectorAll(".gallery-card-title-link").forEach((link) => {
      link.addEventListener("click", handleMetric);
    });
    card.addEventListener("click", (event) => {
      if (event.target.closest("a")) return;
      if (event.target.closest(".gallery-x-embed")) return;
      if (!href) return;
      handleMetric();
      window.location.href = href;
    });
  });
}

async function loadGallery() {
  galleryGridEl.innerHTML = `<div class="gallery-empty">${escapeHtml(galleryCopy().loading)}</div>`;
  try {
    const response = await fetch(endpointUrl("/api/gallery/list"), { method: "GET" });
    const data = await response.json();
    if (!response.ok || !data?.ok || !Array.isArray(data.items)) {
      throw new Error("gallery_list_failed");
    }
    currentHealthInfo = {
      env_tag: data.env_tag,
      history_store_id: data.gallery_store_id || data.history_store_id,
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
