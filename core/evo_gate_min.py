import argparse
import json
from pathlib import Path

"""
ΔRproxy per update (=1 delta_entry) as Δresolved_count; compare to theta_evo via
rolling sum over window_k updates; trigger when pass holds for k_consecutive windows.
"""

def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _compute_case(case: dict) -> dict:
    update_unit = case["update_unit"]
    window_k = int(case["window_k"])
    k_consecutive = int(case["k_consecutive"])
    theta_evo = float(case["theta_evo"])
    resolved = case["resolved_count"]

    deltas = []
    series = []
    consecutive = 0
    max_consecutive = 0
    pass_indices = []
    first_trigger_index = None

    for i, val in enumerate(resolved):
        delta = 0 if i == 0 else (val - resolved[i - 1])
        deltas.append(delta)

        start = max(0, i - window_k + 1)
        window_sum = float(sum(deltas[start : i + 1]))
        passed = window_sum >= theta_evo

        if passed:
            consecutive += 1
            pass_indices.append(i)
            if consecutive >= k_consecutive and first_trigger_index is None:
                first_trigger_index = i
        else:
            consecutive = 0

        max_consecutive = max(max_consecutive, consecutive)
        series.append(
            {
                "i": i,
                "resolved_count": val,
                "delta": delta,
                "window_sum": window_sum,
                "pass_i": passed,
                "consecutive_passes": consecutive,
            }
        )

    trigger = max_consecutive >= k_consecutive
    return {
        "case_id": case.get("case_id"),
        "update_unit": update_unit,
        "window_k": window_k,
        "k_consecutive": k_consecutive,
        "theta_evo": theta_evo,
        "series": series,
        "trigger": trigger,
        "evidence": {
            "resolved_count": resolved,
            "deltas": deltas,
            "pass_indices": pass_indices,
            "max_consecutive_passes": max_consecutive,
            "first_trigger_index": first_trigger_index,
        },
    }


def run(inp: dict) -> dict:
    if "cases" in inp:
        return {"results": [_compute_case(case) for case in inp["cases"]]}
    return _compute_case(inp)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="path to evo gate input json")
    ap.add_argument("--out", dest="outp", required=True, help="path to evo gate output json")
    args = ap.parse_args()

    out = run(_load_json(Path(args.inp)))
    _save_json(Path(args.outp), out)
    print(f"[evo_gate_min] wrote -> {args.outp}")
