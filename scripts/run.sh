#!/bin/bash
set -e

# KV Cache Quantization Benchmark Runner
# Usage: ./run.sh --model MODEL --kv KV --dataset DATASET [OPTIONS] [COMMAND]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SPEC_DIR="$PROJECT_DIR/spec"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

MODEL=""
KV=""
DATASET=""
FILTER=""
USE_GPU=""
USE_CPU=""
USE_CUDA124=""
USE_AGENT_V2=""
USE_DOWNLOAD=""
SKIP_PULL=""
PUSH_RESULTS=""
CUSTOM_RUN_ID=""
COMMAND="both"

while [[ $# -gt 0 ]]; do
    case $1 in
        --model|-m)     MODEL="$2";         shift 2 ;;
        --kv|-k)        KV="$2";            shift 2 ;;
        --dataset|-d)   DATASET="$2";       shift 2 ;;
        --filter|-f)    FILTER="$2";        shift 2 ;;
        --gpu)          USE_GPU="1";        shift ;;
        --cuda124)      USE_CUDA124="1";    shift ;;
        --cpu)          USE_CPU="1";        shift ;;
        --agent-v2)     USE_AGENT_V2="1";   shift ;;
        --download)     USE_DOWNLOAD="1";   shift ;;
        --no-pull)      SKIP_PULL="1";      shift ;;
        --push)         PUSH_RESULTS="1";   shift ;;
        --run-id)       CUSTOM_RUN_ID="$2"; shift 2 ;;
        generate|evaluate|both|server|stop|logs|status)
            COMMAND="$1"; shift ;;
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
            echo "  --cuda124              Custom CUDA 12.4 build with flash attention for all KV quant types (implies --gpu)"
            echo "  --cpu                  Use extended timeouts for slow CPU inference"
            echo "  --agent-v2             Use mini-swe-agent v2 (experimental, for testing)"
            echo "  --download             Download model from HuggingFace if not present"
            echo "  --no-pull              Skip Docker image pull (run pull separately in parallel)"
            echo "  --push                 Push results to HuggingFace after evaluation (requires HF_TOKEN)"
            echo "  --run-id ID            Use existing run ID (for evaluating interrupted runs)"
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

# Commands that don't require config
case "$COMMAND" in
    stop)
        echo "Stopping all services..."
        docker compose --profile generate --profile generate-v2 --profile evaluate down
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

# --- From here on, all commands require model/kv/dataset ---

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

# Load configs in order: runtime → model → quantization → dataset
echo "Loading configuration..."
set -a
source "$RUNTIME_CONF"
source "$MODEL_CONF"
source "$KV_CONF"
source "$DATASET_CONF"
set +a

if [[ -n "$FILTER" ]]; then
    export INSTANCE_FILTER="$FILTER"
fi

MODEL_PATH="$PROJECT_DIR/models/$MODEL_FILE"
if [[ ! -f "$MODEL_PATH" ]]; then
    if [[ -n "$USE_DOWNLOAD" ]]; then
        echo "Model not found, downloading..."
        if ! "$SCRIPT_DIR/download_model.sh" "$MODEL"; then
            echo "Error: Failed to download model"
            exit 1
        fi
    else
        echo "Error: Model file not found: $MODEL_PATH"
        if [[ -n "$MODEL_REPO" ]]; then
            echo "Run with --download to auto-download from HuggingFace"
            echo "Or manually: ./scripts/download_model.sh $MODEL"
        else
            echo "MODEL_REPO not configured for auto-download"
            echo "Download manually from HuggingFace"
        fi
        exit 1
    fi
fi

# CTX_SIZE is per-slot; llama-server needs total
export LLAMA_CTX_SIZE=$((CTX_SIZE * ${PARALLEL:-1}))

# Generate LiteLLM model registry for mini-SWE-agent
# Cost limits prevent runaway generation: input ~2.5M tokens, output ~250K tokens per instance
# (both share budget of 3 via cost_limit in swebench.yaml, 1:10 weight ratio)
if [[ -n "$USE_AGENT_V2" ]]; then
    AGENT_CONFIG_DIR="$PROJECT_DIR/config/mini-swe-agent-v2"
else
    AGENT_CONFIG_DIR="$PROJECT_DIR/config/mini-swe-agent"
fi
mkdir -p "$AGENT_CONFIG_DIR"
cat > "$AGENT_CONFIG_DIR/registry.json" << EOF
{
  "local/${MODEL_NAME}": {
    "max_tokens": 8192,
    "input_cost_per_token": 0.0000012,
    "output_cost_per_token": 0.000012,
    "litellm_provider": "openai",
    "mode": "chat"
  }
}
EOF

# --cuda124 implies --gpu
if [[ -n "$USE_CUDA124" ]]; then
    USE_GPU="1"
fi

# Build docker compose command
COMPOSE_FILES="-f docker-compose.yml"
if [[ -n "$USE_GPU" ]]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
    if [[ -n "$USE_CUDA124" ]]; then
        COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu-cuda124.yml"
    fi
elif [[ -n "$USE_CPU" ]]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.cpu.yml"
fi
if [[ -n "$USE_AGENT_V2" ]]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.v2.yml"
fi
COMPOSE_CMD="docker compose $COMPOSE_FILES"

GIT_NAME=$(git config user.name 2>/dev/null || echo "unknown")
GIT_EMAIL=$(git config user.email 2>/dev/null || echo "unknown")

if [[ -n "$USE_AGENT_V2" ]]; then
    AGENT_BRANCH="v2"
    AGENT_PKG_VERSION="${MINI_SWE_AGENT_VERSION_V2:-2.2.4}"
else
    AGENT_BRANCH="v1"
    AGENT_PKG_VERSION="${MINI_SWE_AGENT_VERSION:-1.17.5}"
fi

# --- Helper functions ---

setup_results_dir() {
    if [[ -n "$CUSTOM_RUN_ID" ]]; then
        RUN_ID="$CUSTOM_RUN_ID"
    else
        RUN_ID="${DATASET_NAME}-${MODEL_NAME}-kv-${KV_TYPE_K}-${KV_TYPE_V}-$(date -u +%Y%m%d_%H%M%S)"
    fi
    export RUN_ID

    RESULTS_DIR="$PROJECT_DIR/results/$RUN_ID"
    mkdir -p "$RESULTS_DIR"

    # Preserve existing metadata for resumed runs
    if [[ -n "$CUSTOM_RUN_ID" ]] && [[ -f "$RESULTS_DIR/metadata.json" ]]; then
        return
    fi

    local accel="cpu"
    [[ -n "$USE_GPU" ]] && accel="gpu"

cat > "$RESULTS_DIR/metadata.json" << EOF
{
  "version": "1.0",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "run_id": "$RUN_ID",
  "benchmark": "swe-bench-${DATASET_NAME#swe-}",
  "dataset": "$DATASET",
  "contributor": {
    "name": "$GIT_NAME",
    "email": "$GIT_EMAIL",
    "hostname": "$(hostname 2>/dev/null || echo unknown)"
  },
  "model": {
    "name": "$MODEL_NAME",
    "file": "$MODEL_FILE"
  },
  "inference": {
    "accelerator": "$accel",
    "ctx_size": $CTX_SIZE,
    "kv_type_k": "$KV_TYPE_K",
    "kv_type_v": "$KV_TYPE_V"
  },
  "agent": {
    "name": "mini-swe-agent",
    "branch": "$AGENT_BRANCH",
    "version": "$AGENT_PKG_VERSION"
  }
}
EOF
}

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    [[ -n "$RESULTS_DIR" ]] && echo "$msg" >> "$RESULTS_DIR/run.log"
}

pull_images() {
    if [[ -n "$SKIP_PULL" ]]; then
        log "Skipping Docker image pull (--no-pull)"
        return 0
    fi

    log "Pulling Docker images for $DATASET_NAME..."

    local PULL_ARGS=("$DATASET")
    [[ -n "$INSTANCE_FILTER" ]] && PULL_ARGS+=(--filter "$INSTANCE_FILTER")

    if ! "$SCRIPT_DIR/pull_images.sh" "${PULL_ARGS[@]}"; then
        log "ERROR: Failed to pull Docker images"
        exit 1
    fi
}

wait_for_server() {
    log "Waiting for llama-server to be ready..."
    local attempts=0
    local max_attempts=60  # 60 × 5s = 5 minutes
    until $COMPOSE_CMD ps llama-server 2>/dev/null | grep -q "healthy"; do
        if $COMPOSE_CMD ps llama-server 2>/dev/null | grep -q "Exited"; then
            log "ERROR: llama-server exited unexpectedly"
            $COMPOSE_CMD logs llama-server --tail 50
            exit 1
        fi
        attempts=$((attempts + 1))
        if [[ $attempts -ge $max_attempts ]]; then
            log "ERROR: llama-server health check timeout"
            $COMPOSE_CMD logs llama-server --tail 50
            exit 1
        fi
        sleep 5
    done
    log "llama-server is ready"
}

run_generate() {
    if [[ -n "$USE_AGENT_V2" ]]; then
        log "Using mini-swe-agent v2"
        $COMPOSE_CMD --profile generate-v2 up "$@"
    else
        $COMPOSE_CMD --profile generate up "$@"
    fi
}

push_results() {
    if [[ -n "$PUSH_RESULTS" ]]; then
        log "Pushing results to HuggingFace..."
        python3 "$SCRIPT_DIR/push_results.py" --run-id "$RUN_ID" || {
            log "WARNING: Failed to push results to HuggingFace"
        }
    fi
}

# --- Print configuration ---

cd "$PROJECT_DIR"

echo ""
echo "=========================================="
echo "KV Cache Quantization Benchmark"
echo "=========================================="
echo "Model:       $MODEL_NAME ($MODEL_FILE)"
echo "KV Cache:    K:$KV_TYPE_K / V:$KV_TYPE_V"
echo "Dataset:     $DATASET_NAME"
echo "Context:     $CTX_SIZE per slot (total: $LLAMA_CTX_SIZE)"
echo "Parallel:    ${PARALLEL:-1} slot(s)"
echo "Workers:     ${WORKERS:-2}"
if [[ -n "$USE_CUDA124" ]]; then
    echo "Accelerator: GPU (CUDA 12.4, all-quant FA)"
elif [[ -n "$USE_GPU" ]]; then
    echo "Accelerator: GPU (CUDA)"
elif [[ -n "$USE_CPU" ]]; then
    echo "Threads:     $THREADS (batch: $THREADS_BATCH)"
    echo "Mode:        CPU (extended timeouts)"
else
    echo "Threads:     $THREADS (batch: $THREADS_BATCH)"
fi
echo "Contributor: $GIT_NAME <$GIT_EMAIL>"
[[ -n "$INSTANCE_FILTER" ]] && echo "Filter:      $INSTANCE_FILTER"
echo "Agent:       mini-swe-agent $AGENT_BRANCH ($AGENT_PKG_VERSION)"
echo "=========================================="
echo ""

# --- Execute command ---

case "$COMMAND" in
    server)
        $COMPOSE_CMD up llama-server
        ;;

    generate)
        setup_results_dir
        pull_images
        log "Starting patch generation"
        run_generate --abort-on-container-exit
        log "Patch generation completed"
        ;;

    evaluate)
        setup_results_dir
        log "Starting evaluation"
        $COMPOSE_CMD --profile evaluate up evaluator
        log "Evaluation completed"
        push_results
        ;;

    both)
        setup_results_dir
        log "Starting full pipeline"
        pull_images

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
            log "Using existing llama-server - WARNING: KV config may not match!"
            SERVER_WAS_RUNNING="1"
        else
            log "Starting llama-server (detached)"
            $COMPOSE_CMD up -d llama-server
            wait_for_server
        fi

        log "Phase 1: Patch generation"
        run_generate --force-recreate --no-deps

        if [[ -z "$SERVER_WAS_RUNNING" ]]; then
            log "Stopping llama-server to free memory"
            $COMPOSE_CMD stop llama-server
        fi

        log "Phase 2: Evaluation"
        $COMPOSE_CMD --profile evaluate up evaluator
        push_results

        log "Full pipeline completed"
        log "Results available at: $RESULTS_DIR"
        ;;
esac
