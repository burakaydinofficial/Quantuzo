#!/usr/bin/env python3
"""
SWE-bench evaluation runner.
Evaluates generated patches using the SWE-bench harness.
"""

import json
import os
import subprocess
import sys
from importlib.metadata import version
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

    # Run SWE-bench evaluation (new API as of 2025)
    try:
        cmd = [
            "python", "-m", "swebench.harness.run_evaluation",
            "--predictions_path", str(predictions_file),
            "--run_id", run_id,
            "--dataset_name", dataset_name,
            "--max_workers", str(eval_workers),
            "--timeout", "900",
            "--report_dir", str(results_dir / "logs"),
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
        "swebench_version": version("swebench"),
        "total_instances": len(patches),
        "predictions_submitted": len(swebench_predictions),
        "resolved": 0,
        "failed": 0,
        "error": 0,
        "instances": []
    }

    # Look for evaluation results
    # swebench may write to report_dir, current dir, or results_dir
    eval_results_dir = results_dir / "logs"
    search_dirs = [
        eval_results_dir,           # --report_dir location
        Path.cwd(),                 # current working directory
        results_dir,                # results directory
    ]

    # Try to find the main report file
    # Format: {model_name}.{run_id}.json
    report_found = False
    report_patterns = [
        f"*.{run_id}.json",  # model.run_id.json
        "report.json",
        f"{run_id}.json",
        "results.json",
    ]

    report_file = None
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for pattern in report_patterns:
            matching_files = list(search_dir.glob(pattern))
            if matching_files:
                report_file = matching_files[0]
                break
        if report_file:
            break

    if report_file and report_file.exists():
        try:
            with open(report_file) as f:
                report = json.load(f)
                print(f"Found report: {report_file}")
                print(f"Report keys: {list(report.keys())}")

                # v3.0.17 format uses *_ids suffix (schema_version: 2)
                if "resolved_ids" in report:
                    results_summary["resolved"] = len(report.get("resolved_ids", []))
                    results_summary["failed"] = len(report.get("unresolved_ids", []))
                    results_summary["error"] = len(report.get("error_ids", []))
                    results_summary["instances"] = report
                    report_found = True
                # Older format without _ids suffix
                elif "resolved" in report and isinstance(report["resolved"], list):
                    results_summary["resolved"] = len(report["resolved"])
                    results_summary["failed"] = len(report.get("unresolved", []))
                    results_summary["error"] = len(report.get("error", []))
                    results_summary["instances"] = report
                    report_found = True
        except Exception as e:
            print(f"Error reading {report_file}: {e}")
    else:
        print(f"No report file found. Searched in: {[str(d) for d in search_dirs]}")
        print(f"Patterns: {report_patterns}")

    # Fallback: search recursively for per-instance results
    if not report_found and eval_results_dir.exists():
        for result_file in eval_results_dir.glob("**/*.json"):
            try:
                with open(result_file) as f:
                    instance_result = json.load(f)

                    # Handle different result formats
                    if "resolved" in instance_result:
                        results_summary["instances"].append(instance_result)
                        if instance_result.get("resolved"):
                            results_summary["resolved"] += 1
                        else:
                            results_summary["failed"] += 1
                    elif "status" in instance_result:
                        results_summary["instances"].append(instance_result)
                        status = instance_result["status"]
                        if status == "resolved":
                            results_summary["resolved"] += 1
                        elif status == "error":
                            results_summary["error"] += 1
                        else:
                            results_summary["failed"] += 1
            except Exception as e:
                # Skip non-JSON or malformed files
                pass

    # If still no results, check for run_instance.log files
    if results_summary["resolved"] == 0 and results_summary["failed"] == 0 and results_summary["error"] == 0:
        for log_file in eval_results_dir.glob("**/run_instance.log"):
            try:
                content = log_file.read_text()
                instance_id = log_file.parent.name
                if "Patch Apply Failed" in content or "FAILED" in content:
                    results_summary["error"] += 1
                    results_summary["instances"].append({"instance_id": instance_id, "status": "error"})
                elif "PASSED" in content:
                    results_summary["resolved"] += 1
                    results_summary["instances"].append({"instance_id": instance_id, "status": "resolved"})
                else:
                    results_summary["failed"] += 1
                    results_summary["instances"].append({"instance_id": instance_id, "status": "failed"})
            except Exception as e:
                pass

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
