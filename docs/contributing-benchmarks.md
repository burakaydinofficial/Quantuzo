# Contributing Benchmarks

A quick start guide for running benchmarks and contributing results to Quantuzo.

## Prerequisites

- **Docker** with Docker Compose v2
- **NVIDIA GPU** (recommended) with [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed
- **Git** with `user.name` and `user.email` configured (used for contributor attribution in results)
- **~400GB free disk space** — SWE-bench Lite alone requires ~340GB for Docker images plus ~17GB for build cache. Model files add a few GB on top. Check usage with `docker system df`.

## 1. Clone the repo

```bash
git clone https://github.com/burakaydinofficial/Quantuzo.git
cd Quantuzo
```

## 2. Pick a model and download it

List available model configs:

```bash
ls spec/models/
```

Download a model:

```bash
./scripts/download_model.sh qwen3.5-4b-q4
```

This reads the model config from `spec/models/`, downloads the GGUF from HuggingFace, and validates the file.

## 3. Build the Docker images

```bash
docker compose build
```

## 4. Run a benchmark

Run the full pipeline (generate patches + evaluate) for a single KV configuration:

```bash
./scripts/run.sh --gpu -m qwen3.5-4b-q4 -k q8 -d swe-lite
```

Or run all KV configurations for a model:

```bash
./scripts/run_all.sh --gpu --model qwen3.5-4b-q4
```

For KV types that need all-quant flash attention (q4_1, q5_0, q5_1, q8-q4, f16-q8, f16-q4):

```bash
./scripts/run.sh --cuda124 -m qwen3.5-4b-q4 -k q5_1 -d swe-lite
```

### Resuming interrupted runs

If a run gets interrupted, resume it with `--run-id`:

```bash
# Find your run ID in results/
ls results/

# Resume — already-completed instances are skipped
./scripts/run.sh --gpu -m qwen3.5-4b-q4 -k q8 -d swe-lite --run-id EXISTING_RUN_ID generate
./scripts/run.sh --gpu -m qwen3.5-4b-q4 -k q8 -d swe-lite --run-id EXISTING_RUN_ID evaluate
```

## 5. Push results to HuggingFace

Set up a HuggingFace token with **write** access:

```bash
echo 'HF_TOKEN=hf_your_token_here' >> .env
```

Push results:

```bash
# Push a specific run
python3 scripts/push_results.py --run-id YOUR_RUN_ID

# Or push all unpushed results
python3 scripts/push_results.py --all

# Dry run to see what would be pushed
python3 scripts/push_results.py --all --dry-run
```

You can also auto-push after evaluation by adding `--push` to the run command:

```bash
./scripts/run.sh --gpu -m qwen3.5-4b-q4 -k q8 -d swe-lite --push
```

## 6. Verify on the dashboard

Check your results on the [Quantuzo dashboard](https://huggingface.co/spaces/burakaydinofficial/Quantuzo).

## Adding a new model

If the model you want to benchmark doesn't have a config yet:

1. Create a config in `spec/models/`:

```bash
cat > spec/models/my-model-q4.conf << 'EOF'
MODEL_REPO=unsloth/My-Model-GGUF
MODEL_FILE=My-Model-Q4_K_M.gguf
MODEL_NAME=my-model-q4
EOF
```

2. Download and run:

```bash
./scripts/download_model.sh my-model-q4
./scripts/run_all.sh --gpu --model my-model-q4
```

## Tips

- See [performance-tips.md](performance-tips.md) for tuning PARALLEL/WORKERS to maximize GPU utilization
- Pre-pull SWE-bench images before your first run to avoid timeouts: `./scripts/pull_images.sh princeton-nlp/SWE-bench_Lite`
- Results are stored locally in `results/` — you can inspect `metadata.json` and `evaluation_results.json` before pushing
- The `--filter` flag is useful for quick validation: `--filter "django__django-11099|django__django-11179"`
