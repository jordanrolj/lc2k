#!/usr/bin/env bash
# Run from any directory; all generated files stay under the repository.
set -euo pipefail
LC2K_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "${LC2K_PYTHON:-python3}" "$LC2K_ROOT/scripts/build_llvm.py" "$@"
