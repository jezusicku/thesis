#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec python -m pip install --upgrade pip
exec python -m pip install --isolated -r requirements.txt
