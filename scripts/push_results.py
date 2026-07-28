#!/usr/bin/env python3
"""
Push benchmark run folders to a HuggingFace Dataset repository.

Uploads a run's artifacts only — it never edits the leaderboard. The leaderboard is
a DERIVED artifact, regenerated from every run's summary.json by --rebuild-leaderboard.

Usage:
    python3 scripts/push_results.py --run-id RUN_ID --pr  # Contribute a run as a PR
    python3 scripts/push_results.py --run-id RUN_ID       # Push to main (needs write access)
    python3 scripts/push_results.py --all --pr            # Contribute every local run
    python3 scripts/push_results.py --rebuild-leaderboard # Maintainer: regenerate the board

Requires HF_TOKEN (a normal token is enough for --pr; writing to main needs write access).
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
    # Bounded like the Action, so a token-bearing script never pulls an unvetted major.
    subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub>=0.20,<1.0"])
    from huggingface_hub import HfApi, hf_hub_download


sys.path.insert(0, str(Path(__file__).parent))
from leaderboard_lib import (  # noqa: E402
    LEADERBOARD_V2_FILE,
    RUNS_PREFIX,
    SUMMARY_FILE,
    build_leaderboard_row,
    build_leaderboard_rows_local,
    load_metadata,
    summary_matches_eval,
)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_REPO = "burakaydinofficial/Quantuzo"
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
+-- leaderboard.v2.jsonl       # One JSON row per run — DERIVED from runs/*/summary.json
+-- runs/
    +-- {run_id}/
        +-- metadata.json             # Run configuration
        +-- summary.json              # Self-describing leaderboard row (source for the board)
        +-- preds.json                # Agent predictions (keyed by instance_id)
        +-- swebench_predictions.json # SWE-bench harness format
        +-- evaluation_results.json   # Full evaluation results
        +-- {instance_id}/            # Per-instance trajectory data
        +-- run.log                   # Full run log
        +-- minisweagent.log          # Agent log
```

## Leaderboard Schema

Runs are contributed as Pull Requests that add only a `runs/{run_id}/` folder; the
leaderboard is regenerated from each run's `summary.json`. Each row in
`leaderboard.v2.jsonl` (identical to a run's `summary.json`, minus `schema_version`) contains:

| Field | Type | Description |
|-------|------|-------------|
| run_id | string | Unique run identifier |
| timestamp | string | ISO 8601 UTC timestamp |
| model_name | string | Model name |
| model_file | string | GGUF filename |
| kv_type_k | string | KV cache key type (f16, q8_0, q5_0, q5_1, q4_0, q4_1) |
| kv_type_v | string | KV cache value type (f16, q8_0, q5_0, q5_1, q4_0, q4_1) |
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
| f16-q8 | f16 | q8_0 | ~88% |
| f16-q4 | f16 | q4_0 | ~82% |
| q8 | q8_0 | q8_0 | ~75% |
| q5 | q5_0 | q5_0 | ~69% |
| q5_1 | q5_1 | q5_1 | ~69% |
| q8-q4 | q8_0 | q4_0 | ~69% |
| q4_1 | q4_1 | q4_1 | ~65% |
| q4 | q4_0 | q4_0 | ~63% |

## Usage

```python
from huggingface_hub import hf_hub_download
import json

# Download leaderboard
path = hf_hub_download(
    repo_id="burakaydinofficial/Quantuzo",
    filename="leaderboard.v2.jsonl",
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


def upload_leaderboard(api: HfApi, repo_id: str, rows: dict[str, dict], filename: str):
    """Upload a leaderboard file to HF from a dict of rows (sorted by timestamp)."""
    sorted_rows = sorted(rows.values(), key=lambda r: r.get("timestamp", ""))
    content = "\n".join(json.dumps(row, separators=(",", ":")) for row in sorted_rows)
    if content:
        content += "\n"

    buf = io.BytesIO(content.encode("utf-8"))
    api.upload_file(
        path_or_fileobj=buf,
        path_in_repo=filename,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Rebuild {filename}",
    )


# =============================================================================
# Push Operations
# =============================================================================

def _find_open_pr(api: HfApi, repo_id: str, title: str) -> int | None:
    """Return the number of an open PR with this exact title, else None.

    Filters client-side: get_repo_discussions' server-side type/status filters
    don't exist on older huggingface_hub (e.g. the ambient/unpinned one used by
    `run.sh --push`), so passing them would raise and silently open a duplicate PR.
    """
    try:
        for d in api.get_repo_discussions(repo_id=repo_id, repo_type="dataset"):
            if d.is_pull_request and d.status == "open" and d.title == title:
                return d.num
    except Exception as e:
        print(f"  WARNING: could not check for an existing PR ({e}); a duplicate may be opened")
    return None


def push_single_run(api: HfApi, repo_id: str, results_dir: Path, run_id: str,
                    dry_run: bool = False, as_pr: bool = False):
    """Push a single run's folder to HF. Folder-only — never edits the leaderboard.

    as_pr=True contributes via a PR (create_pr) instead of committing to main, and
    reuses an existing open PR for the same run_id so re-runs don't open duplicates.
    """
    run_dir = results_dir / run_id
    if not run_dir.is_dir():
        print(f"ERROR: Run directory not found: {run_dir}")
        return False
    if not load_metadata(run_dir):
        print(f"ERROR: No valid metadata.json in {run_dir}")
        return False

    print(f"Pushing: {run_id}" + (" (as PR)" if as_pr else ""))

    if dry_run:
        files = [f.relative_to(run_dir) for f in run_dir.rglob("*") if f.is_file()]
        files = [f for f in files if not str(f).startswith("testbed")]
        target = "a PR" if as_pr else "main"
        print(f"  Would upload {len(files)} files to {RUNS_PREFIX}/{run_id}/ on {target}")
        print("  Leaderboard NOT touched (derived separately via --rebuild-leaderboard)")
        return True

    title = f"Add run {run_id}"
    revision = None
    create_pr = False
    if as_pr:
        existing = _find_open_pr(api, repo_id, title)
        if existing is not None:
            revision = f"refs/pr/{existing}"
            print(f"  Updating existing PR #{existing}")
        else:
            create_pr = True

    info = api.upload_folder(
        folder_path=str(run_dir),
        path_in_repo=f"{RUNS_PREFIX}/{run_id}",
        repo_id=repo_id,
        repo_type="dataset",
        ignore_patterns=UPLOAD_EXCLUDE,
        commit_message=title,
        create_pr=create_pr,
        revision=revision,
    )
    if as_pr:
        # upload_folder returns a bare URL string on older hub, a CommitInfo on newer.
        pr_url = info if isinstance(info, str) else getattr(info, "pr_url", None)
        print(f"  PR ready: {pr_url or 'see repo discussions'}")
    else:
        print(f"  Uploaded artifacts to {RUNS_PREFIX}/{run_id}/")
    print("  Leaderboard not modified (run --rebuild-leaderboard to regenerate).")
    return True


def push_all_runs(api: HfApi, repo_id: str, results_dir: Path, dry_run: bool = False,
                  as_pr: bool = False):
    """Push all local result directories to HF."""
    if not results_dir.exists():
        print(f"No results directory: {results_dir}")
        return True  # nothing to push is a no-op, not a failure

    run_dirs = sorted([d for d in results_dir.iterdir() if d.is_dir()])
    if not run_dirs:
        print(f"No result directories found in: {results_dir}")
        return True

    print(f"Found {len(run_dirs)} run(s) in {results_dir}")
    print()

    success = 0
    failed = 0
    for run_dir in run_dirs:
        try:
            if push_single_run(api, repo_id, results_dir, run_dir.name, dry_run, as_pr):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1
        print()

    print(f"Done: {success} pushed, {failed} failed")
    return failed == 0


def rebuild_leaderboard(api: HfApi, repo_id: str, dry_run: bool = False):
    """Rebuild the derived leaderboard (v2) from each run's summary.json.

    Reads only runs/*/summary.json (+ evaluation_results.json to validate the
    numbers) — O(N) tiny files, no trajectory scan. Runs without a summary are
    SKIPPED and reported (owner runs generate_summary.py --fill-missing).
    """
    print(f"Rebuilding {LEADERBOARD_V2_FILE} from {repo_id} summaries...")
    try:
        all_files = set(api.list_repo_files(repo_id=repo_id, repo_type="dataset"))
    except Exception as e:
        # Fail loudly so the scheduled/manual Action turns red instead of green.
        print(f"ERROR: Could not list repo files: {e}")
        sys.exit(1)

    run_ids = sorted({
        f.split("/")[1] for f in all_files
        if f.startswith(f"{RUNS_PREFIX}/") and len(f.split("/")) >= 3
    })
    if not run_ids:
        print("No runs found under runs/")
        return

    rows: dict[str, dict] = {}
    missing: list[str] = []       # no summary.json
    unverified: list[str] = []    # summary but missing/inconsistent metadata or eval
    errors: list[str] = []        # present-but-unreadable file (excluded, but fail the job)
    mismatched: list = []

    def fetch(path):
        with open(hf_hub_download(repo_id=repo_id, filename=path, repo_type="dataset")) as f:
            return json.load(f)

    for run_id in run_ids:
        summary_path = f"{RUNS_PREFIX}/{run_id}/{SUMMARY_FILE}"
        if summary_path not in all_files:
            missing.append(run_id)
            continue
        try:
            summary = fetch(summary_path)
        except Exception as e:
            # One bad folder must not abort the whole rebuild (a cheap DoS on board
            # freshness) — exclude it, publish the rest, and fail the job at the end.
            print(f"  {run_id}: summary.json present but unreadable ({e}) — excluded")
            errors.append(run_id)
            continue
        if not isinstance(summary, dict):
            print(f"  {run_id}: summary.json is not a JSON object — skipping")
            missing.append(run_id)
            continue

        meta_path = f"{RUNS_PREFIX}/{run_id}/metadata.json"
        eval_path = f"{RUNS_PREFIX}/{run_id}/evaluation_results.json"
        if meta_path not in all_files or eval_path not in all_files:
            unverified.append(run_id)
            continue
        try:
            metadata, ev = fetch(meta_path), fetch(eval_path)
        except Exception as e:
            print(f"  {run_id}: metadata/evaluation_results.json unreadable ({e}) — excluded")
            errors.append(run_id)
            continue
        if not isinstance(metadata, dict) or not isinstance(ev, dict):
            unverified.append(run_id)
            continue
        if metadata.get("run_id") not in (None, run_id):
            print(f"  {run_id}: metadata.run_id ({metadata.get('run_id')!r}) != folder — skipping (possible spoof)")
            unverified.append(run_id)
            continue

        # Build the row from AUTHORITATIVE metadata+eval; the summary supplies only the
        # exit_statuses tally (expensive to recompute) and a staleness signal — so a stale
        # or tampered summary (e.g. a wrong KV label) can't reach the board.
        rows[run_id] = build_leaderboard_row(metadata, ev, summary.get("exit_statuses"))
        if summary_matches_eval(summary, ev):
            mismatched.append(run_id)
        print(f"  {run_id}: resolved={rows[run_id].get('resolved')}/{rows[run_id].get('total')}")

    if missing:
        print(f"\n  {len(missing)} run(s) SKIPPED — no summary.json "
              f"(pull them, then generate_summary.py --fill-missing):")
        for r in missing:
            print(f"    - {r}")
    if unverified:
        print(f"\n  {len(unverified)} run(s) SKIPPED — missing/inconsistent metadata or eval:")
        for r in unverified:
            print(f"    - {r}")
    if errors:
        print(f"\n  {len(errors)} run(s) EXCLUDED — present-but-unreadable files: {errors}")
    if mismatched:
        print(f"\n  {len(mismatched)} run(s) had a stale summary.json (row built from "
              f"metadata+eval anyway): {mismatched}")

    if not rows:
        print("\nERROR: no valid rows — refusing to overwrite the leaderboard with an empty board")
        sys.exit(1)
    if dry_run:
        print(f"\nWould write {len(rows)} rows to {LEADERBOARD_V2_FILE}")
        return

    upload_leaderboard(api, repo_id, rows, filename=LEADERBOARD_V2_FILE)
    print(f"\n{LEADERBOARD_V2_FILE} rebuilt: {len(rows)} rows")
    if errors:
        # Board published with the good runs; still fail so the Action turns red.
        print(f"{len(errors)} run(s) had unreadable files — failing the job.")
        sys.exit(1)


def rebuild_leaderboard_local(results_dir: Path, out_path: Path, dry_run: bool = False):
    """Rebuild the derived leaderboard from LOCAL runs/*/summary.json (no HF)."""
    if not results_dir.is_dir():
        print(f"No results directory: {results_dir}")
        return
    rows, missing, mismatched = build_leaderboard_rows_local(results_dir)
    for run_id in sorted(rows):
        print(f"  {run_id}: resolved={rows[run_id].get('resolved')}/{rows[run_id].get('total')}")
    if missing:
        print(f"\n  {len(missing)} run(s) SKIPPED — no summary.json (generate_summary.py --fill-missing):")
        for r in missing:
            print(f"    - {r}")
    if mismatched:
        print(f"\n  {len(mismatched)} run(s) had a stale summary.json "
              f"(row built from metadata+eval anyway): {mismatched}")

    sorted_rows = sorted(rows.values(), key=lambda r: r.get("timestamp", ""))
    content = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in sorted_rows)
    if dry_run:
        print(f"\nWould write {len(rows)} rows to {out_path}")
        return
    out_path.write_text(content)
    print(f"\n{out_path} written: {len(rows)} rows")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Push benchmark run folders to HuggingFace and rebuild the derived leaderboard"
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-id", help="Push a single run folder by its ID")
    mode.add_argument("--all", action="store_true", help="Push all local run folders")
    mode.add_argument("--rebuild-leaderboard", action="store_true",
                      help=f"Rebuild {LEADERBOARD_V2_FILE} from runs/*/summary.json")

    parser.add_argument("--pr", action="store_true",
                        help="Contribute run folder(s) via a PR (create_pr) instead of pushing to main")
    parser.add_argument("--local", action="store_true",
                        help="With --rebuild-leaderboard: build from local --results-dir and write locally (no HF)")
    parser.add_argument("--out", type=Path,
                        help=f"With --rebuild-leaderboard --local: output path (default: <results-dir>/../{LEADERBOARD_V2_FILE})")
    parser.add_argument("--repo", help=f"HuggingFace repo (default: {DEFAULT_REPO})")
    parser.add_argument("--results-dir", type=Path, default=Path("results"),
                        help="Local results directory (default: results)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without uploading/writing")

    args = parser.parse_args()

    # Resolve results directory
    if not args.results_dir.is_absolute():
        args.results_dir = Path(__file__).parent.parent / args.results_dir

    # Local rebuild needs no HF at all
    if args.rebuild_leaderboard and args.local:
        out = args.out or (args.results_dir.parent / LEADERBOARD_V2_FILE)
        rebuild_leaderboard_local(args.results_dir, out, args.dry_run)
        return

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
    # Propagate failure so callers (run.sh --push, CI) can tell a real contribution
    # from a silent no-op.
    if args.run_id:
        if not push_single_run(api, repo_id, args.results_dir, args.run_id, args.dry_run, args.pr):
            sys.exit(1)
    elif args.all:
        if not push_all_runs(api, repo_id, args.results_dir, args.dry_run, args.pr):
            sys.exit(1)
    elif args.rebuild_leaderboard:
        rebuild_leaderboard(api, repo_id, args.dry_run)


if __name__ == "__main__":
    main()
