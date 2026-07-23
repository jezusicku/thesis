#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
if [[ ! -x .venv/bin/python3 ]]; then
  echo "Brak .venv — uruchom najpierw: ./setup_venv.sh"
  exit 1
fi
exec .venv/bin/python3 -m streamlit run annotation_app.py
