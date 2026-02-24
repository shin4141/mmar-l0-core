import json, os, re, subprocess, sys
from pathlib import Path

OUTDIR = Path("examples/raw_local")
OUTDIR.mkdir(parents=True, exist_ok=True)

BAD = [
    r"^\s*pbpaste\b",
    r"paste_to_raw_local\.py",
    r"ingest_triplet_from_clipboard\.py",
    r"--label\s+",
    r"\bpython\s+-c\b",
]
MIN_CHARS = 120
MAX_CHARS = 2_000_000

def get_clipboard() -> str:
    t = subprocess.check_output(["pbpaste"]).decode("utf-8", errors="replace")
    return t.replace("\r\n","\n").replace("\r","\n")

def guard(t: str):
    if len(t.strip()) < MIN_CHARS:
        raise SystemExit(f"[ERR] clipboard too short (<{MIN_CHARS}). Copy the AI answer BODY, not a command.")
    if len(t) > MAX_CHARS:
        raise SystemExit(f"[ERR] clipboard too large ({len(t)} chars). Probably a log/export, not an answer.")
    if any(re.search(p, t) for p in BAD):
        head = t[:180].replace("\n"," ")
        raise SystemExit(f"[ERR] clipboard looks like a terminal command. HEAD: {head}")

def save(label: str, t: str):
    p = OUTDIR / f"{label}.json"
    p.write_text(json.dumps({"text": t}, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] wrote {p} chars={len(t)} HEAD={t[:120].replace('\\n',' ')}")

def main():
    # リセット（誤爆を毎回消す）
    for k in ["openai","gemini","claude"]:
        p = OUTDIR / f"{k}.json"
        if p.exists(): p.unlink()

    steps = [("openai","OpenAI(GPT)"), ("gemini","Gemini"), ("claude","Claude")]

    print("MMAR ingest: 1 command flow")
    print("For each step: copy the AI answer BODY -> come back -> press Enter.")
    print("----")

    for key, name in steps:
        input(f"[{name}] Copy answer BODY then press Enter here: ")
        t = get_clipboard()
        guard(t)
        save(key, t)

    outp = Path("examples/tmp/dissent_diff_v2.claim.json")
    if outp.exists(): outp.unlink()

    cmd = [sys.executable, "core/dissent_from_raw_v2.py",
           "--raw-openai", str(OUTDIR/"openai.json"),
           "--raw-gemini", str(OUTDIR/"gemini.json"),
           "--raw-claude", str(OUTDIR/"claude.json"),
           "--out", str(outp)]
    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd)

    data = json.loads(outp.read_text(encoding="utf-8"))
    print("[DONE] wrote", outp)
    print("[STATS]", data.get("stats"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
