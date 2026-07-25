#!/usr/bin/env bash
# Double-click this ONCE on a Mac before the first run.
set -e
cd "$(dirname "$0")"
python3 setup_first_time.py
read -n 1 -s -r -p "Press any key to close..."
