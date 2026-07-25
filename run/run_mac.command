#!/usr/bin/env bash
# Double-click this file on a Mac to run the analysis.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/.venv/bin/python" "$ROOT/program/main.py"
echo ""
echo "Done. Open  data/output/Energy_Analysis_Output.xlsx"
read -n 1 -s -r -p "Press any key to close..."
