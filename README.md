# KV Cache Quantization Benchmark on SWE-bench

A reproducible Docker Compose setup to benchmark how KV cache quantization in llama.cpp affects coding accuracy on SWE-bench tasks. This project measures the trade-off between memory savings and model quality degradation when using quantized KV caches (Q8, Q5, Q4) compared to the F16 baseline.

## Key Findings

*Results pending - run benchmarks to populate this table*

| KV Config | Resolved | Rate | Δ Baseline |
|-----------|----------|------|------------|
| K:f16/V:f16 | - | - | - |
| K:q8/V:q8 | - | - | - |
| K:q8/V:q4 | - | - | - |
| K:q4/V:q4 | - | - | - |

## Quick Start

```bash
# 1. Download a model to ./models/
mkdir -p models
# Download from https://huggingface.co/Qwen/Qwen3-4B-Instruct-GGUF

# 2. Build images
docker compose build

# 3. Run benchmark
./scripts/run.sh --model qwen3-4b-instruct-2507 --kv f16 --dataset swe-lite
```

## How It Works

This benchmark uses [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) for patch generation - a lightweight (~100 lines) but effective coding agent that:

1. **Clones the target repository** in a sandboxed container
2. **Lets the model browse files** via bash commands (cat, grep, find)
3. **Makes iterative edits** based on model decisions
4. **Generates patches via `git diff`** - real diffs, not LLM-imagined text

This is the same approach used by top SWE-bench submissions (74%+ on Verified).

## Hardware Requirements

**Supports:** CPU and NVIDIA GPU inference

### Context Length

Default is 64K tokens (65536). This can be adjusted in `spec/runtime.conf`.

**Note:** Results with different context sizes are not directly comparable. When comparing KV quantization levels, use the same context size for all runs.

### Minimum RAM Requirements (64K context)

| Model | Weights (Q4) | F16 KV | Q8 KV | Q4 KV | Minimum RAM |
|-------|--------------|--------|-------|-------|-------------|
| Qwen3-4B | 2.5GB | 9GB | 4.5GB | 2.3GB | **16GB** |
| Qwen3-14B | 8GB | 9GB | 4.5GB | 2.3GB | **24GB** |
| Qwen3-32B | 19GB | 9GB | 4.5GB | 2.3GB | **32GB** |

Memory estimates are approximate. Actual usage depends on model architecture and batch settings.

## Build Options

### Portable Build (default)
Works on most x86_64 CPUs (2013+, requires AVX2):
```bash
docker compose build
```

### Native Build
Optimized for the CPU building the image:
```bash
docker compose build --build-arg NATIVE_BUILD=ON
```

**Note:** Do not publish pre-built images. Users should build locally for optimal performance.

## GPU Support (NVIDIA CUDA)

GPU acceleration uses the official pre-built CUDA image from llama.cpp.

### Prerequisites

Install nvidia-container-toolkit on your host:

```bash
# Ubuntu/Debian
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Usage

Add the `--gpu` flag to any run command:

```bash
./scripts/run.sh --gpu --model qwen3-4b-instruct-2507 --kv q8 --dataset swe-lite
./scripts/run.sh --gpu -m qwen3-4b-instruct-2507 -k f16 -d swe-lite server
```

GPU mode:
- Uses pre-built `ghcr.io/ggml-org/llama.cpp:server-cuda` (no local build needed)
- Offloads all model layers to GPU (`--n-gpu-layers 999`)
- Enables flash attention for better performance
- Ignores CPU thread settings (irrelevant for GPU inference)

### VRAM Requirements (64K context)

| Model | Weights (Q4) | F16 KV | Q8 KV | Q4 KV | Minimum VRAM |
|-------|--------------|--------|-------|-------|--------------|
| Qwen3-4B | 2.5GB | 9GB | 4.5GB | 2.3GB | **12GB** |
| Qwen3-14B | 8GB | 9GB | 4.5GB | 2.3GB | **18GB** |
| Qwen3-32B | 19GB | 9GB | 4.5GB | 2.3GB | **32GB** |

## Configuration System

Configuration is split into four independent layers:

```
spec/
├── runtime.conf              # CTX_SIZE, THREADS, EVAL_WORKERS
├── models/
│   └── qwen3-4b-instruct-2507.conf  # MODEL_FILE, MODEL_NAME
├── quantization/
│   ├── f16.conf              # KV_TYPE_K, KV_TYPE_V
│   ├── q8.conf
│   ├── q5.conf
│   ├── q8-q4.conf
│   └── q4.conf
└── datasets/
    ├── swe-lite.conf         # DATASET, DATASET_NAME, SUBSET
    └── swe-full.conf
```

**Config merge order:** runtime → model (can override) → quantization → dataset

## Commands

```bash
# Full pipeline
./scripts/run.sh --model qwen3-4b-instruct-2507 --kv q8 --dataset swe-lite

# Short flags
./scripts/run.sh -m qwen3-4b-instruct-2507 -k q8 -d swe-lite

# Generate patches only
./scripts/run.sh -m qwen3-4b-instruct-2507 -k q8 -d swe-lite generate

# Evaluate existing patches
./scripts/run.sh -m qwen3-4b-instruct-2507 -k q8 -d swe-lite evaluate

# Quick validation with instance filter
./scripts/run.sh -m qwen3-4b-instruct-2507 -k f16 -d swe-lite --filter "django__django-11099|django__django-11179"

# Start llama-server for testing
./scripts/run.sh -m qwen3-4b-instruct-2507 -k q8 -d swe-lite server

# Utility commands (no config required)
./scripts/run.sh stop      # Stop all services
./scripts/run.sh logs      # Tail logs
./scripts/run.sh status    # Show containers + memory

# Run all KV configurations for a model
./scripts/run_all.sh --model qwen3-4b-instruct-2507

# Analyze results
python scripts/analyze_results.py
python scripts/analyze_results.py --export-csv results.csv
python scripts/analyze_results.py --export-chart results.svg

# Show help
./scripts/run.sh --help
```

## Results Structure

Each run creates a timestamped folder with standardized metadata:

```
results/swe-lite-qwen3-4b-instruct-2507-kv-q8-q8-20240115_143052/
├── metadata.json             # Standard format (contributor, config, timestamps)
├── preds.json                # mini-SWE-agent output
├── swebench_predictions.json # Converted for SWE-bench harness
└── evaluation_results.json   # Evaluation results
```

**metadata.json** is our standard format - consistent across all benchmark types:
```json
{
  "version": "1.0",
  "timestamp": "2024-01-15T14:30:52Z",
  "run_id": "swe-lite-qwen3-4b-instruct-2507-kv-q8-q8-20240115_143052",
  "benchmark": "swe-bench-lite",
  "contributor": {
    "name": "John Doe",
    "email": "john@example.com",
    "hostname": "johns-macbook"
  },
  "model": { "name": "qwen3-4b-instruct-2507", "file": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf" },
  "inference": { "ctx_size": 65536, "kv_type_k": "q8_0", "kv_type_v": "q8_0", ... }
}
```

## Contributing Results

Results are tracked in this repository. Each run gets a unique timestamped folder, so multiple contributors can submit results for the same configuration without conflicts.

To contribute:
1. Run your benchmark
2. Submit a PR with your results folder
3. Include your hardware specs in the PR description

## Adding New Models

1. Download the GGUF model to `./models/`:
   ```bash
   huggingface-cli download Qwen/Qwen3-14B-Instruct-GGUF \
     qwen3-14b-instruct-q4_k_m.gguf --local-dir ./models/
   ```

2. Create a model config:
   ```bash
   cat > spec/models/qwen3-14b.conf << 'EOF'
   MODEL_FILE=qwen3-14b-instruct-q4_k_m.gguf
   MODEL_NAME=qwen3-14b
   EOF
   ```

3. Run benchmarks:
   ```bash
   ./scripts/run_all.sh --model qwen3-14b
   ```

The LiteLLM model registry is generated automatically at runtime by `run.sh`.

## Interpreting Results

### Resolution Rate
The percentage of SWE-bench instances where the generated patch successfully resolves the issue. Higher is better.

### Δ Baseline
The difference in resolution rate compared to the F16 baseline. Negative values indicate quality degradation from quantization.

### Expected Patterns
- Q8 typically shows minimal degradation (<1%)
- Q8/Q4 asymmetric often performs better than Q4/Q4 symmetric
- Q4 may show 2-5% degradation depending on the model

## Architecture

```
Host
└── Docker Compose
    ├── llama-server (llama.cpp with configurable KV cache)
    │   └── Exposes OpenAI-compatible API on port 8080
    ├── swe-agent (mini-SWE-agent for patch generation)
    │   ├── Connects to llama-server via /v1/chat/completions
    │   └── Mounts docker.sock for sandboxed execution
    └── evaluator (SWE-bench harness)
        └── Mounts docker.sock to spawn test containers
```

## License

MIT
