#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! python3 -m venv --help >/dev/null 2>&1; then
	echo "Python venv support is missing." >&2
	echo "Ubuntu/WSL: sudo apt update && sudo apt install -y python3-venv python3-tk" >&2
	exit 2
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
	echo "Python Tk support is missing." >&2
	echo "Ubuntu/WSL: sudo apt update && sudo apt install -y python3-tk" >&2
	exit 2
fi

python3 -m venv "${ROOT_DIR}/client/.venv"
"${ROOT_DIR}/client/.venv/bin/python" -m pip install --upgrade pip
"${ROOT_DIR}/client/.venv/bin/python" -m pip install -r "${ROOT_DIR}/client/requirements.txt"
"${ROOT_DIR}/client/.venv/bin/python" "${ROOT_DIR}/scripts/generate_python.py"

echo "Run: source client/.venv/bin/activate && python client/tk_app.py"