#!/usr/bin/env python3
"""
Phase 1: Extract compact step logs from trajectory files.

Reads *.traj.json files and produces *.steps.json files with:
- Compact command sequence with timing and cost
- Compressed repeated output content
- Collapsed post-container-death steps
- Collapsed format error bursts
- Deterministic statistics (timing, counts)

The steps.json files are designed to be consumed by an LLM in Phase 2
for qualitative analysis (loop detection, failure classification, etc.).

Usage:
    python3 scripts/extract_steps.py --run-id <run-id>
    python3 scripts/extract_steps.py --all
    python3 scripts/extract_steps.py <path/to/instance.traj.json>
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "1.3"
SCRIPT_VERSION = "1.3"

# --- Output compression ---

CONTAINER_DEATH_PATTERNS = [
    "No such container",
    "Error response from daemon",
    "is not running",
]

FORMAT_ERROR_MARKERS = [
    "Please always provide EXACTLY ONE action",
    "Please format your action",
    "found 0 actions",
]

# Minimum thresholds for repeat compression
MIN_REPEATS = 3
MIN_TOTAL_LEN = 60


def compress_repeats(text: str) -> str:
    """Compress repeated patterns in text output.

    Two passes:
    1. Consecutive identical lines
    2. Character-level tandem repeats via regex backreference
    """
    if not text or len(text) < MIN_TOTAL_LEN:
        return text

    # Pass 1: Consecutive identical lines
    lines = text.split("\n")
    compressed_lines: list[str] = []
    i = 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and lines[j] == lines[i]:
            j += 1
        count = j - i
        total_len = count * (len(lines[i]) + 1)
        if count >= MIN_REPEATS and total_len >= MIN_TOTAL_LEN:
            preview = lines[i][:200]
            compressed_lines.append(f"[LINE x{count}: {preview}]")
        else:
            compressed_lines.extend(lines[i:j])
        i = j
    text = "\n".join(compressed_lines)

    # Pass 2: Character-level tandem repeats
    def replacer(match: re.Match) -> str:
        full = match.group(0)
        unit = match.group(1)
        if len(full) < MIN_TOTAL_LEN:
            return full
        count = len(full) // len(unit)
        remainder = full[count * len(unit) :]
        preview = unit if len(unit) <= 100 else unit[:97] + "..."
        result = f"[REPEAT({count}, {preview!r})]"
        return result + remainder if remainder else result

    text = re.sub(r"(.{10,500}?)\1{2,}", replacer, text)

    return text


# --- Step extraction ---


def is_format_error(msg: dict) -> bool:
    """Check if a user message is a framework-generated format error."""
    if msg.get("role") != "user":
        return False
    extra = msg.get("extra", {})
    # Format errors have no returncode/timestamp from command execution
    if extra.get("returncode") is None and extra.get("timestamp") is None:
        content = msg.get("content", "")
        return any(marker in content for marker in FORMAT_ERROR_MARKERS)
    return False


def has_container_death(text: str) -> bool:
    """Check if output contains container death indicators."""
    return any(pattern in text for pattern in CONTAINER_DEATH_PATTERNS)


def extract_command(msg: dict) -> str | None:
    """Extract the command string from an assistant message."""
    extra = msg.get("extra", {})
    actions = extra.get("actions", [])
    if actions and isinstance(actions, list):
        return actions[0].get("command", "")
    return None


def extract_steps(messages: list[dict]) -> tuple[list[dict], dict]:
    """Extract step log from message sequence.

    Returns (steps, detection) where detection contains container death
    info detected from the full observation content (not previews).
    """
    steps = []
    prev_obs_ts = None
    container_death_detected = False
    container_death_step = None
    post_death_count = 0
    format_error_burst_start = None
    format_error_burst_count = 0

    def flush_format_errors():
        """Flush any pending format error burst into steps."""
        nonlocal format_error_burst_start, format_error_burst_count
        if format_error_burst_count <= 0:
            return
        if format_error_burst_count >= MIN_REPEATS:
            steps.append({
                "type": "format_error_burst",
                "step": format_error_burst_start if format_error_burst_start is not None else len(steps),
                "count": format_error_burst_count,
            })
        else:
            for fe_i in range(format_error_burst_count):
                steps.append({
                    "type": "format_error",
                    "step": (format_error_burst_start if format_error_burst_start is not None else len(steps)) + fe_i,
                })
        format_error_burst_start = None
        format_error_burst_count = 0

    i = 0
    while i < len(messages):
        msg = messages[i]

        # Skip system and initial user (instance prompt) messages
        if msg.get("role") == "system" or (msg.get("role") == "user" and i <= 1):
            i += 1
            continue

        # Handle format error messages
        if is_format_error(msg):
            if format_error_burst_start is None:
                format_error_burst_start = len(steps)
            format_error_burst_count += 1
            i += 1
            continue

        # Flush any pending format error burst before processing non-format-error
        if format_error_burst_count > 0:
            flush_format_errors()

        if msg.get("role") != "assistant":
            i += 1
            continue

        cmd = extract_command(msg)
        extra = msg.get("extra", {})
        cost = extra.get("cost", 0)
        ts = extra.get("timestamp")
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")

        # Find the next observation message (scan forward, collecting format errors)
        obs = None
        format_errors_in_scan = 0
        obs_idx = i + 1
        while obs_idx < len(messages):
            candidate = messages[obs_idx]
            if is_format_error(candidate):
                format_errors_in_scan += 1
                obs_idx += 1
                continue
            if candidate.get("role") == "user":
                obs = candidate
            break

        # Record any format errors found between assistant and observation
        if format_errors_in_scan > 0:
            if format_error_burst_start is None:
                format_error_burst_start = len(steps)
            format_error_burst_count += format_errors_in_scan

        # If no observation found, advance past already-scanned format errors
        if obs is None:
            i = obs_idx
            continue

        obs_extra = obs.get("extra", {})
        obs_content = obs.get("content", "")
        returncode = obs_extra.get("returncode")
        obs_ts = obs_extra.get("timestamp")

        # Check for container death using FULL observation content
        if not container_death_detected and has_container_death(obs_content):
            container_death_detected = True
            container_death_step = len(steps)

        if container_death_detected and len(steps) > (container_death_step if container_death_step is not None else 0):
            post_death_count += 1

        # Calculate timing
        inference_sec = None
        if ts is not None and prev_obs_ts is not None:
            inference_sec = round(ts - prev_obs_ts, 2)
            if inference_sec < 0:
                inference_sec = None

        command_sec = None
        if obs_ts is not None and ts is not None:
            command_sec = round(obs_ts - ts, 2)
            if command_sec < 0:
                command_sec = None

        # Compress output
        compressed_output = compress_repeats(obs_content) if obs_content else ""
        max_preview = 500 if len(compressed_output) < 1000 else 300
        output_preview = compressed_output[:max_preview]
        if len(compressed_output) > max_preview:
            output_preview += f"... [{len(obs_content)} chars total]"

        step_data = {
            "type": "step",
            "step": len(steps),
            "command": cmd,
            "returncode": returncode,
            "output_preview": output_preview,
            "output_length": len(obs_content),
            "cost": round(cost, 6) if cost else 0,
            "inference_sec": inference_sec,
            "command_sec": command_sec,
        }

        # Include compressed thought preview
        if content:
            compressed_thought = compress_repeats(content)
            max_thought = 300 if len(steps) < 5 else 150
            if len(compressed_thought) > max_thought:
                step_data["thought_preview"] = compressed_thought[:max_thought] + "..."
            elif len(steps) < 10 or len(compressed_thought) > 20:
                step_data["thought_preview"] = compressed_thought

        # Include compressed reasoning preview (for thinking models)
        if reasoning:
            compressed_reasoning = compress_repeats(reasoning)
            if len(compressed_reasoning) > 500:
                step_data["reasoning_preview"] = compressed_reasoning[:300] + f"... [{len(reasoning)} chars]"
            elif len(compressed_reasoning) > 50:
                step_data["reasoning_preview"] = compressed_reasoning

        steps.append(step_data)
        prev_obs_ts = obs_ts
        i = obs_idx + 1

    # Flush trailing format error burst
    flush_format_errors()

    # Return detection results alongside steps
    detection = {
        "container_death_step": container_death_step,
        "post_death_count": post_death_count,
    }

    return steps, detection


def collapse_identical_commands(steps: list[dict]) -> list[dict]:
    """Collapse consecutive steps with identical commands into a single entry."""
    if not steps:
        return steps

    collapsed: list[dict] = []
    i = 0
    while i < len(steps):
        step = steps[i]

        # Only collapse regular steps with commands
        if step.get("type") != "step" or step.get("command") is None:
            collapsed.append(step)
            i += 1
            continue

        # Count consecutive identical commands
        j = i + 1
        while (
            j < len(steps)
            and steps[j].get("type") == "step"
            and steps[j].get("command") == step["command"]
        ):
            j += 1

        count = j - i
        if count >= MIN_REPEATS:
            run = steps[i:j]
            total_cost = sum(s.get("cost", 0) for s in run)
            inference_times = [s["inference_sec"] for s in run if s.get("inference_sec")]
            returncodes = sorted(set(s.get("returncode") for s in run if s.get("returncode") is not None))
            entry = {
                "type": "repeated_command",
                "step_range": [run[0]["step"], run[-1]["step"]],
                "count": count,
                "command": step["command"],
                "sample_output_preview": step.get("output_preview", ""),
                "returncodes": returncodes,
                "total_cost": round(total_cost, 4),
                "avg_inference_sec": round(
                    sum(inference_times) / len(inference_times), 2
                ) if inference_times else None,
            }
            # If returncodes vary, note where the transition happened
            if len(returncodes) > 1:
                for k, s in enumerate(run):
                    if s.get("returncode") != run[0].get("returncode"):
                        entry["returncode_changed_at_step"] = s["step"]
                        break
            collapsed.append(entry)
        else:
            collapsed.extend(steps[i:j])

        i = j

    return collapsed


def compute_stats(steps: list[dict], info: dict, detection: dict) -> dict:
    """Compute deterministic statistics from extracted steps.

    Uses detection dict from extract_steps for container death info
    (detected from full observation content, not truncated previews).
    """
    model_stats = info.get("model_stats", {})

    # Count step types
    regular_steps = [s for s in steps if s.get("type") == "step"]
    format_errors = sum(
        s.get("count", 1) if s.get("type") == "format_error_burst" else 1
        for s in steps
        if s.get("type") in ("format_error", "format_error_burst")
    )

    # Container death from detection (uses full content, not preview)
    container_death_step = detection.get("container_death_step")
    post_death_count = detection.get("post_death_count", 0)

    # Timing stats from regular steps
    inference_times = [
        s["inference_sec"]
        for s in regular_steps
        if s.get("inference_sec") is not None and s["inference_sec"] > 0
    ]
    command_times = [
        s["command_sec"]
        for s in regular_steps
        if s.get("command_sec") is not None and s["command_sec"] > 0
    ]

    stats = {
        "api_calls": model_stats.get("api_calls", len(regular_steps)),
        "instance_cost": round(model_stats.get("instance_cost", 0), 4),
        "exit_status": info.get("exit_status", "unknown"),
        "step_counts": {
            "total": len(regular_steps) + format_errors,
            "regular": len(regular_steps),
            "format_errors": format_errors,
            "post_container_death": post_death_count,
        },
        "container_death": {
            "detected": container_death_step is not None,
            "step": container_death_step,
            "post_death_steps": post_death_count,
        },
    }

    if inference_times:
        stats["timing"] = {
            "avg_inference_sec": round(sum(inference_times) / len(inference_times), 2),
            "max_inference_sec": round(max(inference_times), 2),
            "avg_command_sec": round(
                sum(command_times) / len(command_times), 2
            ) if command_times else None,
            "max_command_sec": round(max(command_times), 2) if command_times else None,
        }

    return stats


def process_traj_file(traj_path: Path) -> dict:
    """Process a single trajectory file and return steps.json content."""
    with open(traj_path) as f:
        data = json.load(f)

    messages = data.get("messages", [])
    info = data.get("info", {})
    instance_id = data.get("instance_id", traj_path.stem.replace(".traj", ""))

    # Get total duration from first and last timestamps
    first_ts = None
    last_ts = None
    for msg in messages:
        ts = msg.get("extra", {}).get("timestamp")
        if ts is not None:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

    steps, detection = extract_steps(messages)

    # Compute stats BEFORE collapsing (stats need the raw step counts)
    stats = compute_stats(steps, info, detection)

    if first_ts is not None and last_ts is not None:
        stats.setdefault("timing", {})["total_duration_sec"] = round(last_ts - first_ts, 1)

    # Collapse post-container-death steps into a single entry
    container_step = stats["container_death"]["step"]
    if container_step is not None:
        pre_death = [s for s in steps if s.get("type") != "step" or s.get("step", 0) <= container_step]
        post_death = [s for s in steps if s.get("type") == "step" and s.get("step", 0) > container_step]
        if len(post_death) > 2:
            sample = post_death[0] if post_death else None
            steps = pre_death
            if sample:
                steps.append(sample)
            steps.append({
                "type": "post_container_death",
                "collapsed_steps": len(post_death) - (1 if sample else 0),
                "note": "Remaining steps after container death collapsed. All returned container error.",
            })

    # Collapse consecutive identical commands
    steps = collapse_identical_commands(steps)

    return {
        "schema_version": SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "instance_id": instance_id,
        "stats": stats,
        "steps": steps,
    }


def process_run(run_dir: Path):
    """Process all traj files in a run directory."""
    traj_files = sorted(run_dir.glob("*/*.traj.json"))
    if not traj_files:
        print(f"No traj files found in {run_dir}")
        return

    total = len(traj_files)
    print(f"Processing {total} traj files in {run_dir.name}...")
    processed = 0
    errors = 0

    for traj_path in traj_files:
        output_path = traj_path.with_name(
            traj_path.name.replace(".traj.json", ".steps.json")
        )
        try:
            result = process_traj_file(traj_path)
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2)
            processed += 1
            if processed % 50 == 0 or processed == total:
                print(f"  {processed}/{total} processed...", flush=True)
        except Exception as e:
            print(f"  ERROR: {traj_path.name}: {e}", flush=True)
            errors += 1

    print(f"  Done: {processed} processed, {errors} errors", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Extract compact step logs from trajectory files (Phase 1)"
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a single .traj.json file (outputs to stdout)",
    )
    parser.add_argument(
        "--run-id",
        help="Process all traj files in a specific run",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all runs in the results directory",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Results directory (default: results)",
    )

    args = parser.parse_args()
    results_dir = Path(args.results_dir)

    if args.path:
        result = process_traj_file(Path(args.path))
        json.dump(result, sys.stdout, indent=2)
        print()
    elif args.run_id:
        run_dir = results_dir / args.run_id
        if not run_dir.exists():
            print(f"Run directory not found: {run_dir}")
            sys.exit(1)
        process_run(run_dir)
    elif args.all:
        for run_dir in sorted(results_dir.iterdir()):
            if run_dir.is_dir() and run_dir.name.startswith("swe-"):
                process_run(run_dir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
