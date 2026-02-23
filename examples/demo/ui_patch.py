from pathlib import Path
import runpy


if __name__ == "__main__":
    script = Path(__file__).resolve().parents[2] / "tools" / "ui_patch.py"
    runpy.run_path(str(script), run_name="__main__")
