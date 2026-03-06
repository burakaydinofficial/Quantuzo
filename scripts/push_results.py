#!/usr/bin/env python3
"""
Push benchmark results to HuggingFace Dataset repository.

Uploads full result artifacts and maintains a structured leaderboard.

Usage:
    python3 scripts/push_results.py --run-id RUN_ID     # Push single run
    python3 scripts/push_results.py --all                # Push all local results
    python3 scripts/push_results.py --rebuild-leaderboard # Rebuild from HF data

Requires HF_TOKEN environment variable.
"""

import argparse
import io
import json
import os
import sys
from pathlib import Path


# =============================================================================
# Auto-install huggingface_hub if missing
# =============================================================================

try:
    from huggingface_hub import HfApi, hf_hub_download
except ImportError:
    print("huggingface_hub not found, installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
    from huggingface_hub import HfApi, hf_hub_download


# =============================================================================
# Constants
# =============================================================================

DEFAULT_REPO = "burakaydinofficial/Quantuzo"
LEADERBOARD_FILE = "leaderboard.jsonl"
RUNS_PREFIX = "runs"
UPLOAD_EXCLUDE = ["testbed", "testbed/**"]

DATASET_CARD = """\
---
license: mit
task_categories:
  - text-generation
tags:
  - benchmark
  - llama-cpp
  - kv-cache
  - quantization
  - swe-bench
  - swe-agent
  - code-generation
pretty_name: "Quantuzo: KV Cache Quantization Benchmark"
---

# Quantuzo: KV Cache Quantization Benchmark

**Does KV cache quantization in llama.cpp hurt coding ability?**

Quantuzo measures the impact of KV cache quantization levels on real-world software engineering tasks using [SWE-bench](https://www.swebench.com/). Instead of synthetic benchmarks, models must actually browse repositories, understand code, write patches, and pass test suites.

## Motivation

KV cache quantization (q8_0, q5_0, q4_0, etc.) significantly reduces VRAM usage during inference, making it possible to run larger models or use longer contexts on limited hardware. But does this lossy compression degrade the model's ability to reason about code?

This dataset provides empirical answers by running identical SWE-bench evaluations across different KV cache configurations, keeping all other variables constant.

## Methodology

```
llama.cpp (KV cache quantization) -> OpenAI-compatible API -> mini-SWE-agent -> SWE-bench evaluation
```

1. **Inference**: [llama.cpp](https://github.com/ggerganov/llama.cpp) serves GGUF models with configurable KV cache quantization via `--cache-type-k` and `--cache-type-v`
2. **Agent**: [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) generates patches through an agent loop (browsing files, making edits, running tests)
3. **Evaluation**: [SWE-bench harness](https://github.com/princeton-nlp/SWE-bench) runs the generated patches against ground-truth test suites
4. **Context**: All runs use 64K token context to ensure comparability

## Dataset Structure

```
Quantuzo/
+-- README.md
+-- leaderboard.jsonl          # One JSON row per run (programmatic access)
+-- runs/
    +-- {run_id}/
        +-- metadata.json             # Run configuration
        +-- preds.json                # Agent predictions (keyed by instance_id)
        +-- swebench_predictions.json # SWE-bench harness format
        +-- evaluation_results.json   # Full evaluation results
        +-- {instance_id}/            # Per-instance trajectory data
        +-- run.log                   # Full run log
        +-- minisweagent.log          # Agent log
```

## Leaderboard Schema

Each row in `leaderboard.jsonl` contains:

| Field | Type | Description |
|-------|------|-------------|
| run_id | string | Unique run identifier |
| timestamp | string | ISO 8601 UTC timestamp |
| model_name | string | Model name |
| model_file | string | GGUF filename |
| kv_type_k | string | KV cache key type (f16, q8_0, q5_0, q4_0) |
| kv_type_v | string | KV cache value type (f16, q8_0, q5_0, q4_0) |
| ctx_size | int | Context size in tokens |
| accelerator | string | cpu or gpu |
| agent_version | string | mini-swe-agent version |
| agent_branch | string | Agent branch (v1/v2) |
| benchmark | string | Benchmark variant (swe-bench-lite, etc.) |
| total | int | Total instances in dataset |
| resolved | int | Instances where patch passes tests |
| failed | int | Instances where patch fails tests |
| error | int | Instances with evaluation errors |
| rate | float | Resolution rate (%) |
| exit_statuses | object | Agent exit status counts (Submitted, LimitsExceeded, etc.) |

## KV Cache Configurations

| Config | KV_TYPE_K | KV_TYPE_V | Relative Memory |
|--------|-----------|-----------|-----------------|
| f16 | f16 | f16 | 100% (baseline) |
| q8 | q8_0 | q8_0 | ~75% |
| q5 | q5_0 | q5_0 | ~69% |
| q8-q4 | q8_0 | q4_0 | ~69% |
| q4 | q4_0 | q4_0 | ~63% |

## Usage

```python
from huggingface_hub import hf_hub_download
import json

# Download leaderboard
path = hf_hub_download(
    repo_id="burakaydinofficial/Quantuzo",
    filename="leaderboard.jsonl",
    repo_type="dataset",
)

with open(path) as f:
    runs = [json.loads(line) for line in f]

for run in runs:
    print(f"{run['model_name']} KV:{run['kv_type_k']}/{run['kv_type_v']} -> {run['resolved']}/{run['total']} ({run['rate']:.1f}%)")
```

## Source Code

The full benchmarking infrastructure is open source: [github.com/burakaydinofficial/Quantuzo](https://github.com/burakaydinofficial/Quantuzo)

## License

MIT
"""


# =============================================================================
# Helpers
# =============================================================================

def load_metadata(result_dir: Path) -> dict | None:
    """Load metadata.json from a result directory."""
    metadata_file = result_dir / "metadata.json"
    if not metadata_file.exists():
        return None
    try:
        with open(metadata_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def extract_eval_results(result_dir: Path) -> dict | None:
    """Extract evaluation results from a result directory."""
    eval_file = result_dir / "evaluation_results.json"
    if not eval_file.exists():
        return None
    try:
        with open(eval_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def extract_exit_statuses(result_dir: Path) -> dict[str, int]:
    """Count exit statuses from trajectory files in a result directory."""
    counts: dict[str, int] = {}
    for traj_file in result_dir.glob("*/*.traj.json"):
        try:
            with open(traj_file) as f:
                traj = json.load(f)
            status = traj.get("info", {}).get("exit_status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        except (json.JSONDecodeError, IOError):
            counts["parse_error"] = counts.get("parse_error", 0) + 1
    return counts


def build_leaderboard_row(
    metadata: dict,
    eval_results: dict | None,
    exit_statuses: dict[str, int] | None = None,
) -> dict:
    """Build a flat leaderboard row from metadata and evaluation results."""
    model = metadata.get("model", {})
    inference = metadata.get("inference", {})
    agent = metadata.get("agent", {})

    row = {
        "run_id": metadata.get("run_id", ""),
        "timestamp": metadata.get("timestamp", ""),
        "model_name": model.get("name", ""),
        "model_file": model.get("file", ""),
        "kv_type_k": inference.get("kv_type_k", ""),
        "kv_type_v": inference.get("kv_type_v", ""),
        "ctx_size": inference.get("ctx_size", 0),
        "accelerator": inference.get("accelerator", ""),
        "agent_version": agent.get("version", ""),
        "agent_branch": agent.get("branch", ""),
        "benchmark": metadata.get("benchmark", ""),
        "total": 0,
        "resolved": 0,
        "failed": 0,
        "error": 0,
        "rate": 0.0,
    }

    if eval_results:
        row["total"] = eval_results.get("total_instances", 0)
        row["resolved"] = eval_results.get("resolved", 0)
        row["failed"] = eval_results.get("failed", 0)
        row["error"] = eval_results.get("error", 0)
        row["rate"] = eval_results.get("resolution_rate", 0.0)

    if exit_statuses:
        row["exit_statuses"] = exit_statuses

    return row


def ensure_repo(api: HfApi, repo_id: str):
    """Create the HF dataset repo if it doesn't exist."""
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset")
    except Exception:
        print(f"Creating dataset repo: {repo_id}")
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=False)
        # Upload dataset card
        api.upload_file(
            path_or_fileobj=DATASET_CARD.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
        )


def download_leaderboard(api: HfApi, repo_id: str) -> dict[str, dict]:
    """Download current leaderboard.jsonl from HF, return dict keyed by run_id."""
    rows = {}
    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=LEADERBOARD_FILE,
            repo_type="dataset",
        )
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    rows[row["run_id"]] = row
    except Exception:
        # File doesn't exist yet, that's fine
        pass
    return rows


def upload_leaderboard(api: HfApi, repo_id: str, rows: dict[str, dict]):
    """Upload leaderboard.jsonl to HF from dict of rows."""
    # Sort by timestamp
    sorted_rows = sorted(rows.values(), key=lambda r: r.get("timestamp", ""))
    content = "\n".join(json.dumps(row, separators=(",", ":")) for row in sorted_rows)
    if content:
        content += "\n"

    buf = io.BytesIO(content.encode("utf-8"))
    api.upload_file(
        path_or_fileobj=buf,
        path_in_repo=LEADERBOARD_FILE,
        repo_id=repo_id,
        repo_type="dataset",
    )


# =============================================================================
# Push Operations
# =============================================================================

def push_single_run(api: HfApi, repo_id: str, results_dir: Path, run_id: str, dry_run: bool = False):
    """Push a single run's results to HF."""
    run_dir = results_dir / run_id
    if not run_dir.is_dir():
        print(f"ERROR: Run directory not found: {run_dir}")
        return False

    metadata = load_metadata(run_dir)
    if not metadata:
        print(f"ERROR: No valid metadata.json in {run_dir}")
        return False

    print(f"Pushing: {run_id}")

    exit_statuses = extract_exit_statuses(run_dir)

    if dry_run:
        files = [f.relative_to(run_dir) for f in run_dir.rglob("*") if f.is_file()]
        # Filter out testbed
        files = [f for f in files if not str(f).startswith("testbed")]
        print(f"  Would upload {len(files)} files to {RUNS_PREFIX}/{run_id}/")
        eval_results = extract_eval_results(run_dir)
        if eval_results:
            row = build_leaderboard_row(metadata, eval_results, exit_statuses)
            print(f"  Would upsert leaderboard row: resolved={row['resolved']}/{row['total']} rate={row['rate']}%")
            if exit_statuses:
                print(f"  Exit statuses: {exit_statuses}")
        else:
            print(f"  No evaluation_results.json — leaderboard not updated")
        return True

    # Upload entire run folder
    api.upload_folder(
        folder_path=str(run_dir),
        path_in_repo=f"{RUNS_PREFIX}/{run_id}",
        repo_id=repo_id,
        repo_type="dataset",
        ignore_patterns=UPLOAD_EXCLUDE,
    )
    print(f"  Uploaded artifacts to {RUNS_PREFIX}/{run_id}/")

    # Update leaderboard if evaluation results exist
    eval_results = extract_eval_results(run_dir)
    if eval_results:
        rows = download_leaderboard(api, repo_id)
        row = build_leaderboard_row(metadata, eval_results, exit_statuses)
        rows[run_id] = row
        upload_leaderboard(api, repo_id, rows)
        print(f"  Leaderboard updated: resolved={row['resolved']}/{row['total']} rate={row['rate']}%")
        if exit_statuses:
            print(f"  Exit statuses: {exit_statuses}")
    else:
        print(f"  No evaluation_results.json — leaderboard not updated")

    return True


def push_all_runs(api: HfApi, repo_id: str, results_dir: Path, dry_run: bool = False):
    """Push all local result directories to HF."""
    if not results_dir.exists():
        print(f"No results directory: {results_dir}")
        return

    run_dirs = sorted([d for d in results_dir.iterdir() if d.is_dir()])
    if not run_dirs:
        print(f"No result directories found in: {results_dir}")
        return

    print(f"Found {len(run_dirs)} run(s) in {results_dir}")
    print()

    success = 0
    failed = 0
    for run_dir in run_dirs:
        try:
            if push_single_run(api, repo_id, results_dir, run_dir.name, dry_run):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1
        print()

    print(f"Done: {success} pushed, {failed} failed")


def rebuild_leaderboard(api: HfApi, repo_id: str, dry_run: bool = False):
    """Rebuild leaderboard.jsonl from HF run data."""
    print(f"Rebuilding leaderboard from {repo_id}...")

    # List all files and find metadata.json under runs/
    try:
        all_files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
    except Exception as e:
        print(f"ERROR: Could not list repo files: {e}")
        return

    metadata_files = [f for f in all_files if f.startswith(f"{RUNS_PREFIX}/") and f.endswith("/metadata.json")]

    if not metadata_files:
        print("No metadata.json files found under runs/")
        return

    print(f"Found {len(metadata_files)} run(s)")
    rows = {}

    for meta_path in metadata_files:
        # meta_path is like "runs/RUN_ID/metadata.json"
        parts = meta_path.split("/")
        if len(parts) < 3:
            continue
        run_id = parts[1]

        try:
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=meta_path,
                repo_type="dataset",
            )
            with open(local_path) as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"  Skipping {run_id}: could not load metadata ({e})")
            continue

        # Try to download evaluation_results.json
        eval_results = None
        eval_path = f"{RUNS_PREFIX}/{run_id}/evaluation_results.json"
        try:
            local_eval_path = hf_hub_download(
                repo_id=repo_id,
                filename=eval_path,
                repo_type="dataset",
            )
            with open(local_eval_path) as f:
                eval_results = json.load(f)
        except Exception:
            pass

        # Extract exit statuses from trajectory files
        exit_statuses: dict[str, int] = {}
        traj_files = [f for f in all_files if f.startswith(f"{RUNS_PREFIX}/{run_id}/") and f.endswith(".traj.json")]
        for traj_path in traj_files:
            try:
                local_traj = hf_hub_download(
                    repo_id=repo_id,
                    filename=traj_path,
                    repo_type="dataset",
                )
                with open(local_traj) as f:
                    traj = json.load(f)
                status_val = traj.get("info", {}).get("exit_status", "unknown")
                exit_statuses[status_val] = exit_statuses.get(status_val, 0) + 1
            except Exception:
                exit_statuses["parse_error"] = exit_statuses.get("parse_error", 0) + 1

        row = build_leaderboard_row(metadata, eval_results, exit_statuses or None)
        rows[run_id] = row
        status = f"resolved={row['resolved']}/{row['total']}" if eval_results else "no eval"
        print(f"  {run_id}: {status}")
        if exit_statuses:
            print(f"    exit_statuses: {exit_statuses}")

    if dry_run:
        print(f"\nWould write {len(rows)} rows to {LEADERBOARD_FILE}")
        return

    upload_leaderboard(api, repo_id, rows)
    print(f"\nLeaderboard rebuilt: {len(rows)} rows")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Push benchmark results to HuggingFace"
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--run-id",
        help="Push a single run by its ID",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Push all local result directories",
    )
    mode.add_argument(
        "--rebuild-leaderboard",
        action="store_true",
        help="Rebuild leaderboard.jsonl from HF run data",
    )

    parser.add_argument(
        "--repo",
        help=f"HuggingFace repo (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Local results directory (default: results)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without uploading",
    )

    args = parser.parse_args()

    # Resolve results directory
    if not args.results_dir.is_absolute():
        script_dir = Path(__file__).parent
        project_dir = script_dir.parent
        args.results_dir = project_dir / args.results_dir

    # Initialize API (uses HF_TOKEN env var or stored token from `huggingface-cli login`)
    hf_token = os.environ.get("HF_TOKEN")
    api = HfApi(token=hf_token) if hf_token else HfApi()

    # Determine repo ID
    repo_id = args.repo or os.environ.get("HF_REPO") or DEFAULT_REPO

    print(f"Repository: {repo_id}")
    print()

    # Ensure repo exists (skip for dry run without token)
    if not args.dry_run:
        ensure_repo(api, repo_id)

    # Execute
    if args.run_id:
        push_single_run(api, repo_id, args.results_dir, args.run_id, args.dry_run)
    elif args.all:
        push_all_runs(api, repo_id, args.results_dir, args.dry_run)
    elif args.rebuild_leaderboard:
        rebuild_leaderboard(api, repo_id, args.dry_run)


if __name__ == "__main__":
    main()
