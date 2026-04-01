const TOPIC = "本日SORAが撤退というニュースが出てきたけど。GPTは動画サービスに手を出すべきでなかった。";

const runButton = document.getElementById("run-button");
const copyButton = document.getElementById("copy-button");
const statusEl = document.getElementById("status");
const errorEl = document.getElementById("error");
const outputEl = document.getElementById("output");

let latestRenderedText = "";

function resetOutput() {
  latestRenderedText = "";
  copyButton.disabled = true;
  outputEl.className = "output-grid empty";
  outputEl.innerHTML = '<div class="empty-state">Run Debate を押すと、Turn1 から Turn3 まで表示します。</div>';
  errorEl.hidden = true;
}

function setRunningState() {
  latestRenderedText = "";
  copyButton.disabled = true;
  statusEl.textContent = "Running...";
  statusEl.className = "status running";
  errorEl.hidden = true;
  outputEl.className = "output-grid empty";
  outputEl.innerHTML = '<div class="empty-state">Running...</div>';
}

function setFailureState() {
  statusEl.textContent = "Failed";
  statusEl.className = "status";
  errorEl.hidden = false;
  outputEl.className = "output-grid empty";
  outputEl.innerHTML = '<div class="empty-state">Preview failed.</div>';
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderDebate(turns) {
  outputEl.className = "output-grid";
  outputEl.innerHTML = turns
    .map((turn) => {
      const turnNumber = Number(turn.turn || 0);
      return `
        <section class="turn-row" aria-label="Turn ${turnNumber}">
          <article class="turn-card">
            <div class="turn-head">
              <div class="turn-label">Turn ${turnNumber}</div>
              <div class="side-name">Side A</div>
            </div>
            <p class="turn-text">${escapeHtml(turn.a || "")}</p>
          </article>
          <article class="turn-card">
            <div class="turn-head">
              <div class="turn-label">Turn ${turnNumber}</div>
              <div class="side-name">Side B</div>
            </div>
            <p class="turn-text">${escapeHtml(turn.b || "")}</p>
          </article>
        </section>
      `;
    })
    .join("");

  latestRenderedText = turns
    .map((turn) => `Turn ${turn.turn}\nSide A: ${turn.a}\nSide B: ${turn.b}`)
    .join("\n\n");
  copyButton.disabled = latestRenderedText.length === 0;
}

async function runDebate() {
  setRunningState();

  try {
    const response = await fetch("/api/debate_v4", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: TOPIC }),
    });

    const payload = await response.json();
    const turns = payload?.debate?.turns;

    if (!response.ok || !Array.isArray(turns) || turns.length !== 3) {
      throw new Error("preview_failed");
    }

    renderDebate(turns);
    statusEl.textContent = "Done";
    statusEl.className = "status done";
  } catch (error) {
    console.error(error);
    setFailureState();
  }
}

async function copyDebate() {
  if (!latestRenderedText) {
    return;
  }
  try {
    await navigator.clipboard.writeText(latestRenderedText);
    statusEl.textContent = "Copied";
    statusEl.className = "status done";
  } catch (error) {
    console.error(error);
  }
}

runButton.addEventListener("click", runDebate);
copyButton.addEventListener("click", copyDebate);
resetOutput();
