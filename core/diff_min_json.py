import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def _is_primitive(x: Any) -> bool:
    return x is None or isinstance(x, (str, int, float, bool))

def _path_join(base: str, key: str) -> str:
    if base == "":
        return key
    if key.startswith("["):
        return f"{base}{key}"
    return f"{base}.{key}"

def _diff(a: Any, b: Any, p: str, out: List[Dict[str, Any]]) -> None:
    if a == b:
        return

    # Type change or primitive change
    if _is_primitive(a) or _is_primitive(b) or type(a) != type(b):
        out.append({"path": p or "$", "op": "change", "before": a, "after": b})
        return

    # Dict diff
    if isinstance(a, dict) and isinstance(b, dict):
        a_keys = set(a.keys())
        b_keys = set(b.keys())
        for k in sorted(a_keys - b_keys):
            out.append({"path": _path_join(p, k), "op": "remove", "before": a.get(k), "after": None})
        for k in sorted(b_keys - a_keys):
            out.append({"path": _path_join(p, k), "op": "add", "before": None, "after": b.get(k)})
        for k in sorted(a_keys & b_keys):
            _diff(a[k], b[k], _path_join(p, k), out)
        return

    # List diff (minimal: compare by index)
    if isinstance(a, list) and isinstance(b, list):
        max_len = max(len(a), len(b))
        for i in range(max_len):
            idx = f"[{i}]"
            if i >= len(a):
                out.append({"path": _path_join(p, idx), "op": "add", "before": None, "after": b[i]})
            elif i >= len(b):
                out.append({"path": _path_join(p, idx), "op": "remove", "before": a[i], "after": None})
            else:
                _diff(a[i], b[i], _path_join(p, idx), out)
        return

    # Fallback
    out.append({"path": p or "$", "op": "change", "before": a, "after": b})

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    before = _load(Path(args.before))
    after = _load(Path(args.after))

    changes: List[Dict[str, Any]] = []
    _diff(before, after, "", changes)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "before": str(args.before),
        "after": str(args.after),
        "change_count": len(changes),
        "changes": changes,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
