import argparse, json, os, re, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("--label", required=True, choices=["openai","gemini","claude"])
args = ap.parse_args()

# クリップボード取得（pipe不要＝誤爆減る）
t = subprocess.check_output(["pbpaste"]).decode("utf-8", errors="replace")
t = t.replace("\r\n","\n").replace("\r","\n")

if not t.strip():
    print("[ERR] clipboard empty", file=sys.stderr)
    raise SystemExit(2)

# コマンド誤爆を自動ブロック（Shinが判断しない）
bad = [
    r"^\s*pbpaste\b",
    r"paste_to_raw_local\.py",
    r"--label\s+(openai|gemini|claude)",
    r"\bpython\s+-c\b",
    r"\bjson\.dump\b",
]
if any(re.search(p, t) for p in bad):
    print("[ERR] clipboard looks like a terminal command. Copy the AI answer text (not the command).", file=sys.stderr)
    print("HEAD:", t[:180].replace("\n"," "), file=sys.stderr)
    raise SystemExit(2)

# サイズ誤爆もブロック（巨大ログを掴んだ時用）
MAX_CHARS = 2_000_000
if len(t) > MAX_CHARS:
    print(f"[ERR] clipboard too large ({len(t)} chars). Probably not an answer text.", file=sys.stderr)
    print("HEAD:", t[:180].replace("\n"," "), file=sys.stderr)
    raise SystemExit(2)

os.makedirs("examples/raw_local", exist_ok=True)
outp = f"examples/raw_local/{args.label}.json"
with open(outp, "w", encoding="utf-8") as f:
    json.dump({"text": t}, f, ensure_ascii=False)

print(f"[OK] wrote {outp} chars={len(t)}")
print("HEAD:", t[:180].replace("\n"," "))
