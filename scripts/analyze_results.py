#!/usr/bin/env python3
"""
Analyze and compare benchmark results across runs.
Groups results by benchmark type and uses appropriate extractors.
"""

import argparse
import csv
import json
import sys
from pathlib import Path


# =============================================================================
# Benchmark Extractors
# =============================================================================

def extract_swebench_results(result_dir: Path) -> dict | None:
    """Extract results from SWE-bench format (works for all variants)."""
    eval_file = result_dir / "evaluation_results.json"
    if not eval_file.exists():
        return None

    try:
        with open(eval_file) as f:
            data = json.load(f)

        return {
            "total": data.get("total_instances", 0),
            "resolved": data.get("resolved", 0),
            "failed": data.get("failed", 0),
            "rate": data.get("resolution_rate", 0.0),
        }
    except (json.JSONDecodeError, KeyError):
        return None


# Map benchmark types to extractors
# SWE-bench variants all use the same format
EXTRACTORS = {
    "swe-bench": extract_swebench_results,
    "swe-bench-lite": extract_swebench_results,
    "swe-bench-full": extract_swebench_results,
    "swe-bench-verified": extract_swebench_results,
}


# =============================================================================
# Results Loading
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


def load_all_results(results_dir: Path) -> dict[str, list[dict]]:
    """
    Load all results, grouped by benchmark type.
    Returns: {"swe-bench-lite": [result1, result2, ...], ...}
    """
    grouped = {}

    if not results_dir.exists():
        return grouped

    for run_dir in results_dir.iterdir():
        if not run_dir.is_dir():
            continue

        # Load metadata
        metadata = load_metadata(run_dir)
        if not metadata:
            continue

        benchmark = metadata.get("benchmark", "unknown")
        extractor = EXTRACTORS.get(benchmark)
        if not extractor:
            # Unknown benchmark type, skip
            continue

        # Extract benchmark-specific results
        results = extractor(run_dir)
        if not results:
            continue

        # Combine metadata and results
        entry = {
            "run_id": metadata.get("run_id", run_dir.name),
            "timestamp": metadata.get("timestamp", ""),
            "contributor": metadata.get("contributor", {}),
            "model": metadata.get("model", {}),
            "inference": metadata.get("inference", {}),
            "benchmark": benchmark,
            "dataset": metadata.get("dataset", ""),
            "results": results,
            "run_dir": str(run_dir),
        }

        if benchmark not in grouped:
            grouped[benchmark] = []
        grouped[benchmark].append(entry)

    return grouped


# =============================================================================
# Display Functions
# =============================================================================

def get_kv_config(entry: dict) -> str:
    """Extract KV config string from entry."""
    inference = entry.get("inference", {})
    kv_k = inference.get("kv_type_k", "?")
    kv_v = inference.get("kv_type_v", "?")
    return f"K:{kv_k}/V:{kv_v}"


def print_swebench_table(results: list[dict], benchmark: str):
    """Print results table for SWE-bench variants."""
    if not results:
        return

    # Sort by rate descending
    results = sorted(results, key=lambda x: x["results"].get("rate", 0), reverse=True)

    # Find baseline (f16/f16)
    baseline_rate = None
    for r in results:
        inf = r.get("inference", {})
        if inf.get("kv_type_k") == "f16" and inf.get("kv_type_v") == "f16":
            baseline_rate = r["results"].get("rate", 0)
            break

    # If no f16 baseline, use highest rate
    if baseline_rate is None and results:
        baseline_rate = results[0]["results"].get("rate", 0)

    # Print header
    print(f"\n{'=' * 90}")
    print(f"Benchmark: {benchmark}")
    print(f"{'=' * 90}")
    print(f"\n{'Run ID':<45} {'KV Config':<15} {'Resolved':<10} {'Rate':<10} {'Δ Baseline':<10}")
    print("-" * 90)

    for r in results:
        run_id = r.get("run_id", "unknown")
        # Truncate long run_ids
        if len(run_id) > 43:
            run_id = run_id[:40] + "..."

        kv_config = get_kv_config(r)
        resolved = r["results"].get("resolved", 0)
        rate = r["results"].get("rate", 0)

        if baseline_rate and baseline_rate > 0:
            delta = rate - baseline_rate
            delta_str = f"{delta:+.1f}%" if abs(delta) > 0.01 else "-"
        else:
            delta_str = "-"

        print(f"{run_id:<45} {kv_config:<15} {resolved:<10} {rate:<9.1f}% {delta_str:<10}")

    print("-" * 90)


def print_summary(grouped_results: dict[str, list[dict]]):
    """Print summary tables for all benchmark types."""
    if not grouped_results:
        print("No results found.")
        return

    for benchmark, results in sorted(grouped_results.items()):
        # Use appropriate printer based on benchmark
        if benchmark.startswith("swe-bench"):
            print_swebench_table(results, benchmark)
        else:
            # Generic fallback (shouldn't happen with current extractors)
            print(f"\n{benchmark}: {len(results)} results (no display handler)")


# =============================================================================
# Export Functions
# =============================================================================

def export_csv(grouped_results: dict[str, list[dict]], output_file: Path):
    """Export results to CSV."""
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "benchmark", "run_id", "timestamp", "contributor",
            "model", "kv_type_k", "kv_type_v", "resolved", "total", "rate"
        ])

        for benchmark, results in grouped_results.items():
            for r in results:
                writer.writerow([
                    benchmark,
                    r.get("run_id", ""),
                    r.get("timestamp", ""),
                    r.get("contributor", {}).get("name", ""),
                    r.get("model", {}).get("name", ""),
                    r.get("inference", {}).get("kv_type_k", ""),
                    r.get("inference", {}).get("kv_type_v", ""),
                    r["results"].get("resolved", 0),
                    r["results"].get("total", 0),
                    r["results"].get("rate", 0),
                ])

    print(f"Exported CSV to: {output_file}")


def export_json(grouped_results: dict[str, list[dict]], output_file: Path):
    """Export results to JSON."""
    # Flatten for export
    export_data = []
    for benchmark, results in grouped_results.items():
        for r in results:
            export_data.append({
                "benchmark": benchmark,
                "run_id": r.get("run_id"),
                "timestamp": r.get("timestamp"),
                "contributor": r.get("contributor"),
                "model": r.get("model"),
                "inference": r.get("inference"),
                "results": r.get("results"),
            })

    with open(output_file, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported JSON to: {output_file}")


def export_chart(grouped_results: dict[str, list[dict]], output_file: Path):
    """Export results as bar chart."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Error: matplotlib not installed. Install with: pip install matplotlib")
        return

    # Flatten all swe-bench results for chart
    swe_results = []
    for benchmark, results in grouped_results.items():
        if benchmark.startswith("swe-bench"):
            swe_results.extend(results)

    if not swe_results:
        print("No SWE-bench results to chart.")
        return

    # Sort by KV config for consistent ordering
    swe_results = sorted(swe_results, key=lambda x: get_kv_config(x))

    labels = []
    rates = []

    for r in swe_results:
        kv_config = get_kv_config(r)
        model = r.get("model", {}).get("name", "?")
        labels.append(f"{model}\n{kv_config}")
        rates.append(r["results"].get("rate", 0))

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(labels, rates, color="steelblue", edgecolor="black")

    # Add value labels on bars
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{rate:.1f}%", ha="center", va="bottom", fontsize=9)

    ax.set_ylabel("Resolution Rate (%)")
    ax.set_xlabel("Model / KV Cache Configuration")
    ax.set_title("SWE-bench Resolution Rate by KV Cache Quantization")
    ax.set_ylim(0, max(rates) * 1.15 if rates else 100)

    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    print(f"Exported chart to: {output_file}")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Analyze benchmark results across runs"
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing results (default: results)"
    )
    parser.add_argument(
        "--export-csv",
        type=Path,
        metavar="FILE",
        help="Export results to CSV file"
    )
    parser.add_argument(
        "--export-json",
        type=Path,
        metavar="FILE",
        help="Export results to JSON file"
    )
    parser.add_argument(
        "--export-chart",
        type=Path,
        metavar="FILE",
        help="Export results as bar chart (SVG/PNG)"
    )

    args = parser.parse_args()

    # Resolve results directory
    if not args.results_dir.is_absolute():
        script_dir = Path(__file__).parent
        project_dir = script_dir.parent
        args.results_dir = project_dir / args.results_dir

    # Load results
    grouped_results = load_all_results(args.results_dir)

    if not grouped_results:
        print(f"No results found in: {args.results_dir}")
        print("Run benchmarks first with: ./scripts/run.sh -m qwen3-4b -k f16 -d swe-lite")
        sys.exit(0)  # Exit cleanly, not an error

    # Print summary
    print_summary(grouped_results)

    # Export if requested
    if args.export_csv:
        export_csv(grouped_results, args.export_csv)

    if args.export_json:
        export_json(grouped_results, args.export_json)

    if args.export_chart:
        export_chart(grouped_results, args.export_chart)


if __name__ == "__main__":
    main()
