#!/usr/bin/env bash
# Odtwarza .venv w BIEŻĄCEJ lokalizacji folderu (po przeniesieniu projektu trzeba to zrobić ponownie).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
echo "Katalog projektu: $ROOT"
rm -rf .venv
python3 -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.txt
echo ""
echo "OK. Uruchom aplikację:"
echo "  source .venv/bin/activate && python3 -m streamlit run annotation_app.py"
echo "albo: ./run_streamlit.sh"
