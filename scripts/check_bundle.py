"""Run the packaged GUI without showing it, then check the machine-readable result."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.version import VERSION


def main():
    root = Path(sys.argv[1]).resolve()
    binary = (root / "AIGCTool.app/Contents/MacOS/AIGCTool" if sys.platform == "darwin"
              else root / "AIGCTool/AIGCTool.exe")
    report = root / "smoke-report.json"
    if report.exists():
        raise RuntimeError("Smoke report already exists; refusing a stale result")
    subprocess.run([str(binary), "--smoke-test", str(report)], check=True, timeout=45,
                   creationflags=0x08000000 if sys.platform == "win32" else 0)
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data == {"version": VERSION, "tabs": 5, "drag_and_drop": True, "status": "ok"}, data
    print(json.dumps(data))


if __name__ == "__main__":
    main()
