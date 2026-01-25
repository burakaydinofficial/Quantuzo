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
./scripts/run.sh --model qwen3-4b --kv f16 --dataset swe-lite
```

## Hardware Requirements

**Supports:** CPU and NVIDIA GPU inference

### Mandatory Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Context Length | 32768 | Fixed for all benchmark runs |

**Context length is NOT configurable.** All valid benchmark results must use 32K context. Reducing context length invalidates comparisons and results cannot be submitted.

### Minimum RAM Requirements (32K context, mandatory)

| Model | Weights (Q4) | F16 KV | Q8 KV | Q4 KV | Minimum RAM |
|-------|--------------|--------|-------|-------|-------------|
| Qwen3-4B | 2.5GB | 4.6GB | 2.3GB | 1.2GB | **16GB** |
| Qwen3-14B | 8GB | 4.6GB | 2.3GB | 1.2GB | **24GB** |
| Qwen3-32B | 19GB | 4.6GB | 2.3GB | 1.2GB | **32GB** |

If your system doesn't meet the minimum RAM for your target model, **use a smaller model** - do not reduce context length.

### Tested Configurations
- AMD Ryzen 9 5950X (16C/32T) + 96GB DDR4-3200
- Intel Core Ultra 7 155H + 80GB LPDDR5x-5600

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
./scripts/run.sh --gpu --model qwen3-4b --kv q8 --dataset swe-lite
./scripts/run.sh --gpu -m qwen3-4b -k f16 -d swe-lite server
```

GPU mode:
- Uses pre-built `ghcr.io/ggml-org/llama.cpp:server-cuda` (no local build needed)
- Offloads all model layers to GPU (`--n-gpu-layers 999`)
- Enables flash attention for better performance
- Ignores CPU thread settings (irrelevant for GPU inference)

### VRAM Requirements (32K context)

| Model | Weights (Q4) | F16 KV | Q8 KV | Q4 KV | Minimum VRAM |
|-------|--------------|--------|-------|-------|--------------|
| Qwen3-4B | 2.5GB | 4.6GB | 2.3GB | 1.2GB | **8GB** |
| Qwen3-14B | 8GB | 4.6GB | 2.3GB | 1.2GB | **16GB** |
| Qwen3-32B | 19GB | 4.6GB | 2.3GB | 1.2GB | **24GB** |

## Configuration System

Configuration is split into four independent layers:

```
spec/
├── runtime.conf              # CTX_SIZE, THREADS, EVAL_WORKERS
├── models/
│   ├── qwen3-4b.conf         # MODEL_FILE, MODEL_NAME
│   ├── qwen3-14b.conf
│   └── qwen3-32b.conf
├── quantization/
│   ├── f16.conf              # KV_TYPE_K, KV_TYPE_V
│   ├── q8.conf
│   ├── q5.conf
│   ├── q8-q4.conf
│   └── q4.conf
└── datasets/
    ├── swe-lite.conf         # DATASET, DATASET_NAME
    └── swe-full.conf
```

**Config merge order:** runtime → model (can override) → quantization → dataset

## Commands

```bash
# Full pipeline
./scripts/run.sh --model qwen3-4b --kv q8 --dataset swe-lite

# Short flags
./scripts/run.sh -m qwen3-4b -k q8 -d swe-lite

# Generate patches only
./scripts/run.sh -m qwen3-4b -k q8 -d swe-lite generate

# Evaluate existing patches
./scripts/run.sh -m qwen3-4b -k q8 -d swe-lite evaluate

# Quick validation with instance filter
./scripts/run.sh -m qwen3-4b -k f16 -d swe-lite --filter "django__django-11099|django__django-11179"

# Start llama-server for testing
./scripts/run.sh -m qwen3-4b -k q8 -d swe-lite server

# Utility commands (no config required)
./scripts/run.sh stop      # Stop all services
./scripts/run.sh logs      # Tail logs
./scripts/run.sh status    # Show containers + memory

# Run all KV configurations for a model
./scripts/run_all.sh --model qwen3-4b

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
results/swe-lite-qwen3-4b-kv-q8-q8-20240115_143052/
├── metadata.json             # Standard format (contributor, config, timestamps)
├── patches.json              # Generated patches (SWE-bench format)
└── evaluation_results.json   # Evaluation results (SWE-bench format)
```

**metadata.json** is our standard format - consistent across all benchmark types:
```json
{
  "version": "1.0",
  "timestamp": "2024-01-15T14:30:52Z",
  "run_id": "swe-lite-qwen3-4b-kv-q8-q8-20240115_143052",
  "benchmark": "swe-bench-lite",
  "contributor": {
    "name": "John Doe",
    "email": "john@example.com",
    "hostname": "johns-macbook"
  },
  "model": { "name": "qwen3-4b", "file": "qwen3-4b-instruct-q4_k_m.gguf" },
  "inference": { "ctx_size": 32768, "kv_type_k": "q8_0", "kv_type_v": "q8_0", ... }
}
```

Other files (patches.json, evaluation_results.json) use native SWE-bench format.

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
    ├── swe-agent (patch generation)
    │   └── Connects to llama-server via /v1/chat/completions
    └── evaluator (SWE-bench harness)
        └── Mounts docker.sock to spawn test containers
```

## License

MIT
