import json
import subprocess
import sys

def test_dissent_v2_smoke(tmp_path):
    raw_o = tmp_path / "openai.json"
    raw_g = tmp_path / "gemini.json"
    raw_c = tmp_path / "claude.json"
    outp  = tmp_path / "out.json"

    raw_o.write_text(json.dumps({"text": "A. Cats are good.\n\nB. Safety matters."}), encoding="utf-8")
    raw_g.write_text(json.dumps({"content": "Cats are great. Safety matters a lot."}), encoding="utf-8")
    raw_c.write_text(json.dumps({"message": "Cats are good.\nSafety matters."}), encoding="utf-8")

    cmd = [
        sys.executable, "core/dissent_from_raw_v2.py",
        "--raw-openai", str(raw_o),
        "--raw-gemini", str(raw_g),
        "--raw-claude", str(raw_c),
        "--out", str(outp),
    ]
    subprocess.check_call(cmd)

    data = json.loads(outp.read_text(encoding="utf-8"))
    assert data["schema"] == "mmar.dissent_diff.v2"
    assert data["key_type"] == "claim"
    assert "claims" in data and len(data["claims"]) >= 1
    assert data["claims"][0]["claim_id"].startswith("claim_")
    assert set(data["claims"][0]["texts"].keys()) == {"openai", "gemini", "claude"}
