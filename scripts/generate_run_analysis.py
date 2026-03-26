#!/usr/bin/env python3
"""
Generate run-level rollup from per-instance analysis.json and steps.json files.

Produces a single run_analysis.json per run directory with aggregated failure
reasons, problem approach stats, loop detection, and limits/budget analysis.

Usage:
    python3 scripts/generate_run_analysis.py --run-id <run-id>
    python3 scripts/generate_run_analysis.py --all
"""

import argparse
import json
import math
import sys
from pathlib import Path


SCHEMA_VERSION = "1.0"

# Agent version -> (step_limit, cost_limit)
AGENT_LIMITS = {
    "v1": (100, 3.0),
    "v2": (250, 3.0),
}
COST_THRESHOLD = 0.95  # fraction of cost_limit to consider "cost-limited"


def coerce_int(value, default: int = 0, minimum: int = 0) -> int:
    """Coerce value to int safely for aggregation math."""
    if isinstance(value, int) and not isinstance(value, bool):
        return max(value, minimum)
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        try:
            return max(int(value), minimum)
        except (ValueError, OverflowError):
            return default
    if isinstance(value, str):
        try:
            return max(int(value), minimum)
        except ValueError:
            try:
                parsed = float(value)
                if not math.isfinite(parsed):
                    return default
                return max(int(parsed), minimum)
            except (ValueError, OverflowError):
                return default
    return default


def coerce_float(value, default: float = 0.0, minimum: float = 0.0) -> float:
    """Coerce value to float safely for limit checks."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        try:
            parsed = float(value)
        except (ValueError, OverflowError, TypeError):
            return default
        if not math.isfinite(parsed):
            return default
        return max(parsed, minimum)
    if isinstance(value, str):
        try:
            parsed = float(value)
            if not math.isfinite(parsed):
                return default
            return max(parsed, minimum)
        except (ValueError, OverflowError, TypeError):
            return default
    return default


def coerce_bool(value, default: bool = False) -> bool:
    """Coerce common boolean-like values; fallback to default."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    return default


VALID_FAILURE_REASONS = {
    "resolved",
    "submitted_incorrect",
    "context_overflow",
    "format_error_dominated",
    "exact_loop",
    "behavioral_loop",
    "wrong_target",
    "insufficient_capability",
}


def normalize_failure_reason(value) -> str:
    """Validate failure_reason against canonical enum, return 'unknown' if invalid."""
    if not isinstance(value, str) or value not in VALID_FAILURE_REASONS:
        return "unknown"
    return value


def load_metadata(run_dir: Path) -> dict:
    meta_path = run_dir / "metadata.json"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def get_limits(metadata: dict) -> tuple[int, float]:
    agent = metadata.get("agent", {})
    if not isinstance(agent, dict):
        agent = {}
    branch = agent.get("branch", "v1")
    if not isinstance(branch, str):
        branch = "v1"
    return AGENT_LIMITS.get(branch, AGENT_LIMITS["v1"])


def classify_limits(api_calls: int, cost: float, step_limit: int, cost_limit: float) -> set[str]:
    """Determine hard limits that were truly exceeded."""
    triggered = set()
    if cost >= cost_limit:
        triggered.add("cost")
    if api_calls >= step_limit:
        triggered.add("step")
    return triggered or {"unknown"}


def is_near_cost_limit(cost: float, cost_limit: float) -> bool:
    """Track near-budget behavior separately from hard limit exceedance."""
    return cost >= cost_limit * COST_THRESHOLD


def process_run(run_dir: Path) -> dict | None:
    """Aggregate all analysis.json + steps.json in a run directory."""
    analysis_files = sorted(run_dir.glob("*/*.analysis.json"))
    if not analysis_files:
        return None

    metadata = load_metadata(run_dir)
    step_limit, cost_limit = get_limits(metadata)

    # Counters
    failure_reasons: dict[str, int] = {}
    approach_totals = {
        "identified_correct_file": 0,
        "identified_root_cause": 0,
        "fix_attempted": 0,
        "had_viable_fix": 0,
        "distinct_strategies_sum": 0,
    }
    loop_count = 0
    loop_start_steps: list[int] = []

    # Limits analysis
    total_instances = 0
    skipped_instances = 0
    limits_exceeded = 0
    limit_type_counts = {"cost": 0, "step": 0, "unknown": 0}
    near_cost_limit_count = 0
    container_death_count = 0

    # "Blocked" = productive agent cut off (had_viable_fix=true, no behavioral loop)
    blocked_by_cost = []
    blocked_by_step = []
    blocked_by_container = []

    for analysis_path in analysis_files:
        instance_id = analysis_path.parent.name
        steps_path = analysis_path.with_name(
            analysis_path.name.replace(".analysis.json", ".steps.json")
        )

        try:
            with open(analysis_path, encoding="utf-8") as f:
                analysis = json.load(f)
            if not steps_path.exists():
                skipped_instances += 1
                continue
            with open(steps_path, encoding="utf-8") as f:
                steps_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARN: skipping {instance_id}: {e}")
            continue

        if not isinstance(analysis, dict):
            print(f"  WARN: skipping {instance_id}: analysis JSON root is not an object")
            continue
        if not isinstance(steps_data, dict):
            print(f"  WARN: skipping {instance_id}: steps JSON root is not an object")
            continue

        analysis_instance_id = analysis.get("instance_id")
        if isinstance(analysis_instance_id, str) and analysis_instance_id:
            if analysis_instance_id != instance_id:
                print(
                    "  WARN: instance_id mismatch "
                    f"(dir={instance_id}, analysis={analysis_instance_id})"
                )

        total_instances += 1
        stats = steps_data.get("stats", {})
        if not isinstance(stats, dict):
            stats = {}

        # --- Failure reasons ---
        fr = normalize_failure_reason(analysis.get("failure_reason", "unknown"))
        failure_reasons[fr] = failure_reasons.get(fr, 0) + 1

        # --- Problem approach ---
        pa = analysis.get("problem_approach", {})
        if not isinstance(pa, dict):
            pa = {}
        for key in ("identified_correct_file", "identified_root_cause", "fix_attempted", "had_viable_fix"):
            if coerce_bool(pa.get(key), default=False):
                approach_totals[key] += 1
        approach_totals["distinct_strategies_sum"] += coerce_int(
            pa.get("distinct_strategies", 0), default=0, minimum=0
        )

        # --- Behavioral loops ---
        bl = analysis.get("behavioral_loop", {})
        if not isinstance(bl, dict):
            bl = {}
        loop_detected = coerce_bool(bl.get("detected"), default=False)
        if loop_detected:
            loop_count += 1
            if isinstance(bl.get("start_step"), int) and not isinstance(bl.get("start_step"), bool):
                loop_start_steps.append(bl["start_step"])

        # --- Limits analysis ---
        exit_status = stats.get("exit_status", "")
        api_calls = coerce_int(stats.get("api_calls", 0), default=0, minimum=0)
        instance_cost = coerce_float(stats.get("instance_cost", 0), default=0.0, minimum=0.0)
        cd = stats.get("container_death", {})
        if not isinstance(cd, dict):
            cd = {}
        has_container_death = coerce_bool(cd.get("detected"), default=False)

        if has_container_death:
            container_death_count += 1

        if is_near_cost_limit(instance_cost, cost_limit):
            near_cost_limit_count += 1

        if exit_status == "LimitsExceeded":
            limits_exceeded += 1
            triggered = classify_limits(api_calls, instance_cost, step_limit, cost_limit)
            for lt in triggered:
                limit_type_counts[lt] += 1

        # --- Blocked detection ---
        # Agent was productive: had viable fix AND not in a behavioral loop
        was_productive = coerce_bool(pa.get("had_viable_fix"), default=False) and not loop_detected

        if was_productive and exit_status != "Submitted":
            base_entry = {
                "instance_id": instance_id,
                "api_calls": api_calls,
                "instance_cost": round(instance_cost, 2),
                "failure_reason": fr,
            }

            if has_container_death:
                blocked_by_container.append({
                    **base_entry,
                    "container_death_step": cd.get("step"),
                    "post_death_steps": cd.get("post_death_steps", 0),
                })

            if exit_status == "LimitsExceeded":
                triggered = classify_limits(api_calls, instance_cost, step_limit, cost_limit)
                if "cost" in triggered:
                    blocked_by_cost.append(base_entry.copy())
                if "step" in triggered:
                    blocked_by_step.append(base_entry.copy())

    # --- Build result ---
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_dir.name,
        "instance_count": total_instances,
        "skipped_instances": skipped_instances,
        "failure_reasons": dict(sorted(failure_reasons.items(), key=lambda x: -x[1])),
        "problem_approach": {
            "identified_correct_file": approach_totals["identified_correct_file"],
            "identified_root_cause": approach_totals["identified_root_cause"],
            "fix_attempted": approach_totals["fix_attempted"],
            "had_viable_fix": approach_totals["had_viable_fix"],
            "distinct_strategies_avg": round(
                approach_totals["distinct_strategies_sum"] / max(total_instances, 1), 2
            ),
        },
        "behavioral_loops": {
            "count": loop_count,
            "avg_start_step": round(sum(loop_start_steps) / len(loop_start_steps), 1)
            if loop_start_steps else None,
        },
        "limits_analysis": {
            "agent_limits": {
                "step_limit": step_limit,
                "cost_limit": cost_limit,
            },
            "limits_exceeded_count": limits_exceeded,
            "near_cost_limit_count": near_cost_limit_count,
            "limited_by": {
                "cost": limit_type_counts["cost"],
                "step": limit_type_counts["step"],
                "unknown": limit_type_counts["unknown"],
            },
            "container_death_count": container_death_count,
            "blocked_productive_agents": {
                "description": "Agents with had_viable_fix=true and no behavioral loop, cut off by environment limits (category counts may overlap)",
                "by_cost_limit": len(blocked_by_cost),
                "by_step_limit": len(blocked_by_step),
                "by_container_death": len(blocked_by_container),
                "unique_blocked_instances": len(
                    {
                        *[x["instance_id"] for x in blocked_by_cost],
                        *[x["instance_id"] for x in blocked_by_step],
                        *[x["instance_id"] for x in blocked_by_container],
                    }
                ),
                "instances": {
                    "cost_limited": blocked_by_cost,
                    "step_limited": blocked_by_step,
                    "container_death": blocked_by_container,
                },
            },
        },
    }

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate run-level analysis rollup from per-instance analysis.json files"
    )
    parser.add_argument("--run-id", help="Process a specific run")
    parser.add_argument("--all", action="store_true", help="Process all runs")
    parser.add_argument(
        "--results-dir", default="results", help="Results directory (default: results)"
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing run_analysis.json")

    args = parser.parse_args()
    results_dir = Path(args.results_dir)

    if not results_dir.exists() or not results_dir.is_dir():
        print(f"Invalid results directory: {results_dir}")
        sys.exit(1)

    if args.run_id:
        run_dirs = [results_dir / args.run_id]
    elif args.all:
        run_dirs = sorted(
            d for d in results_dir.iterdir()
            if d.is_dir() and d.name.startswith("swe-")
        )
    else:
        parser.print_help()
        sys.exit(1)

    for run_dir in run_dirs:
        if not run_dir.exists():
            print(f"Not found: {run_dir}")
            continue

        output_path = run_dir / "run_analysis.json"
        if output_path.exists() and not args.force:
            print(f"Skipping {run_dir.name} (run_analysis.json exists, use --force)")
            continue

        result = process_run(run_dir)
        if result is None:
            print(f"No analysis.json files in {run_dir.name}")
            continue

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        blocked = result["limits_analysis"]["blocked_productive_agents"]
        print(
            f"{run_dir.name}: {result['instance_count']} instances, "
            f"{result['failure_reasons'].get('resolved', 0)} resolved, "
            f"{blocked['unique_blocked_instances']} unique blocked "
            f"(cost={blocked['by_cost_limit']}, step={blocked['by_step_limit']}, container={blocked['by_container_death']})"
        )


if __name__ == "__main__":
    main()
