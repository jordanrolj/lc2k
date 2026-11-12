#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/doctor.py --setup-only
bash scripts/build.sh "$@"
python3 scripts/doctor.py
python3 scripts/test.py --suite full
