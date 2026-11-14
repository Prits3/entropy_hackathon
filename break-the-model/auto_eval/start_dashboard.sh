#!/bin/bash
# AutoEval Dashboard Server — serves a live dashboard that regenerates on every request.
# Usage: ./start_dashboard.sh [port]

PORT=${1:-8050}
cd "$(dirname "$0")/.." || exit 1

PYTHON=.venv/bin/python
[ -x "$PYTHON" ] || PYTHON=python3

echo "Starting AutoEval Dashboard at http://localhost:$PORT ..."
exec "$PYTHON" -m auto_eval.run_dashboard --serve --port "$PORT"
