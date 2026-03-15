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
# spec/models/qwen3-32b.conf
MODEL_FILE=qwen3-32b-q4_k_m.gguf
MODEL_NAME=qwen3-32b
PARALLEL=1
WORKERS=1
```

While a small model on a large GPU might handle more:

```
# spec/models/qwen3-4b.conf
MODEL_FILE=qwen3-4b-q4_k_m.gguf
MODEL_NAME=qwen3-4b
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
