#!/bin/bash
set -e

# Run all KV cache configurations for a model
# ============================================
# Usage: ./run_all.sh --model MODEL --dataset DATASET

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SPEC_DIR="$PROJECT_DIR/spec"

MODEL=""
DATASET="swe-lite"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --model|-m)
            MODEL="$2"
            shift 2
            ;;
        --dataset|-d)
            DATASET="$2"
            shift 2
            ;;
        --help|-h)
            echo "Run all KV configurations for a model"
            echo ""
            echo "Usage: $0 --model MODEL [--dataset DATASET]"
            echo ""
            echo "Arguments:"
            echo "  --model, -m MODEL      Model config name (required)"
            echo "  --dataset, -d DATASET  Dataset config name (default: swe-lite)"
            echo ""
            echo "Example:"
            echo "  $0 --model qwen3-4b"
            echo "  $0 --model qwen3-14b --dataset swe-full"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$MODEL" ]]; then
    echo "Error: --model is required"
    echo "Available models: $(ls "$SPEC_DIR/models/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
    exit 1
fi

# Get all quantization configs
KV_CONFIGS=($(ls "$SPEC_DIR/quantization/" | sed 's/\.conf$//'))

echo "=========================================="
echo "KV Cache Quantization Benchmark Suite"
echo "=========================================="
echo "Model:   $MODEL"
echo "Dataset: $DATASET"
echo "KV Configs: ${KV_CONFIGS[*]}"
echo "=========================================="
echo ""

for kv in "${KV_CONFIGS[@]}"; do
    echo ""
    echo "=========================================="
    echo "Running: $MODEL with KV=$kv"
    echo "=========================================="
    echo ""

    "$SCRIPT_DIR/run.sh" --model "$MODEL" --kv "$kv" --dataset "$DATASET" both

    echo ""
    echo "Completed: $MODEL with KV=$kv"
    echo ""
done

echo ""
echo "=========================================="
echo "All configurations completed"
echo "=========================================="
echo ""

# Run analysis
echo "Running analysis..."
python "$SCRIPT_DIR/analyze_results.py"
