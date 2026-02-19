import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        out.append(json.loads(ln))
    return out

def _resolved_proxy(entry: Dict[str, Any]) -> int:
    # Current minimal proxy (still provisional): use resolved_count_proxy if present.
    return int(entry.get("delta_proxy", {}).get("resolved_count_proxy", 0))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, help="logs/delta_entries.jsonl")
    ap.add_argument("--out", required=True, help="out_gate/case.from_log.json")
    ap.add_argument("--window-k", type=int, default=3)
    ap.add_argument("--k-consecutive", type=int, default=2)
    ap.add_argument("--theta-evo", type=float, default=2.0)
    ap.add_argument("--mode", choices=["cumulative", "per_update"], default="cumulative",
                    help="cumulative: resolved_count is running total; per_update: raw proxy per entry")
    args = ap.parse_args()

    entries = _read_jsonl(Path(args.log))
    proxies = [_resolved_proxy(e) for e in entries]

    if args.mode == "cumulative":
        resolved_count: List[int] = []
        total = 0
        for p in proxies:
            total += p
            resolved_count.append(total)
    else:
        resolved_count = proxies[:]  # raw per update

    payload = {
        "update_unit": "1 update = 1 delta_entry",
        "window_k": args.window_k,
        "k_consecutive": args.k_consecutive,
        "theta_evo": args.theta_evo,
        "resolved_count": resolved_count,
        "evidence": {
            "log": str(args.log),
            "entries": len(entries),
            "proxies": proxies,
            "mode": args.mode
        }
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
