# Benchmark Results

KV Cache Quantization benchmark results on SWE-bench.

## Results Log

| Date | Model | KV Cache | Dataset | Submitted | Resolved | Rate | Errors | Run ID |
|------|-------|----------|---------|-----------|----------|------|--------|--------|
| 2026-01-31 | qwen3-4b-instruct-2507 | f16/f16 | SWE-bench Lite | 159/300 | 8 | 2.67% | 55 | swe-lite-qwen3-4b-instruct-2507-kv-f16-f16-20260131_080149 |
| 2026-01-27 | qwen3-4b-instruct-2507 | q8_0/q8_0 | SWE-bench Lite | 185/300 | 5 | 1.67% | 65 | swe-lite-qwen3-4b-instruct-2507-kv-q8-q8-20260127_125632 |
| 2026-01-27 | qwen3-4b-instruct-2507 | q4_0/q4_0 | SWE-bench Lite | 155/300 | 3 | 1.00% | 48 | swe-lite-qwen3-4b-instruct-2507-kv-q4-q4-20260127_125803 |

## Column Definitions

- **Date**: Run start date
- **Model**: Model name and quantization (weights)
- **KV Cache**: KV cache quantization (K type / V type)
- **Dataset**: SWE-bench variant used
- **Submitted**: Patches submitted / Total instances
- **Resolved**: Instances where patch fixed the issue
- **Rate**: Resolution rate (Resolved / Total)
- **Errors**: Instances that errored during evaluation
- **Run ID**: Full run identifier for reference

## Notes

- All runs use 64K context size
- Resolution rate calculated against total instances (300 for Lite)
- Errors typically indicate Docker image issues or test environment problems
- Instances not submitted had empty patches (agent failed to produce a fix)
