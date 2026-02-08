#!/bin/bash
# Wrapper script for mini-SWE-agent v2
# =====================================
# Handles conditional arguments for v2 API.
#
# v2 Changes from v1:
# - Uses litellm_textbased for text-based parsing (local models)
# - Config structure changed (observation_template under model)
# - Agent.run() returns dict instead of tuple
# - CLI mostly compatible but supports new -c override syntax

set -e

# Print version for debugging
echo "=== mini-swe-agent v2 ==="
pip show mini-swe-agent | grep Version || echo "Package info not available"
echo "========================="

# Build command - v2 CLI is compatible with v1 for basic usage
CMD="mini-extra swebench"
CMD="$CMD --config /app/config/swebench.yaml"
CMD="$CMD --model local/${MODEL_NAME:-qwen3-4b}"
CMD="$CMD --subset ${SUBSET:-lite}"
CMD="$CMD --split test"
CMD="$CMD --output /results/${RUN_ID:-default}"
CMD="$CMD --workers ${WORKERS:-2}"

# Add filter only if set
if [[ -n "$INSTANCE_FILTER" ]]; then
    CMD="$CMD --filter \"$INSTANCE_FILTER\""
fi

echo "Running: $CMD"
eval $CMD
