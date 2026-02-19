import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _resolved_proxy(changes: List[Dict[str, Any]]) -> int:
    c = 0
    for x in changes:
        if x.get("op") in ("add", "change"):
            c += 1
    return c

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-id", default=None)
    args = ap.parse_args()

    diff = _load(Path(args.inp))
    changes = diff.get("changes", [])
    before = diff.get("before")
    after = diff.get("after")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    case_id = args.case_id or f"delta_from:{Path(str(before)).name}->{Path(str(after)).name}"

    payload = {
        "case_id": case_id,
        "asof_utc": now,
        "update_unit": "1 update = 1 delta_entry",
        "delta_proxy": {
            "name": "ΔRproxy",
            "definition": "count(add/change) over JSON diff changes[] (minimal proxy)",
            "resolved_count_proxy": _resolved_proxy(changes),
        },
        "inputs": {"before": before, "after": after},
        "delta_items": changes,
        "evidence": [],
        "notes": [
            "Minimal adapter: diff.json -> delta_entry-like json",
            "Proxy definition is provisional; later align with resolved_count semantics."
        ],
    }
    _write(Path(args.out), payload)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
