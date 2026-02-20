from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime, timezone

RESOLVED = {"resolved","accepted","rejected"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--key", required=True, help="dissent key to resolve (e.g. output_text)")
    ap.add_argument("--status", required=True, choices=["resolved","accepted","rejected","pending","unknown","needs-evidence"])
    ap.add_argument("--by", default="human")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    p = Path(args.inp)
    d = json.loads(p.read_text(encoding="utf-8"))
    items = d.get("dissent_diff", [])
    hit = 0
    for it in items:
        if isinstance(it, dict) and it.get("key") == args.key:
            it["resolution"] = {
                "status": args.status,
                "by": args.by,
                "note": args.note,
                "at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
            }
            hit += 1

    # recompute resolved_count from dissent_diff
    d["resolved_count"] = sum(
        1 for it in items
        if isinstance(it, dict) and it.get("resolution", {}).get("status") in RESOLVED
    )

    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"updated: {p} (resolved_count={d['resolved_count']}, hits={hit})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
