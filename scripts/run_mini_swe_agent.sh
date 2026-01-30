#!/bin/bash
# Wrapper script for mini-SWE-agent
# Handles conditional arguments

set -e

# Build command
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
