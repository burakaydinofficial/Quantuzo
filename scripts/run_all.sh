#!/bin/bash
set -e

# Run all KV cache configurations for a model
# ============================================
# Usage: ./run_all.sh --model MODEL [--dataset DATASET] [--gpu|--cuda124] [...]
#
# Any flags not consumed by this script are forwarded to run.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SPEC_DIR="$PROJECT_DIR/spec"

MODEL=""
DATASET="swe-lite"
RUN_SH_FLAGS=()

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
            echo "Usage: $0 --model MODEL [--dataset DATASET] [OPTIONS]"
            echo ""
            echo "Arguments:"
            echo "  --model, -m MODEL      Model config name (required)"
            echo "  --dataset, -d DATASET  Dataset config name (default: swe-lite)"
            echo ""
            echo "All other flags are forwarded to run.sh (e.g., --gpu, --cuda124, --push, --no-pull, --filter)."
            echo ""
            echo "Examples:"
            echo "  $0 --model qwen3.5-4b-q4"
            echo "  $0 --model qwen3.5-4b-q4 --gpu"
            echo "  $0 --model qwen3.5-4b-q4 --cuda124 --push"
            echo "  $0 --model qwen3.5-4b-q4 --gpu --dataset swe-full"
            echo ""
            echo "Available configs:"
            echo "  Models:       $(ls "$SPEC_DIR/models/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
            echo "  Quantization: $(ls "$SPEC_DIR/quantization/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
            echo "  Datasets:     $(ls "$SPEC_DIR/datasets/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
            exit 0
            ;;
        *)
            # Collect all other flags for run.sh passthrough
            RUN_SH_FLAGS+=("$1")
            # If the next arg exists and doesn't start with --, it's a value for this flag
            if [[ $# -ge 2 ]] && [[ "$2" != --* ]] && [[ "$2" != -* ]]; then
                RUN_SH_FLAGS+=("$2")
                shift
            fi
            shift
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
echo "Model:       $MODEL"
echo "Dataset:     $DATASET"
echo "KV Configs:  ${KV_CONFIGS[*]}"
if [[ ${#RUN_SH_FLAGS[@]} -gt 0 ]]; then
    echo "Extra flags: ${RUN_SH_FLAGS[*]}"
fi
echo "=========================================="
echo ""

for kv in "${KV_CONFIGS[@]}"; do
    echo ""
    echo "=========================================="
    echo "Running: $MODEL with KV=$kv"
    echo "=========================================="
    echo ""

    "$SCRIPT_DIR/run.sh" --model "$MODEL" --kv "$kv" --dataset "$DATASET" "${RUN_SH_FLAGS[@]}" both

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
python3 "$SCRIPT_DIR/analyze_results.py"
