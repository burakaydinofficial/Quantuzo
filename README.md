# KV Cache Quantization Benchmark on SWE-bench

A reproducible Docker Compose setup to benchmark how KV cache quantization in llama.cpp affects coding accuracy on SWE-bench tasks. This project measures the trade-off between memory savings and model quality degradation when using quantized KV caches (Q8, Q5, Q4) compared to the F16 baseline.

## Results

All benchmark results are published to the [Quantuzo dataset on HuggingFace](https://huggingface.co/datasets/burakaydinofficial/Quantuzo), including full run artifacts, per-instance trajectories, and a structured leaderboard.

## Quick Start

> **Want to contribute benchmark results?** See the full [Contributing Benchmarks](docs/contributing-benchmarks.md) guide.

```bash
# 1. Download a model
./scripts/download_model.sh qwen3.5-4b-q4

# 2. Build images
docker compose build

# 3. Run benchmark
./scripts/run.sh --gpu --model qwen3.5-4b-q4 --kv f16 --dataset swe-lite
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
./scripts/run.sh --gpu --model qwen3.5-4b-q4 --kv q8 --dataset swe-lite
./scripts/run.sh --gpu -m qwen3.5-4b-q4 -k f16 -d swe-lite server
```

GPU mode:
- Uses pre-built `ghcr.io/ggml-org/llama.cpp:server-cuda` (no local build needed)
- Offloads all model layers to GPU (`--n-gpu-layers 999`)
- Enables flash attention for better performance
- Ignores CPU thread settings (irrelevant for GPU inference)

### All-Quant Flash Attention (CUDA 12.4)

The official CUDA image only supports flash attention for f16, q8_0, and q4_0 KV types. For q4_1, q5_0, q5_1, and asymmetric combinations (q8-q4, f16-q8, f16-q4), use the `--cuda124` flag which builds a custom image with `GGML_CUDA_FA_ALL_QUANTS=ON`:

```bash
./scripts/run.sh --cuda124 --model qwen3.5-4b-q4 --kv q5 --dataset swe-lite
```

Without this flag, these KV types may not work correctly.

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
│   ├── f16-q8.conf
│   ├── f16-q4.conf
│   ├── q8.conf
│   ├── q5.conf
│   ├── q5_1.conf
│   ├── q8-q4.conf
│   ├── q4.conf
│   └── q4_1.conf
└── datasets/
    ├── swe-lite.conf         # DATASET, DATASET_NAME, SUBSET
    ├── swe-full.conf
    └── swe-verified.conf
```

**Config merge order:** runtime → model (can override) → quantization → dataset

## Commands

```bash
# Full pipeline
./scripts/run.sh --model qwen3.5-4b-q4 --kv q8 --dataset swe-lite

# Short flags
./scripts/run.sh -m qwen3.5-4b-q4 -k q8 -d swe-lite

# Generate patches only
./scripts/run.sh -m qwen3.5-4b-q4 -k q8 -d swe-lite generate

# Evaluate existing patches
./scripts/run.sh -m qwen3.5-4b-q4 -k q8 -d swe-lite evaluate

# Quick validation with instance filter
./scripts/run.sh -m qwen3.5-4b-q4 -k f16 -d swe-lite --filter "django__django-11099|django__django-11179"

# Start llama-server for testing
./scripts/run.sh -m qwen3.5-4b-q4 -k q8 -d swe-lite server

# Utility commands (no config required)
./scripts/run.sh stop      # Stop all services
./scripts/run.sh logs      # Tail logs
./scripts/run.sh status    # Show containers + memory

# Run all KV configurations for a model
./scripts/run_all.sh --gpu --model qwen3.5-4b-q4

# Resume an interrupted run (skips completed instances)
./scripts/run.sh --gpu -m qwen3.5-4b-q4 -k q8 -d swe-lite --run-id EXISTING_RUN_ID generate
./scripts/run.sh --gpu -m qwen3.5-4b-q4 -k q8 -d swe-lite --run-id EXISTING_RUN_ID evaluate

# Auto-push results to HuggingFace after evaluation
./scripts/run.sh --gpu -m qwen3.5-4b-q4 -k q8 -d swe-lite --push

# Download a model (with validation and resume support)
./scripts/download_model.sh qwen3.5-4b-q4

# Pre-pull SWE-bench Docker images (prevents timeouts during runs)
./scripts/pull_images.sh princeton-nlp/SWE-bench_Lite

# Contribute results as a PR (folder only, no dataset write access needed)
python3 scripts/push_results.py --run-id RUN_ID --pr
python3 scripts/push_results.py --all --pr
python3 scripts/push_results.py --run-id RUN_ID --pr --dry-run
python3 scripts/push_results.py --rebuild-leaderboard  # Maintainer: regenerate leaderboard.v2.jsonl

# Pull results from HuggingFace
python3 scripts/pull_results.py --list             # List available runs
python3 scripts/pull_results.py --run-id RUN_ID    # Pull single run
python3 scripts/pull_results.py --all              # Pull all runs

# Analyze results
python3 scripts/analyze_results.py
python3 scripts/analyze_results.py --export-csv results.csv
python3 scripts/analyze_results.py --export-json results.json
python3 scripts/analyze_results.py --export-chart results.svg

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

## Publishing and Pulling Results

Results are published to [HuggingFace](https://huggingface.co/datasets/burakaydinofficial/Quantuzo). Contributors submit **only their run folder** as a Pull Request (no write access to the dataset needed); the leaderboard is regenerated from each run's `summary.json`. Use `--push` to open the PR automatically after evaluation, or do it manually:

```bash
# Contribute a run as a PR — folder only, a normal HF_TOKEN is enough
python3 scripts/push_results.py --run-id RUN_ID --pr
python3 scripts/push_results.py --all --pr

# Maintainer: regenerate the derived leaderboard (leaderboard.v2.jsonl) from summaries
python3 scripts/push_results.py --rebuild-leaderboard          # from HF (needs write access)
python3 scripts/push_results.py --rebuild-leaderboard --local  # from local results/

# Pull results from HuggingFace
python3 scripts/pull_results.py --list             # List available runs
python3 scripts/pull_results.py --run-id RUN_ID    # Pull single run
python3 scripts/pull_results.py --all              # Pull all runs
```

Both scripts support `--repo REPO` (or `HF_REPO` env var) to target a different HuggingFace repository.

**Maintainer note:** a run appears on the leaderboard only after its `summary.json` exists and a rebuild runs (the [rebuild-leaderboard Action](.github/workflows/rebuild-leaderboard.yml), or `make rebuild-leaderboard`). Fresh runs write `summary.json` automatically; for a run that lacks one (e.g. contributed from an older version), pull it, generate the summary, and push it back before rebuilding — the rebuild reads `summary.json` from the dataset, not from your disk:

```bash
python3 scripts/pull_results.py --run-id RUN_ID
python3 scripts/generate_summary.py --fill-missing
python3 scripts/push_results.py --run-id RUN_ID    # re-upload so the rebuild can see it
```

The rebuild reports any run it skipped for a missing (or eval-less, unverifiable) summary.

`validate_run.py` checks a run's *internal consistency* — counts, non-empty resolved patches, that a PR touches only its own folder, and that `summary.json` agrees with `evaluation_results.json`. It cannot verify the evaluation actually ran on the claimed configuration: descriptive fields (KV types, `ctx_size`, model, agent) are contributor-asserted, so it catches sloppy or accidental errors, not a carefully fabricated self-consistent run. Weigh cross-contributor comparisons accordingly.

## Adding New Models

1. Create a model config:
   ```bash
   cat > spec/models/my-model-q4.conf << 'EOF'
   MODEL_REPO=unsloth/My-Model-GGUF
   MODEL_FILE=My-Model-Q4_K_M.gguf
   MODEL_NAME=my-model-q4
   EOF
   ```

2. Download the model:
   ```bash
   ./scripts/download_model.sh my-model-q4
   ```

3. Run benchmarks:
   ```bash
   ./scripts/run_all.sh --gpu --model my-model-q4
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
- F16/Q8 and F16/Q4 asymmetric test V-only quantization with full-precision keys
- Q4 may show 2-5% degradation depending on the model

## Performance Tips

See [docs/performance-tips.md](docs/performance-tips.md) for GPU parallelism tuning, pre-pulling SWE-bench images, and other optimization tips.

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

## Dashboard

An interactive dashboard for exploring benchmark results is available at [HuggingFace Spaces](https://huggingface.co/spaces/burakaydinofficial/Quantuzo). It includes a leaderboard, per-run drill-down with agent trajectories and patch diffs, and model comparison charts (degradation curves, memory vs. accuracy).

For local development:
```bash
cd dashboard && npm run dev
```

## License

MIT
