#!/usr/bin/env python3
"""
SWE-bench evaluation runner.
Evaluates generated patches using the SWE-bench harness.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    # Configuration from environment
    run_id = os.environ.get("RUN_ID", "default")
    dataset_name = os.environ.get("DATASET", "princeton-nlp/SWE-bench_Lite")
    eval_workers = int(os.environ.get("EVAL_WORKERS", "8"))

    results_dir = Path("/results") / run_id
    patches_file = results_dir / "patches.json"
    output_file = results_dir / "evaluation_results.json"

    print(f"SWE-bench Evaluator")
    print(f"  Run ID: {run_id}")
    print(f"  Dataset: {dataset_name}")
    print(f"  Workers: {eval_workers}")
    print(f"  Patches: {patches_file}")

    if not patches_file.exists():
        print(f"Error: Patches file not found: {patches_file}")
        sys.exit(1)

    # Load patches
    with open(patches_file) as f:
        patches = json.load(f)

    print(f"Loaded {len(patches)} patches")

    # Convert to SWE-bench format
    swebench_predictions = []
    for patch in patches:
        if patch.get("status") == "success" and patch.get("model_patch"):
            swebench_predictions.append({
                "instance_id": patch["instance_id"],
                "model_name_or_path": patch.get("model_name_or_path", "unknown"),
                "model_patch": patch["model_patch"]
            })

    predictions_file = results_dir / "swebench_predictions.json"
    with open(predictions_file, "w") as f:
        json.dump(swebench_predictions, f, indent=2)

    print(f"Prepared {len(swebench_predictions)} predictions for evaluation")

    # Run SWE-bench evaluation
    try:
        cmd = [
            "python", "-m", "swebench.harness.run_evaluation",
            "--predictions_path", str(predictions_file),
            "--swe_bench_tasks", dataset_name,
            "--log_dir", str(results_dir / "logs"),
            "--testbed", str(results_dir / "testbed"),
            "--skip_existing",
            "--timeout", "900",
            "--num_processes", str(eval_workers)
        ]

        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=False, text=True)

        if result.returncode != 0:
            print(f"Warning: Evaluation returned non-zero exit code: {result.returncode}")

    except Exception as e:
        print(f"Error running evaluation: {e}")
        sys.exit(1)

    # Parse and summarize results
    results_summary = {
        "run_id": run_id,
        "dataset": dataset_name,
        "total_instances": len(patches),
        "predictions_submitted": len(swebench_predictions),
        "resolved": 0,
        "failed": 0,
        "error": 0,
        "instances": []
    }

    # Look for evaluation results
    eval_results_dir = results_dir / "logs"
    if eval_results_dir.exists():
        for result_file in eval_results_dir.glob("*.json"):
            try:
                with open(result_file) as f:
                    instance_result = json.load(f)
                    results_summary["instances"].append(instance_result)

                    status = instance_result.get("resolved", False)
                    if status:
                        results_summary["resolved"] += 1
                    else:
                        results_summary["failed"] += 1
            except Exception as e:
                print(f"Error reading {result_file}: {e}")
                results_summary["error"] += 1

    # Calculate resolution rate
    if results_summary["total_instances"] > 0:
        results_summary["resolution_rate"] = (
            results_summary["resolved"] / results_summary["total_instances"] * 100
        )
    else:
        results_summary["resolution_rate"] = 0.0

    # Save final results
    with open(output_file, "w") as f:
        json.dump(results_summary, f, indent=2)

    print(f"\n{'='*50}")
    print(f"Evaluation Complete")
    print(f"{'='*50}")
    print(f"Total instances: {results_summary['total_instances']}")
    print(f"Resolved: {results_summary['resolved']}")
    print(f"Failed: {results_summary['failed']}")
    print(f"Resolution rate: {results_summary['resolution_rate']:.1f}%")
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
