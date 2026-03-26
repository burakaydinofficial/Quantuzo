# Performance Tips

## GPU: Tuning PARALLEL and WORKERS

The defaults in `spec/runtime.conf` are conservative (`PARALLEL=1`, `WORKERS=1`). On GPU, you can increase both to utilize spare VRAM and process multiple SWE-bench instances concurrently.

- **PARALLEL** controls how many llama-server slots are allocated. Each slot reserves a full `CTX_SIZE` worth of KV cache memory.
- **WORKERS** controls how many SWE-agent instances run simultaneously. Works best when set equal to PARALLEL — each worker gets its own dedicated server slot.

### How to tune

1. Start with `PARALLEL=1`, `WORKERS=1` and note the tokens per second (TPS).
2. Increase both values incrementally (2, 3, 4...) until TPS drops to the **4-5 TPS range**.
3. That's the sweet spot — you're fully utilizing VRAM without starving individual requests.

The optimal values depend on:
- **Model size** — smaller models leave more headroom for parallelism
- **GPU VRAM** — each additional slot costs `CTX_SIZE * kv_cache_bytes_per_token`
- **KV quantization level** — lower quants (Q4, Q5) use less VRAM per slot, allowing more slots

### Context-dependent slowdown

Some models generate tokens fast at the start of a conversation but slow down significantly as context fills up. When tuning, test at **near-full context** (not just the first few turns) and make sure TPS stays above 4 even in that worst case. If a model drops below that threshold at high context, reduce PARALLEL/WORKERS.

### Override per model

Model configs in `spec/models/` can override runtime defaults. For example, a large model that can only sustain 1 slot:

```
# spec/models/qwen3.5-27b-q4.conf
MODEL_REPO=unsloth/Qwen3.5-27B-GGUF
MODEL_FILE=Qwen3.5-27B-Q4_K_M.gguf
MODEL_NAME=qwen3.5-27b-q4
PARALLEL=1
WORKERS=1
```

While a small model on a large GPU might handle more:

```
# spec/models/qwen3.5-4b-q4.conf
MODEL_REPO=unsloth/Qwen3.5-4B-GGUF
MODEL_FILE=Qwen3.5-4B-Q4_K_M.gguf
MODEL_NAME=qwen3.5-4b-q4
PARALLEL=4
WORKERS=4
```

## Pre-pulling SWE-bench Images

SWE-bench Docker images are large. If they're pulled on-demand during a run, the first instance of each project can hit timeouts. Pre-pull them:

```bash
./scripts/pull_images.sh princeton-nlp/SWE-bench_Lite
./scripts/pull_images.sh princeton-nlp/SWE-bench_Lite --filter "django|matplotlib"
```

## Evaluation Workers

`EVAL_WORKERS` controls how many SWE-bench test containers run in parallel during evaluation. This is independent of inference and is CPU/disk-bound. The default of 8 works well on most machines.

## Other Runtime Settings

These settings in `spec/runtime.conf` are less commonly tuned but available:

- **`FLASH_ATTN`** (default: `on`) — Flash attention mode for GPU inference. Options: `auto` (detect hardware support), `on` (force enable), `off` (disable). Note that q4_1, q5_0, q5_1 and asymmetric types (q8-q4, f16-q8, f16-q4) require `--cuda124` to work correctly.
- **`CACHE_RAM`** (default: `0`) — Prompt cache RAM limit in MiB. Controls how much memory the server uses for caching previous prompts. Set to `0` to disable (recommended — prompt caching adds overhead from matching new chats against cached ones, which slows down runs without benefit in this benchmark).
- **`EXTRA_LLAMA_ARGS`** — Extra arguments passed directly to llama-server. For example, `-nkvo` to offload KV cache to CPU.
