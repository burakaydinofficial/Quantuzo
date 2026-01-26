#!/bin/bash
set -e

# KV Cache Quantization Benchmark Runner
# ======================================
# Usage: ./run.sh --model MODEL --kv KV --dataset DATASET [OPTIONS] [COMMAND]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SPEC_DIR="$PROJECT_DIR/spec"

# Default values
MODEL=""
KV=""
DATASET=""
FILTER=""
USE_GPU=""
USE_CPU=""
COMMAND="both"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --model|-m)
            MODEL="$2"
            shift 2
            ;;
        --kv|-k)
            KV="$2"
            shift 2
            ;;
        --dataset|-d)
            DATASET="$2"
            shift 2
            ;;
        --filter|-f)
            FILTER="$2"
            shift 2
            ;;
        --gpu)
            USE_GPU="1"
            shift
            ;;
        --cpu)
            USE_CPU="1"
            shift
            ;;
        generate|evaluate|both|server|stop|logs|status)
            COMMAND="$1"
            shift
            ;;
        --help|-h)
            echo "KV Cache Quantization Benchmark Runner"
            echo ""
            echo "Usage: $0 --model MODEL --kv KV --dataset DATASET [OPTIONS] [COMMAND]"
            echo ""
            echo "Required arguments:"
            echo "  --model, -m MODEL      Model config name (e.g., qwen3-4b)"
            echo "  --kv, -k KV            KV cache config name (e.g., q8, f16, q8-q4)"
            echo "  --dataset, -d DATASET  Dataset config name (e.g., swe-lite)"
            echo ""
            echo "Optional arguments:"
            echo "  --filter, -f FILTER    Instance filter (pipe-separated instance IDs)"
            echo "  --gpu                  Use NVIDIA GPU acceleration (requires nvidia-container-toolkit)"
            echo "  --cpu                  Use extended timeouts for slow CPU inference"
            echo ""
            echo "Commands:"
            echo "  generate    Run patch generation only"
            echo "  evaluate    Run evaluation only"
            echo "  both        Full pipeline (default)"
            echo "  server      Start llama-server only"
            echo "  stop        Stop all services"
            echo "  logs        Tail logs"
            echo "  status      Show container status and memory"
            echo ""
            echo "Examples:"
            echo "  $0 --model qwen3-4b --kv q8 --dataset swe-lite"
            echo "  $0 -m qwen3-4b -k f16 -d swe-lite generate"
            echo "  $0 -m qwen3-4b -k q8 -d swe-lite --filter 'django__django-11099|django__django-11179'"
            echo ""
            echo "Available configs:"
            echo "  Models:       $(ls "$SPEC_DIR/models/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
            echo "  Quantization: $(ls "$SPEC_DIR/quantization/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
            echo "  Datasets:     $(ls "$SPEC_DIR/datasets/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Commands that don't require full config
case "$COMMAND" in
    stop)
        echo "Stopping all services..."
        docker compose --profile generate --profile evaluate down
        exit 0
        ;;
    logs)
        docker compose logs -f
        exit 0
        ;;
    status)
        echo "=== Running Containers ==="
        docker compose ps
        echo ""
        echo "=== Memory Usage ==="
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
            $(docker compose ps -q 2>/dev/null) 2>/dev/null || echo "No containers running"
        exit 0
        ;;
esac

# Validate required arguments
if [[ -z "$MODEL" ]]; then
    echo "Error: --model is required"
    echo "Available models: $(ls "$SPEC_DIR/models/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
    exit 1
fi

if [[ -z "$KV" ]]; then
    echo "Error: --kv is required"
    echo "Available KV configs: $(ls "$SPEC_DIR/quantization/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
    exit 1
fi

if [[ -z "$DATASET" ]]; then
    echo "Error: --dataset is required"
    echo "Available datasets: $(ls "$SPEC_DIR/datasets/" 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
    exit 1
fi

# Validate config files exist
RUNTIME_CONF="$SPEC_DIR/runtime.conf"
MODEL_CONF="$SPEC_DIR/models/${MODEL}.conf"
KV_CONF="$SPEC_DIR/quantization/${KV}.conf"
DATASET_CONF="$SPEC_DIR/datasets/${DATASET}.conf"

for conf in "$RUNTIME_CONF" "$MODEL_CONF" "$KV_CONF" "$DATASET_CONF"; do
    if [[ ! -f "$conf" ]]; then
        echo "Error: Config file not found: $conf"
        exit 1
    fi
done

# Load configs in order (later configs override earlier ones)
echo "Loading configuration..."
set -a
source "$RUNTIME_CONF"
source "$MODEL_CONF"
source "$KV_CONF"
source "$DATASET_CONF"
set +a

# Apply command-line overrides
if [[ -n "$FILTER" ]]; then
    export INSTANCE_FILTER="$FILTER"
fi

# Generate LiteLLM model registry for mini-SWE-agent
# This tells LiteLLM how to talk to our local model via OpenAI-compatible API
mkdir -p "$PROJECT_DIR/config/mini-swe-agent"
cat > "$PROJECT_DIR/config/mini-swe-agent/registry.json" << EOF
{
  "local/${MODEL_NAME}": {
    "max_tokens": 32768,
    "input_cost_per_token": 0.0,
    "output_cost_per_token": 0.0,
    "litellm_provider": "openai",
    "mode": "chat"
  }
}
EOF

# Build docker compose command with optional overrides
COMPOSE_CMD="docker compose"
if [[ -n "$USE_GPU" ]]; then
    COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.gpu.yml"
elif [[ -n "$USE_CPU" ]]; then
    COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.cpu.yml"
fi

# Generate timestamp
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")

# Generate RUN_ID with timestamp
# Format: {dataset}-{model}-kv-{k}-{v}-{timestamp}
# Extract quantization level: q8_0 -> q8, f16 -> f16
kv_k_short="${KV_TYPE_K%_*}"  # q8_0 -> q8, f16 -> f16
kv_v_short="${KV_TYPE_V%_*}"  # q4_0 -> q4, f16 -> f16
RUN_ID="${DATASET_NAME}-${MODEL_NAME}-kv-${kv_k_short}-${kv_v_short}-${TIMESTAMP}"
export RUN_ID

# Create results directory
RESULTS_DIR="$PROJECT_DIR/results/$RUN_ID"
mkdir -p "$RESULTS_DIR"

# Collect metadata
GIT_NAME=$(git config user.name 2>/dev/null || echo "unknown")
GIT_EMAIL=$(git config user.email 2>/dev/null || echo "unknown")
HOSTNAME=$(hostname 2>/dev/null || echo "unknown")

# Determine acceleration type
if [[ -n "$USE_GPU" ]]; then
    ACCEL_TYPE="gpu"
else
    ACCEL_TYPE="cpu"
fi

# Write metadata file (standard format for all benchmarks)
cat > "$RESULTS_DIR/metadata.json" << EOF
{
  "version": "1.0",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "run_id": "$RUN_ID",
  "benchmark": "swe-bench-${DATASET_NAME#swe-}",
  "dataset": "$DATASET",
  "contributor": {
    "name": "$GIT_NAME",
    "email": "$GIT_EMAIL",
    "hostname": "$HOSTNAME"
  },
  "model": {
    "name": "$MODEL_NAME",
    "file": "$MODEL_FILE"
  },
  "inference": {
    "accelerator": "$ACCEL_TYPE",
    "ctx_size": $CTX_SIZE,
    "threads": $THREADS,
    "threads_batch": $THREADS_BATCH,
    "kv_type_k": "$KV_TYPE_K",
    "kv_type_v": "$KV_TYPE_V"
  }
}
EOF

# Log function
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$RESULTS_DIR/run.log"
}

# Change to project directory
cd "$PROJECT_DIR"

# Print configuration
echo ""
echo "=========================================="
echo "KV Cache Quantization Benchmark"
echo "=========================================="
echo "Model:       $MODEL_NAME ($MODEL_FILE)"
echo "KV Cache:    K:$KV_TYPE_K / V:$KV_TYPE_V"
echo "Dataset:     $DATASET_NAME"
echo "Context:     $CTX_SIZE"
if [[ -n "$USE_GPU" ]]; then
    echo "Accelerator: GPU (CUDA)"
elif [[ -n "$USE_CPU" ]]; then
    echo "Threads:     $THREADS (batch: $THREADS_BATCH)"
    echo "Mode:        CPU (extended timeouts)"
else
    echo "Threads:     $THREADS (batch: $THREADS_BATCH)"
fi
echo "Contributor: $GIT_NAME <$GIT_EMAIL>"
echo "RUN_ID:      $RUN_ID"
if [[ -n "$INSTANCE_FILTER" ]]; then
    echo "Filter:      $INSTANCE_FILTER"
fi
echo "=========================================="
echo ""

case "$COMMAND" in
    server)
        log "Starting llama-server"
        $COMPOSE_CMD up llama-server
        ;;

    generate)
        log "Starting patch generation"
        $COMPOSE_CMD --profile generate up --abort-on-container-exit
        log "Patch generation completed"
        ;;

    evaluate)
        log "Starting evaluation"
        $COMPOSE_CMD --profile evaluate up --abort-on-container-exit
        log "Evaluation completed"
        ;;

    both)
        log "Starting full pipeline"

        # Check if llama-server is already running and healthy
        SERVER_WAS_RUNNING=""
        if $COMPOSE_CMD ps llama-server 2>/dev/null | grep -q "healthy"; then
            echo ""
            echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            echo "WARNING: llama-server is already running!"
            echo "The EXISTING server's KV config will be used, NOT: K:$KV_TYPE_K / V:$KV_TYPE_V"
            echo "To use the requested KV config, stop the server first:"
            echo "  ./scripts/run.sh stop"
            echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            echo ""
            log "Using existing llama-server (healthy) - WARNING: KV config may not match!"
            SERVER_WAS_RUNNING="1"
        else
            log "Starting llama-server (detached)"
            $COMPOSE_CMD up -d llama-server

            # Wait for server to be healthy (up to 5 minutes for model loading)
            log "Waiting for llama-server to be ready..."
            WAIT_COUNT=0
            MAX_WAIT=60  # 60 * 5 seconds = 5 minutes
            until $COMPOSE_CMD ps llama-server 2>/dev/null | grep -q "healthy"; do
                # Check if container exited
                if $COMPOSE_CMD ps llama-server 2>/dev/null | grep -q "Exited"; then
                    log "ERROR: llama-server exited unexpectedly"
                    $COMPOSE_CMD logs llama-server --tail 50
                    exit 1
                fi
                WAIT_COUNT=$((WAIT_COUNT + 1))
                if [[ $WAIT_COUNT -ge $MAX_WAIT ]]; then
                    log "ERROR: llama-server health check timeout"
                    $COMPOSE_CMD logs llama-server --tail 50
                    exit 1
                fi
                sleep 5
            done
            log "llama-server is ready"
        fi

        # Generate patches (only swe-agent output)
        log "Phase 1: Patch generation"
        $COMPOSE_CMD --profile generate up swe-agent

        # Stop llama-server only if we started it
        if [[ -z "$SERVER_WAS_RUNNING" ]]; then
            log "Stopping llama-server to free memory"
            $COMPOSE_CMD stop llama-server
        fi

        # Run evaluation
        log "Phase 2: Evaluation"
        $COMPOSE_CMD --profile evaluate up evaluator

        log "Full pipeline completed"
        log "Results available at: $RESULTS_DIR"
        ;;
esac
