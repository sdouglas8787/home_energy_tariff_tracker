"""First-time setup: create a local virtual environment and install dependencies.

Run once, before the first analysis. After this, use run_mac / run_windows.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    if not VENV.exists():
        run([sys.executable, "-m", "venv", str(VENV)])
    python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    print("\nSetup complete. To run the analysis, double-click run/run_mac or run/run_windows.")


if __name__ == "__main__":
    raise SystemExit(main())
