import argparse
import json
from pathlib import Path
from typing import Any, List

def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="delta_entry.min.json")
    ap.add_argument("--out", required=True, help="case json for evo_gate_min")
    ap.add_argument("--repeat", type=int, default=6)
    ap.add_argument("--base", type=int, default=0)
    args = ap.parse_args()

    de = _load(Path(args.inp))
    proxy = int(de.get("delta_proxy", {}).get("resolved_count_proxy", 0))

    # Demo series: monotonic progress
    resolved_count: List[int] = [args.base + i * proxy for i in range(args.repeat)]

    payload = {
        "update_unit": "1 update = 1 delta_entry",
        "window_k": 3,
        "k_consecutive": 2,
        "theta_evo": 2,
        "resolved_count": resolved_count
    }
    _write(Path(args.out), payload)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
