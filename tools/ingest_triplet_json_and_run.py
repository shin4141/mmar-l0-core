from __future__ import annotations
import json, sys
from pathlib import Path
import subprocess

SRC = Path("incoming/triplet.json")
OUTDIR = Path("examples/raw_local")
OUTDIR.mkdir(parents=True, exist_ok=True)

def main():
    if not SRC.exists():
        print("[MISS] incoming/triplet.json not found", file=sys.stderr)
        raise SystemExit(2)

    d = json.loads(SRC.read_text(encoding="utf-8", errors="replace"))
    for k in ("openai","gemini","claude"):
        if k not in d or not isinstance(d[k], str) or not d[k].strip():
            print(f"[MISS] triplet.json missing non-empty key: {k}", file=sys.stderr)
            raise SystemExit(2)
        (OUTDIR/f"{k}.json").write_text(json.dumps({"text": d[k]}, ensure_ascii=False), encoding="utf-8")

    subprocess.check_call([sys.executable, "tools/build_v1_linekey_from_raw_local.py"])
    subprocess.check_call([sys.executable, "tools/build_claim_v2_from_latest_v1.py", "--v1", "out_v1/dissent_diff.latest.json"])
    print("[DONE] v2 -> examples/tmp/dissent_diff_v2.claim.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
