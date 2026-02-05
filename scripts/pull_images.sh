#!/bin/bash
# Pull SWE-bench Docker images before running benchmarks
#
# Pre-pulling images prevents timeout failures during patch generation.
# Uses official SWE-bench Docker Hub registry.
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

# Pass variables via environment to avoid shell expansion issues
export PULL_DATASET="$DATASET"
export PULL_FILTER="${FILTER:-}"

# Run Python script with proper error handling
if ! python3 << 'PYTHON_SCRIPT'
import os
import sys
import subprocess
from datasets import load_dataset

dataset_name = os.environ.get("PULL_DATASET", "")
filter_pattern = os.environ.get("PULL_FILTER", "")
registry = "docker.io/swebench/sweb.eval.x86_64"

if not dataset_name:
    print("ERROR: No dataset specified", file=sys.stderr)
    sys.exit(1)

print(f"Loading dataset {dataset_name}...")
try:
    ds = load_dataset(dataset_name, split="test")
except Exception as e:
    print(f"ERROR: Failed to load dataset: {e}", file=sys.stderr)
    sys.exit(1)

# Collect instances to pull
instances = []
for item in ds:
    iid = item["instance_id"]
    # Apply filter if specified (supports pipe-separated patterns)
    if filter_pattern:
        # Filter out empty patterns from "a||b" edge case
        patterns = [p.strip() for p in filter_pattern.split("|") if p.strip()]
        if patterns and not any(p.lower() in iid.lower() for p in patterns):
            continue
    instances.append(iid)

total = len(instances)
print(f"Found {total} instances to check")

pulled = 0
skipped = 0
failed = 0

for i, iid in enumerate(instances, 1):
    # Convert to Docker-compatible name (same as mini-swe-agent)
    docker_id = iid.replace("__", "_1776_").lower()
    image = f"{registry}.{docker_id}:latest"

    # Check if already exists
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True
    )
    if result.returncode == 0:
        skipped += 1
        continue

    # Pull image
    print(f"[PULL {i}/{total}] {docker_id}")
    result = subprocess.run(
        ["docker", "pull", image],
        capture_output=True
    )
    if result.returncode == 0:
        pulled += 1
    else:
        print(f"[FAIL {i}/{total}] {docker_id}")
        failed += 1

print(f"")
print(f"Images: {pulled} pulled, {skipped} cached, {failed} failed")

if failed > 0:
    print(f"WARNING: {failed} images failed to pull", file=sys.stderr)
PYTHON_SCRIPT
then
    echo "ERROR: Failed to pull Docker images"
    exit 1
fi

# Clean up environment variables
unset PULL_DATASET PULL_FILTER

echo ""
echo "================================================"
echo "Complete!"
echo "================================================"
