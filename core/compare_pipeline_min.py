import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Minimal pipeline:
# before/after -> diff -> delta_entry -> append log(jsonl) -> case -> evo_gate

def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def _write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _is_primitive(x):
    return x is None or isinstance(x, (str, int, float, bool))

def _path_join(base: str, key: str) -> str:
    if base == "":
        return key
    if key.startswith("["):
        return f"{base}{key}"
    return f"{base}.{key}"

def _diff(a, b, p, out):
    if a == b:
        return
    if _is_primitive(a) or _is_primitive(b) or type(a) != type(b):
        out.append({"path": p or "$", "op": "change", "before": a, "after": b})
        return
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
    out.append({"path": p or "$", "op": "change", "before": a, "after": b})

def _resolved_proxy(changes):
    # Minimal proxy for now: count add/change
    return sum(1 for x in changes if x.get("op") in ("add", "change"))

def _read_jsonl(path: Path):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        out.append(json.loads(ln))
    return out

def _append_jsonl(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def _make_case_from_log(log_entries, window_k, k_consecutive, theta_evo, mode="cumulative"):
    proxies = [int(e.get("delta_proxy", {}).get("resolved_count_proxy", 0)) for e in log_entries]
    if mode == "cumulative":
        resolved = []
        total = 0
        for p in proxies:
            total += p
            resolved.append(total)
    else:
        resolved = proxies[:]
    return {
        "update_unit": "1 update = 1 delta_entry",
        "window_k": window_k,
        "k_consecutive": k_consecutive,
        "theta_evo": float(theta_evo),
        "resolved_count": resolved,
        "evidence": {"entries": len(log_entries), "proxies": proxies, "mode": mode},
    }

def _evo_gate(case):
    # Implements the same logic as evo_gate_min.py (input shape: resolved_count list)
    resolved = case["resolved_count"]
    window_k = int(case["window_k"])
    k_consecutive = int(case["k_consecutive"])
    theta_evo = float(case["theta_evo"])

    deltas = []
    max_consecutive = 0
    consecutive = 0
    first_trigger_index = None
    pass_indices = []

    series = []
    for i, rc in enumerate(resolved):
        delta = 0 if i == 0 else rc - resolved[i - 1]
        deltas.append(delta)
        start = max(0, i - window_k + 1)
        window_sum = float(sum(deltas[start:i + 1]))
        passed = window_sum >= theta_evo
        if passed:
            consecutive += 1
            pass_indices.append(i)
            if consecutive > max_consecutive:
                max_consecutive = consecutive
            if consecutive >= k_consecutive and first_trigger_index is None:
                first_trigger_index = i
        else:
            consecutive = 0

        series.append({
            "i": i,
            "resolved_count": rc,
            "delta": delta,
            "window_sum": window_sum,
            "pass_i": bool(passed),
            "consecutive_passes": consecutive
        })

    trigger = max_consecutive >= k_consecutive
    return {
        "case_id": case.get("case_id"),
        "update_unit": case.get("update_unit"),
        "window_k": window_k,
        "k_consecutive": k_consecutive,
        "theta_evo": theta_evo,
        "series": series,
        "trigger": bool(trigger),
        "evidence": {
            "resolved_count": resolved,
            "deltas": deltas,
            "pass_indices": pass_indices,
            "max_consecutive_passes": max_consecutive,
            "first_trigger_index": first_trigger_index
        }
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--window-k", type=int, default=3)
    ap.add_argument("--k-consecutive", type=int, default=2)
    ap.add_argument("--theta-evo", type=float, default=2.0)
    ap.add_argument("--mode", choices=["cumulative", "per_update"], default="cumulative")
    ap.add_argument("--delta-out", default="out_delta/delta_entry.min.json")
    args = ap.parse_args()

    before = _load_json(Path(args.before))
    after = _load_json(Path(args.after))

    changes = []
    _diff(before, after, "", changes)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    delta_entry = {
        "case_id": f"delta_from:{Path(args.before).name}->{Path(args.after).name}",
        "asof_utc": now,
        "update_unit": "1 update = 1 delta_entry",
        "delta_proxy": {
            "name": "ΔRproxy",
            "definition": "count(add/change) over JSON diff changes[] (minimal proxy)",
            "resolved_count_proxy": _resolved_proxy(changes),
        },
        "inputs": {"before": args.before, "after": args.after},
        "delta_items": changes,
        "evidence": [],
    }

    # write delta_entry snapshot
    _write_json(Path(args.delta_out), delta_entry)

    # append to log
    _append_jsonl(Path(args.log), delta_entry)

    # build case from log and write
    entries = _read_jsonl(Path(args.log))
    case = _make_case_from_log(entries, args.window_k, args.k_consecutive, args.theta_evo, mode=args.mode)
    _write_json(Path(args.case), case)

    # run evo gate and write
    out = _evo_gate(case)
    _write_json(Path(args.out), out)

    print(f"Wrote delta_entry: {args.delta_out}")
    print(f"Appended log: {args.log} (entries={len(entries)})")
    print(f"Wrote case: {args.case}")
    print(f"Wrote gate out: {args.out} (trigger={out['trigger']})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
