import json
import subprocess
from pathlib import Path

def run(cmd: str):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    assert r.returncode == 0, (r.stderr + "\n" + r.stdout)
    return r.stdout

def test_3ai_raw_to_gate_cycle(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    (raw_dir / "openai.json").write_text(
        json.dumps({"meta":{"source":"openai","captured_at":"2026-02-21T00:00:00Z"},"raw":{"text":"A"}}),
        encoding="utf-8",
    )
    (raw_dir / "gemini.json").write_text(
        json.dumps({"meta":{"source":"gemini","captured_at":"2026-02-21T00:00:00Z"},"raw":{"text":"B"}}),
        encoding="utf-8",
    )
    (raw_dir / "claude.json").write_text(
        json.dumps({"meta":{"source":"claude","captured_at":"2026-02-21T00:00:00Z"},"raw":{"text":"A"}}),
        encoding="utf-8",
    )

    before = tmp_path / "before.json"
    after  = tmp_path / "after.json"
    before.write_text('{"x":1}', encoding="utf-8")
    after.write_text('{"x":2}', encoding="utf-8")

    log = tmp_path / "log.jsonl"
    case = tmp_path / "case.json"
    out  = tmp_path / "out.json"
    delta_out = tmp_path / "delta.json"

    run(
        f'python3 core/compare_pipeline_min.py '
        f'--before {before} --after {after} --log {log} --case {case} --out {out} '
        f'--delta-out {delta_out} --mode cumulative '
        f'--raw-openai {raw_dir/"openai.json"} --raw-gemini {raw_dir/"gemini.json"} --raw-claude {raw_dir/"claude.json"}'
    )

    d = json.loads(delta_out.read_text(encoding="utf-8"))
    assert len(d.get("dissent_diff", [])) >= 1
    assert d.get("resolved_count") == 0

    run(f'python3 tools/resolve_dissent.py --in {delta_out} --key output_text --status resolved --by test --note t')
    d2 = json.loads(delta_out.read_text(encoding="utf-8"))
    assert d2.get("resolved_count") == 1

    case2 = tmp_path / "case2.json"
    out2  = tmp_path / "out2.json"
    run(f'python3 core/delta_entry_to_updates_min.py --in {delta_out} --out {case2} --repeat 6 --base 0')
    run(f'python3 core/evo_gate_min.py --in {case2} --out {out2}')
    o = json.loads(out2.read_text(encoding="utf-8"))
    assert o.get("trigger") is True
