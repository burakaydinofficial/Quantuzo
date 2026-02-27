#!/usr/bin/env python3
"""
Pull benchmark results from HuggingFace Dataset repository.

Usage:
    python3 scripts/pull_results.py --run-id RUN_ID   # Pull single run
    python3 scripts/pull_results.py --all              # Pull all runs
    python3 scripts/pull_results.py --list             # List available runs
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

try:
    from huggingface_hub import HfApi, snapshot_download
except ImportError:
    print("huggingface_hub not found, installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
    from huggingface_hub import HfApi, snapshot_download

DEFAULT_REPO = "burakaydinofficial/Quantuzo"
RUNS_PREFIX = "runs"


def list_runs(api, repo_id):
    """List all run IDs available on HF."""
    all_files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
    run_ids = set()
    for f in all_files:
        if f.startswith(f"{RUNS_PREFIX}/"):
            parts = f.split("/")
            if len(parts) >= 3:
                run_ids.add(parts[1])
    return sorted(run_ids)


def pull_run(api, repo_id, run_id, results_dir):
    """Pull a single run from HF to local results directory."""
    dest = results_dir / run_id
    if dest.exists():
        print(f"  Already exists: {dest} (skipping)")
        return True

    print(f"  Downloading: {run_id}")
    try:
        cache_dir = snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            allow_patterns=f"{RUNS_PREFIX}/{run_id}/*",
        )
        # snapshot_download puts files under cache_dir/runs/{run_id}/
        src = Path(cache_dir) / RUNS_PREFIX / run_id
        if not src.exists():
            print(f"  ERROR: Run not found in repo: {run_id}")
            return False

        # Copy from cache to results dir
        shutil.copytree(src, dest)
        print(f"  Saved to: {dest}")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Pull benchmark results from HuggingFace"
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-id", help="Pull a single run by its ID")
    mode.add_argument("--all", action="store_true", help="Pull all runs")
    mode.add_argument("--list", action="store_true", help="List available runs")

    parser.add_argument("--repo", default=None, help=f"HuggingFace repo (default: {DEFAULT_REPO})")
    parser.add_argument("--results-dir", type=Path, default=Path("results"), help="Local results directory (default: results)")

    args = parser.parse_args()

    if not args.results_dir.is_absolute():
        script_dir = Path(__file__).parent
        project_dir = script_dir.parent
        args.results_dir = project_dir / args.results_dir

    hf_token = os.environ.get("HF_TOKEN")
    api = HfApi(token=hf_token) if hf_token else HfApi()
    repo_id = args.repo or os.environ.get("HF_REPO") or DEFAULT_REPO

    print(f"Repository: {repo_id}")
    print()

    if args.list:
        runs = list_runs(api, repo_id)
        if not runs:
            print("No runs found.")
            return
        print(f"Available runs ({len(runs)}):")
        for r in runs:
            local = args.results_dir / r
            marker = " (local)" if local.exists() else ""
            print(f"  {r}{marker}")
        return

    args.results_dir.mkdir(parents=True, exist_ok=True)

    if args.run_id:
        pull_run(api, repo_id, args.run_id, args.results_dir)
    elif args.all:
        runs = list_runs(api, repo_id)
        if not runs:
            print("No runs found on HF.")
            return
        print(f"Found {len(runs)} run(s)")
        success = 0
        skipped = 0
        failed = 0
        for r in runs:
            if (args.results_dir / r).exists():
                print(f"  Already exists: {r} (skipping)")
                skipped += 1
            elif pull_run(api, repo_id, r, args.results_dir):
                success += 1
            else:
                failed += 1
        print(f"\nDone: {success} pulled, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
