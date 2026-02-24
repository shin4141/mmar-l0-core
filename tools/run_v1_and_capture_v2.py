from __future__ import annotations
import argparse, json, os, subprocess, sys, re
from pathlib import Path
from typing import Any, List, Dict

# --- minimal text extractor (same spirit as v2) ---
WANT_KEYS = {"text","content","message","completion","output_text","final","response"}

def collect_strings(obj: Any, out: List[str] | None = None) -> List[str]:
    if out is None: out = []
    if isinstance(obj, dict):
        for k,v in obj.items():
            if isinstance(v, str) and (k in WANT_KEYS or len(v) >= 40):
                out.append(v)
            else:
                collect_strings(v, out)
    elif isinstance(obj, list):
        for it in obj: collect_strings(it, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out

def robust_load(p: str) -> Any:
    txt = Path(p).read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
    try:
        return json.loads(txt)
    except Exception:
        # JSONL fallback
        objs = []
        ok = True
        for ln in txt.splitlines():
            ln = ln.strip()
            if not ln: continue
            try:
                objs.append(json.loads(ln))
            except Exception:
                ok = False
                break
        if ok and objs: return objs
        return {"text": txt}

def extract_text(payload: Any) -> str:
    ss = [s.strip() for s in collect_strings(payload) if isinstance(s,str) and s.strip()]
    if not ss:
        return ""
    # dedup, keep longer fragments
    seen=set(); uniq=[]
    for s in ss:
        key=re.sub(r"\s+"," ",s).strip().lower()
        if key in seen: continue
        seen.add(key); uniq.append(s)
    uniq.sort(key=len, reverse=True)
    # join top few (avoid huge)
    joined="\n".join(uniq[:8])
    return joined[:2_000_000]

def main():
    ap = argparse.ArgumentParser()
    # v1 inputs (same shape as L0)
    ap.add_argument("--raw-openai", required=True)
    ap.add_argument("--raw-gemini", required=True)
    ap.add_argument("--raw-claude", required=True)
    ap.add_argument("--out-v1", required=True)
    # optional: also run v2
    ap.add_argument("--out-v2", default="examples/tmp/dissent_diff_v2.claim.json")
    args = ap.parse_args()

    os.makedirs("logs/raw_latest", exist_ok=True)
    os.makedirs("examples/raw_local", exist_ok=True)
    os.makedirs(Path(args.out_v1).parent or ".", exist_ok=True)
    os.makedirs(Path(args.out_v2).parent or ".", exist_ok=True)

    # 1) 保存（full raw）: logs/raw_latest/
    for label, src in [("openai",args.raw_openai),("gemini",args.raw_gemini),("claude",args.raw_claude)]:
        payload = robust_load(src)
        Path(f"logs/raw_latest/{label}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        text = extract_text(payload)
        Path(f"examples/raw_local/{label}.json").write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")

    # 2) v1 実行（既存の line-key 生成を壊さない）
    # ※プロジェクト側の実体に合わせて必要ならここを差し替える
    cmd_v1 = [
        sys.executable, "core/dissent_from_raw.py",
        "--raw-openai", args.raw_openai,
        "--raw-gemini", args.raw_gemini,
        "--raw-claude", args.raw_claude,
        "--out", args.out_v1,
    ]
    subprocess.check_call(cmd_v1)

    # 3) v2 実行（claim-key）
    cmd_v2 = [
        sys.executable, "core/dissent_from_raw_v2.py",
        "--raw-openai", "examples/raw_local/openai.json",
        "--raw-gemini", "examples/raw_local/gemini.json",
        "--raw-claude", "examples/raw_local/claude.json",
        "--out", args.out_v2,
    ]
    subprocess.check_call(cmd_v2)

    data = json.loads(Path(args.out_v2).read_text(encoding="utf-8"))
    print("[DONE] v1:", args.out_v1)
    print("[DONE] v2:", args.out_v2)
    print("[STATS]", data.get("stats"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
