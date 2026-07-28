#!/usr/bin/env python3
"""
Generate runs/<run_id>/summary.json for a benchmark run.

summary.json is a self-describing leaderboard row (see leaderboard_lib.py). It
lets the leaderboard be rebuilt from O(N) tiny files instead of scanning every
trajectory, and lets runs contribute without hand-editing a shared file.

Usage:
    python3 scripts/generate_summary.py <run_dir>          # one folder
    python3 scripts/generate_summary.py --run-id RUN_ID    # results/<RUN_ID>
    python3 scripts/generate_summary.py --all              # every run in results/
    python3 scripts/generate_summary.py --fill-missing     # only where absent/stale
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from leaderboard_lib import (  # noqa: E402
    SUMMARY_FILE,
    extract_eval_results,
    generate_summary,
    summary_matches_eval,
)


def needs_summary(run_dir: Path) -> bool:
    """True if summary.json is missing or disagrees with evaluation_results.json."""
    summary_path = run_dir / SUMMARY_FILE
    if not summary_path.exists():
        return True
    try:
        with open(summary_path) as f:
            summary = json.load(f)
    except (json.JSONDecodeError, IOError):
        return True
    return bool(summary_matches_eval(summary, extract_eval_results(run_dir)))


def write_summary(run_dir: Path) -> bool:
    """Generate and write summary.json for one run. Returns True on success."""
    try:
        summary = generate_summary(run_dir)
    except ValueError as e:
        print(f"  SKIP {run_dir.name}: {e}")
        return False
    with open(run_dir / SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  wrote {run_dir.name}/{SUMMARY_FILE}: "
          f"resolved={summary['resolved']}/{summary['total']} rate={summary['rate']:.2f}%")
    return True


def resolve_results_dir(results_dir: Path) -> Path:
    """Resolve a relative results dir against the project root (scripts/..)."""
    if not results_dir.is_absolute():
        return Path(__file__).parent.parent / results_dir
    return results_dir


def main():
    parser = argparse.ArgumentParser(description="Generate summary.json for benchmark runs")
    parser.add_argument("run_dir", nargs="?", help="Path to a single run directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run-id", help="Run id under --results-dir")
    mode.add_argument("--all", action="store_true", help="Every run in --results-dir")
    parser.add_argument("--fill-missing", action="store_true",
                        help="Only (re)generate summaries that are absent or disagree with eval")
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    args = parser.parse_args()

    results_dir = resolve_results_dir(args.results_dir)

    if args.run_dir:
        run_dirs = [Path(args.run_dir)]
    elif args.run_id:
        run_dirs = [results_dir / args.run_id]
    elif args.all or args.fill_missing:  # --fill-missing with no target means "all runs"
        if not results_dir.exists():
            print(f"No results directory: {results_dir}")
            return
        run_dirs = sorted(d for d in results_dir.iterdir() if d.is_dir())
    else:
        parser.print_help()
        sys.exit(1)

    written = skipped = failed = 0
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            print(f"  SKIP {run_dir}: not a directory")
            skipped += 1
            continue
        if args.fill_missing and not needs_summary(run_dir):
            skipped += 1
            continue
        if write_summary(run_dir):
            written += 1
        else:
            failed += 1

    print(f"\nDone: {written} written, {skipped} skipped, {failed} failed")
    # A named single target that couldn't produce a summary is an error, so callers
    # (e.g. run.sh --push) can warn instead of silently contributing a summary-less run.
    if failed and (args.run_dir or args.run_id):
        sys.exit(1)


if __name__ == "__main__":
    main()
