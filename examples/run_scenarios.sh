#!/usr/bin/env bash
# Run all example scenarios against the local server and save plots.
# Usage: bash examples/run_scenarios.sh
# Requires: server running on :8000, venv active, matplotlib installed.

set -euo pipefail
BASE="http://localhost:8000/ai/risk-assess"
PLOT="python3 tools/plot_response.py"

run() {
  local file="$1"
  local name="$2"
  echo "▶  $file → examples/${name}.png"
  curl -s -X POST "$BASE" \
    -H 'Content-Type: application/json' \
    -d "@examples/${file}" \
    | $PLOT --output "examples/${name}.png"
}

run "request.json"                   "acetamiprid_baseline"
run "request_deltamethrin.json"      "deltamethrin_aerial"
run "request_fungicide.json"         "fungicide_safe"
run "request_spinosad_night.json"    "spinosad_night"
run "request_chlorpyrifos_storm.json" "chlorpyrifos_storm"

echo ""
echo "✓  All plots saved to examples/"
