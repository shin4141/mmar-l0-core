from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _demo_dir(root: Path) -> Path:
    return root / "examples" / "demo"


def _target_file(root: Path) -> Path:
    return _demo_dir(root) / "index.html"


def _backup_dir(root: Path) -> Path:
    return _demo_dir(root) / "_bak"


def _canonical_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>MMAR Demo</title>
  <style>
    :root{
      --bg:#f6f7f9; --card:#ffffff; --text:#0F172A; --muted:#64748B;
      --line:#e6e8ee; --accent:rgba(56,189,248,.75); --accentSoft:rgba(56,189,248,.12);
      --shadow:0 10px 26px rgba(16,24,40,.08);
      --r:16px;
    }
    *{ box-sizing:border-box; }
    body{ margin:0; font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial;
          color:var(--text); background:var(--bg); }
    .wrap{ display:grid; grid-template-columns: 1fr 2fr; gap:16px; padding:16px; height:100vh; }
    .card{ background:var(--card); border:1px solid var(--line); border-radius:var(--r);
           padding:14px; display:flex; flex-direction:column; min-height:0; box-shadow:var(--shadow); }
    .muted{ color:var(--muted); font-size:12px; }
    .row{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    .pill{ border:1px solid var(--line); border-radius:999px; padding:4px 10px; font-size:12px; background:#fff; }
    textarea{ width:100%; min-height:160px; resize:vertical; border:1px solid var(--line);
              border-radius:12px; padding:10px; font-size:14px; outline:none; }
    textarea:focus{ border-color:var(--accent); box-shadow:0 0 0 4px var(--accentSoft); }
    textarea.big{ min-height:55vh; }

    .tabs{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
    button{ border:1px solid var(--line); background:#fff; border-radius:999px; padding:8px 12px;
            cursor:pointer; font-weight:700; }
    button.active{ border-color:var(--accent); box-shadow:0 0 0 4px var(--accentSoft); color:#0284C7; }
    pre{ margin:0; white-space:pre-wrap; word-break:break-word; overflow:auto; flex:1; font-size:13px; line-height:1.45; }
    .subpre{ margin:0; white-space:pre-wrap; word-break:break-word; overflow:auto; font-size:13px; line-height:1.45; }

    .counter{ margin-left:auto; font-size:12px; color:var(--muted); font-weight:700; }
    .counter.warn{ color:#c2410c; }

    details{ border:1px solid var(--line); border-radius:14px; padding:10px 12px; background:#fff; }
    summary{ cursor:pointer; font-weight:800; list-style:none; }
    summary::-webkit-details-marker{ display:none; }
    .small{ color:var(--muted); font-size:12px; margin-left:8px; font-weight:700; }
    .preview{ margin-top:8px; }
    .deltaBox{ background: rgba(56,189,248,.08); border:1px solid rgba(56,189,248,.25); }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="row">
        <div class="pill">MMAR demo</div>
        <div id="ts" class="muted"></div>
      </div>
      <p class="muted" style="margin:10px 0 6px;">Input (static demo). Output files are loaded from this folder.</p>
      <textarea id="q" placeholder="Question (for display only)"></textarea>
      <div class="row" style="margin-top:10px;">
        <button id="reload">Reload files</button>
        <span class="muted">Default view is Compare.</span>
        <span id="counter" class="counter"></span>
      </div>
      <p class="muted" style="margin-top:10px;">
        Files expected:
        <br>out_compare.txt / out_expand.txt / out_diff.txt / out_merge.txt
      </p>
    </div>

    <div class="card">
      <div class="tabs" id="tabs"></div>
      <div id="out">Loading…</div>
      <div class="muted" style="margin-top:8px;">
        If content doesn't load on GitHub Pages immediately, wait a bit or hard-reload.
      </div>
    </div>
  </div>

<script>
  const TAB_SPEC = [
    { key: "compare", label: "Compare", file: "out_compare.txt" },
    { key: "expand",  label: "Expand",  file: "out_expand.txt"  },
    { key: "diff",    label: "Diff",    file: "out_diff.txt"    },
    { key: "merge",   label: "Merge",   file: "out_merge.txt"   },
  ];

  const tabsEl = document.getElementById("tabs");
  const outEl  = document.getElementById("out");
  const qEl    = document.getElementById("q");
  const tsEl   = document.getElementById("ts");
  const LIMIT = 600;
  const PREVIEW_LINES_MAIN = 7;
  const PREVIEW_LINES_DELTA = 3;
  const counterEl = document.getElementById("counter");

  function updateCounter(){
    const used = (qEl.value || "").length;
    const left = LIMIT - used;
    counterEl.textContent = `Remaining: ${left}`;
    counterEl.className = "counter" + (left < 0 ? " warn" : "");
  }
  qEl.addEventListener("input", updateCounter);
  qEl.addEventListener("focus", () => qEl.classList.add("big"));
  qEl.addEventListener("blur", () => qEl.classList.remove("big"));
  updateCounter();

  let active = "compare";
  function setTimestamp(){ tsEl.textContent = new Date().toISOString(); }

  function renderTabs(){
    tabsEl.innerHTML = "";
    for (const t of TAB_SPEC){
      const b = document.createElement("button");
      b.textContent = t.label;
      b.className = (t.key === active) ? "active" : "";
      b.onclick = () => { active = t.key; renderTabs(); loadActive(); };
      tabsEl.appendChild(b);
    }
  }

  async function fetchText(file){
    const url = `${file}?_=${Date.now()}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${file}: HTTP ${r.status}`);
    return await r.text();
  }

  function escapeHtml(s){
    return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function section(txt, head, nextHead){
    const re = new RegExp(`=== ${head} ===\\\\s*([\\\\s\\\\S]*?)(?=\\\\n=== ${nextHead} ===|$)`);
    const m = txt.match(re);
    return (m && m[1]) ? m[1].trim() : "";
  }

  function clipLines(text, maxLines){
    const raw = (text || "(empty)").replace(/\\r\\n/g, "\\n");
    const lines = raw.split("\\n");
    const clipped = lines.slice(0, maxLines).join("\\n");
    const truncated = lines.length > maxLines;
    return {
      preview: truncated ? `${clipped}\\n...` : clipped,
      total: lines.length,
      clippedTo: maxLines
    };
  }

  function detailsBlock(title, fullText, previewLines, extraClass=""){
    const info = clipLines(fullText, previewLines);
    const meta = `<span class="small">(${info.total} lines, preview ${info.clippedTo})</span>`;
    return `
      <details class="${extraClass}" open>
        <summary>${title} ${meta}</summary>
        <div class="preview"><pre class="subpre">${escapeHtml(info.preview)}</pre></div>
      </details>
    `;
  }

  async function loadActive(){
    const spec = TAB_SPEC.find(x => x.key === active);
    outEl.textContent = "Loading…";
    try{
      const txt = await fetchText(spec.file);
      setTimestamp();

      if (active === "compare"){
        const input  = section(txt, "INPUT", "SINGLE \\\\(seed\\\\)");
        const before = section(txt, "SINGLE \\\\(seed\\\\)", "MMAR EXPAND \\\\(tab output\\\\)");
        const after  = section(txt, "MMAR EXPAND \\\\(tab output\\\\)", "DIFF \\\\(head\\\\)");
        const delta  = section(txt, "DIFF \\\\(head\\\\)", "$");
        if (input) qEl.value = input;
        updateCounter();

        outEl.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:12px;">
            ${detailsBlock("Before (Single)", before, PREVIEW_LINES_MAIN)}
            ${detailsBlock("After (MMAR)", after, PREVIEW_LINES_MAIN)}
            ${detailsBlock("Δ (Diff)", delta, PREVIEW_LINES_DELTA, "deltaBox")}
          </div>
        `;
      } else {
        outEl.innerHTML = `<pre class="subpre">${escapeHtml(txt.trim() ? txt : "(empty)")}</pre>`;
      }
    } catch(e){
      outEl.textContent = `Failed to load ${spec.file}\\n\\n${e}`;
    }
  }

  document.getElementById("reload").onclick = loadActive;
  renderTabs();
  loadActive();
</script>
</body>
</html>
"""


def _check_state(text: str) -> list[str]:
    checks = [
        ("水色テーマ(accent=56,189,248)", bool(re.search(r"56\s*,\s*189\s*,\s*248", text))),
        ("入力欄focus拡張(55vh)", "textarea.big{ min-height:55vh; }" in text),
        ("文字数カウンター(LIMIT=600/Remaining/warn)", ("const LIMIT = 600;" in text and "Remaining:" in text and "counter.warn" in text)),
        ("Compare details収納(Before/After/Δ)", ('detailsBlock("Before (Single)"' in text and 'detailsBlock("After (MMAR)"' in text and 'detailsBlock("Δ (Diff)"' in text and "<details" in text)),
        ("行数プレビュー(7/7/3)", ("const PREVIEW_LINES_MAIN = 7;" in text and "const PREVIEW_LINES_DELTA = 3;" in text and "clipLines(" in text)),
        ("初期プレビュー(open)", '<details class="${extraClass}" open>' in text),
        ("衝突マーカーなし", all(mark not in text for mark in CONFLICT_MARKERS)),
    ]
    return [f"[{'OK' if ok else 'NG'}] {name}" for name, ok in checks]


def _scan_conflicts_or_fail(root: Path) -> None:
    demo_dir = _demo_dir(root)
    paths = sorted(demo_dir.glob("*.txt")) + [demo_dir / "index.html"]
    hits: list[tuple[Path, int, str]] = []

    for p in paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in CONFLICT_MARKERS):
                hits.append((p, lineno, line.strip()))

    if hits:
        print("[FAIL] conflict markers found in demo artifacts:")
        for path, lineno, line in hits:
            print(f"  - {path}:{lineno}: {line}")
        raise SystemExit(1)

    print("[ui_patch] conflict scan: OK")


def main() -> None:
    root = _root_dir()
    target = _target_file(root)
    if not target.exists():
        raise SystemExit(f"[ERROR] target not found: {target}")

    _scan_conflicts_or_fail(root)

    before = target.read_text(encoding="utf-8")
    after = _canonical_index_html()

    print("[ui_patch] target:", target)
    print("[ui_patch] before checks:")
    for line in _check_state(before):
        print(" ", line)

    if before == after:
        print("[ui_patch] no change: already normalized")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    bak_dir = _backup_dir(root)
    bak_dir.mkdir(parents=True, exist_ok=True)
    backup = bak_dir / f"index.html.bak_{ts}"
    backup.write_text(before, encoding="utf-8")
    target.write_text(after, encoding="utf-8")

    print("[ui_patch] backup:", backup)
    print("[ui_patch] wrote normalized index.html")
    print("[ui_patch] after checks:")
    for line in _check_state(after):
        print(" ", line)


if __name__ == "__main__":
    main()
