#!/bin/bash
# Pull SWE-bench Docker images before running benchmarks
#
# Pre-pulling images prevents timeout failures during patch generation.
# Uses official SWE-bench Docker Hub registry.
#
# Dependencies: Bash + Docker only (Python runs inside container)
#
# Usage:
#   ./scripts/pull_images.sh DATASET [--filter PATTERN]
#
# Arguments:
#   DATASET              HuggingFace dataset name (e.g., princeton-nlp/SWE-bench_Lite)
#
# Options:
#   --filter PATTERN     Only pull images matching pattern (pipe-separated)
#
# Examples:
#   ./scripts/pull_images.sh princeton-nlp/SWE-bench_Lite
#   ./scripts/pull_images.sh princeton-nlp/SWE-bench_Lite --filter "matplotlib|xarray"

set -e

# Parse arguments
DATASET=""
FILTER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --filter|-f)
            FILTER="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 DATASET [--filter PATTERN]"
            echo ""
            echo "Arguments:"
            echo "  DATASET              HuggingFace dataset name"
            echo ""
            echo "Options:"
            echo "  --filter PATTERN     Only pull images matching pattern (pipe-separated)"
            echo ""
            echo "Examples:"
            echo "  $0 princeton-nlp/SWE-bench_Lite"
            echo "  $0 princeton-nlp/SWE-bench_Lite --filter matplotlib"
            echo "  $0 princeton-nlp/SWE-bench_Lite --filter 'matplotlib|xarray'"
            exit 0
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            DATASET="$1"
            shift
            ;;
    esac
done

if [[ -z "$DATASET" ]]; then
    echo "Error: DATASET argument is required"
    echo "Usage: $0 DATASET [--filter PATTERN]"
    exit 1
fi

echo "================================================"
echo "SWE-bench Docker Image Puller"
echo "================================================"
echo "Dataset: $DATASET"
[[ -n "$FILTER" ]] && echo "Filter:  $FILTER"
echo "================================================"
echo ""

# Get list of instance IDs using Python inside a container
# This avoids requiring Python/datasets on the host
echo "Loading dataset (via container)..."

INSTANCE_IDS=$(docker run --rm \
    -e HF_HUB_DISABLE_PROGRESS_BARS=1 \
    python:3.11-slim \
    /bin/bash -c "
        pip install -q datasets > /dev/null 2>&1
        python3 << 'PYTHON_SCRIPT'
import sys
from datasets import load_dataset

dataset_name = '$DATASET'
filter_pattern = '$FILTER'

try:
    ds = load_dataset(dataset_name, split='test')
except Exception as e:
    print(f'ERROR: Failed to load dataset: {e}', file=sys.stderr)
    sys.exit(1)

for item in ds:
    iid = item['instance_id']
    if filter_pattern:
        patterns = [p.strip() for p in filter_pattern.split('|') if p.strip()]
        if patterns and not any(p.lower() in iid.lower() for p in patterns):
            continue
    print(iid)
PYTHON_SCRIPT
    ")

if [[ -z "$INSTANCE_IDS" ]]; then
    echo "ERROR: No instances found (or failed to load dataset)"
    exit 1
fi

# Count instances
TOTAL=$(echo "$INSTANCE_IDS" | wc -l | tr -d ' ')
echo "Found $TOTAL instances to check"
echo ""

# Pull images
PULLED=0
SKIPPED=0
FAILED=0
CURRENT=0

REGISTRY="docker.io/swebench/sweb.eval.x86_64"

while IFS= read -r INSTANCE_ID; do
    CURRENT=$((CURRENT + 1))

    # Convert to Docker-compatible name (same as mini-swe-agent)
    DOCKER_ID=$(echo "$INSTANCE_ID" | sed 's/__/_1776_/g' | tr '[:upper:]' '[:lower:]')
    IMAGE="${REGISTRY}.${DOCKER_ID}:latest"

    # Check if already exists
    if docker image inspect "$IMAGE" &>/dev/null; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # Pull image
    echo "[PULL $CURRENT/$TOTAL] $DOCKER_ID"
    if docker pull "$IMAGE" > /dev/null 2>&1; then
        PULLED=$((PULLED + 1))
    else
        echo "[FAIL $CURRENT/$TOTAL] $DOCKER_ID"
        FAILED=$((FAILED + 1))
    fi
done <<< "$INSTANCE_IDS"

echo ""
echo "Images: $PULLED pulled, $SKIPPED cached, $FAILED failed"

if [[ $FAILED -gt 0 ]]; then
    echo "WARNING: $FAILED images failed to pull" >&2
fi

echo ""
echo "================================================"
echo "Complete!"
echo "================================================"
