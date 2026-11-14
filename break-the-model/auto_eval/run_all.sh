#!/bin/bash
# run_all.sh - Execute SQL extraction suite and update the unified AutoEval HTML dashboard
# Usage: ./run_all.sh [output_dir]

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="${1:-$PROJECT_ROOT/logs}"

echo "Starting SQL Extraction & Unified Dashboard Pipeline"
echo "====================================================="
echo ""

mkdir -p "$OUTPUT_DIR"
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo "Step 1/2: Running SQL extraction suite (non-Groq models)..."
python3 "$PROJECT_ROOT/auto_eval/generate_extraction_report.py"

echo ""
echo "Step 2/2: Updating unified HTML dashboard & console summary..."
python3 -m auto_eval.run_dashboard --no-open

echo ""
echo "Pipeline Complete! Dashboard written to: $PROJECT_ROOT/auto_eval/dashboard.html"
