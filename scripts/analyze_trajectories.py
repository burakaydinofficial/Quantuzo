#!/usr/bin/env python3
"""
Trajectory analysis using an LLM (OpenAI-compatible API).

Reads *.steps.json files (from extract_steps.py) and produces *.analysis.json
files using an LLM to classify failure reasons, detect behavioral loops, and
assess the agent's problem-solving approach.

Usage:
    python3 scripts/analyze_trajectories.py --run-id <run-id> [--model MODEL] [--base-url URL]
    python3 scripts/analyze_trajectories.py --all [--model MODEL]
    python3 scripts/analyze_trajectories.py <path/to/instance.steps.json> [--model MODEL]

Environment variables:
    OPENAI_API_KEY       API key (required)
    OPENAI_BASE_URL      Base URL for OpenAI-compatible endpoint (optional)
    ANALYSIS_MODEL       Default model name (optional)
"""

import argparse
import concurrent.futures
from collections import Counter
import hashlib
import json
import os
import re
import sys
import time
import threading
from pathlib import Path

SCHEMA_VERSION = "1.2"
PROMPT_FILE = Path(__file__).parent.parent / "config" / "analysis" / "trajectory_analysis_prompt.md"
DEFAULT_MODEL = "gpt-4o"

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

def coerce_bool(val, default: bool = False) -> bool:
    """Coerce a value to bool. Handles 'yes'/'no', 1/0, etc."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "yes", "1")
    if isinstance(val, (int, float)):
        return bool(val)
    return default


def coerce_int(val, default: int = 0, min_val: int = 0) -> int:
    """Coerce a value to int with minimum bound."""
    if isinstance(val, int) and not isinstance(val, bool):
        return max(val, min_val)
    if isinstance(val, float):
        return max(int(val), min_val)
    if isinstance(val, str):
        try:
            return max(int(val), min_val)
        except ValueError:
            pass
    return default


def repair_analysis(data: dict, fallback: dict) -> tuple[dict, list[str]]:
    """Validate and coercively repair LLM output. Returns (repaired_data, issues)."""
    issues = []
    result = {}

    # failure_reason
    fr = data.get("failure_reason")
    if isinstance(fr, str) and fr in VALID_FAILURE_REASONS:
        result["failure_reason"] = fr
    else:
        if fr is not None:
            issues.append(f"invalid failure_reason: {fr!r}")
        result["failure_reason"] = fallback["failure_reason"]

    # summary
    s = data.get("summary")
    if isinstance(s, str) and len(s) > 0:
        result["summary"] = s
    else:
        issues.append("missing or invalid summary")
        result["summary"] = fallback["summary"]

    # behavioral_loop
    bl = data.get("behavioral_loop")
    fb_bl = fallback["behavioral_loop"]
    if isinstance(bl, dict):
        result["behavioral_loop"] = {
            "detected": coerce_bool(bl.get("detected"), fb_bl["detected"]),
            "start_step": bl.get("start_step") if isinstance(bl.get("start_step"), (int, type(None))) and not isinstance(bl.get("start_step"), bool) else fb_bl["start_step"],
            "description": bl.get("description") if isinstance(bl.get("description"), (str, type(None))) else fb_bl["description"],
        }
    else:
        issues.append("missing or non-dict behavioral_loop")
        result["behavioral_loop"] = fb_bl

    # problem_approach
    pa = data.get("problem_approach")
    fb_pa = fallback["problem_approach"]
    if isinstance(pa, dict):
        result["problem_approach"] = {
            "identified_correct_file": coerce_bool(pa.get("identified_correct_file"), fb_pa["identified_correct_file"]),
            "identified_root_cause": coerce_bool(pa.get("identified_root_cause"), fb_pa["identified_root_cause"]),
            "distinct_strategies": coerce_int(pa.get("distinct_strategies"), fb_pa["distinct_strategies"], min_val=0),
            "fix_attempted": coerce_bool(pa.get("fix_attempted"), fb_pa["fix_attempted"]),
            "had_viable_fix": coerce_bool(pa.get("had_viable_fix"), fb_pa["had_viable_fix"]),
        }
    else:
        issues.append("missing or non-dict problem_approach")
        result["problem_approach"] = fb_pa

    return result, issues


def load_prompt() -> tuple[str, str]:
    """Load the analysis prompt and compute its hash."""
    text = PROMPT_FILE.read_text()
    prompt_hash = hashlib.sha256(text.encode()).hexdigest()[:12]
    return text, prompt_hash


def load_resolution_map(run_dir: Path) -> dict[str, str]:
    """Load per-instance resolution status from evaluation_results.json.

    Returns dict mapping instance_id -> "resolved" | "unresolved" | "error" | "not_submitted"
    """
    eval_file = run_dir / "evaluation_results.json"
    if not eval_file.exists():
        return {}

    with open(eval_file) as f:
        data = json.load(f)

    instances = data.get("instances", {})
    resolution_map: dict[str, str] = {}

    for iid in instances.get("resolved_ids", []):
        resolution_map[iid] = "resolved"
    for iid in instances.get("unresolved_ids", []):
        resolution_map[iid] = "unresolved"
    for iid in instances.get("error_ids", []):
        resolution_map[iid] = "error"

    return resolution_map


def pre_classify(steps_data: dict, resolution: str) -> str | None:
    """Attempt to classify failure reason without LLM.

    Returns a failure_reason string if deterministic, None if LLM needed.
    """
    stats = steps_data.get("stats", {})
    exit_status = stats.get("exit_status", "")
    counts = stats.get("step_counts", {})
    total = counts.get("total", 1)
    format_errors = counts.get("format_errors", 0)

    if resolution == "resolved":
        return "resolved"

    if exit_status == "BadRequestError":
        return "context_overflow"

    if format_errors > total * 0.5:
        return "format_error_dominated"

    # Check if dominated by exact loops
    steps = steps_data.get("steps", [])
    repeated_steps = sum(
        s.get("count", 0) for s in steps if s.get("type") == "repeated_command"
    )
    regular_steps = counts.get("regular", 0)
    if regular_steps > 0 and repeated_steps > regular_steps * 0.6:
        return "exact_loop"

    # Check for identical steps by content (thought_preview + output_preview)
    regular = [s for s in steps if s.get("type") == "step"]
    if len(regular) >= 10:
        sigs = [
            (s.get("thought_preview", "")[:100], s.get("output_preview", "")[:100])
            for s in regular
        ]
        top_count = Counter(sigs).most_common(1)[0][1]
        # Overall: 50%+ identical = stuck from early on
        if top_count >= len(sigs) * 0.5:
            return "exact_loop"
        # Tail: 80%+ of last half identical = got stuck later
        half = len(sigs) // 2
        tail = sigs[half:]
        tail_top = Counter(tail).most_common(1)[0][1]
        if tail_top >= len(tail) * 0.8:
            return "exact_loop"

    if resolution in ("unresolved", "error"):
        return "submitted_incorrect"

    return None  # LLM needed


def build_llm_input(
    steps_data: dict,
    resolution: str,
    pre_class: str | None,
) -> str:
    """Build the user message content for the LLM."""
    stats = steps_data.get("stats", {})
    instance_id = steps_data.get("instance_id", "unknown")

    context_lines = [
        f"Instance: {instance_id}",
        f"Exit status: {stats.get('exit_status', 'unknown')}",
        f"Resolution: {resolution}",
        f"API calls: {stats.get('api_calls', '?')}",
        f"Cost: ${stats.get('instance_cost', 0):.2f}",
    ]

    if pre_class:
        context_lines.append(f"Pre-classified failure reason: {pre_class}")
        context_lines.append(
            "The failure_reason is already determined. "
            "Focus on behavioral_loop, problem_approach, and summary."
        )

    counts = stats.get("step_counts", {})
    context_lines.append(
        f"Step counts: {counts.get('regular', 0)} regular, "
        f"{counts.get('format_errors', 0)} format errors, "
        f"{counts.get('post_container_death', 0)} post-container-death"
    )

    cd = stats.get("container_death", {})
    if cd.get("detected"):
        context_lines.append(
            f"Container death at step {cd['step']} "
            f"({cd.get('post_death_steps', 0)} steps wasted after)"
        )

    timing = stats.get("timing", {})
    if timing:
        context_lines.append(
            f"Timing: avg inference {timing.get('avg_inference_sec', '?')}s, "
            f"total duration {timing.get('total_duration_sec', '?')}s"
        )

    context = "\n".join(context_lines)
    steps_json = json.dumps(steps_data.get("steps", []), indent=2)

    return f"## Context\n\n{context}\n\n## Steps\n\n{steps_json}"


def create_client(base_url: str | None = None, api_key: str | None = None):
    """Create an OpenAI-compatible client."""
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: openai package required. pip install openai")
        sys.exit(1)

    kwargs = {"timeout": 1800.0}  # 30 min — needed for large models with long thinking
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    return OpenAI(**kwargs)


def call_llm(
    client,
    system_prompt: str,
    user_content: str,
    model: str,
) -> dict | None:
    """Call an OpenAI-compatible API and parse the JSON response."""
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1 if attempt > 0 else 0,
            )
            raw = response.choices[0].message.content.strip()
            raw_len = len(raw)

            # Strip thinking tags (e.g. Qwen3.5)
            text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("```", 1)[0]
                text = text.strip()

            return json.loads(text)

        except json.JSONDecodeError as e:
            after_strip = len(text)
            print(f"  JSON parse error (attempt {attempt + 1}): {e} [raw={raw_len}, after_strip={after_strip}]")
            if attempt < 2:
                time.sleep(2)
        except Exception as e:
            print(f"  API error (attempt {attempt + 1}): {e}")
            if attempt < 2:
                time.sleep(5)

    return None


def analyze_instance(
    steps_path: Path,
    resolution: str,
    client,
    system_prompt: str,
    prompt_hash: str,
    model: str,
) -> dict:
    """Analyze a single instance and return analysis.json content."""
    with open(steps_path) as f:
        steps_data = json.load(f)

    instance_id = steps_data.get("instance_id", "unknown")
    pre_class = pre_classify(steps_data, resolution)

    user_content = build_llm_input(steps_data, resolution, pre_class)
    llm_result = call_llm(client, system_prompt, user_content, model)

    fallback = {
        "failure_reason": pre_class or "insufficient_capability",
        "behavioral_loop": {
            "detected": False,
            "start_step": None,
            "description": None,
        },
        "problem_approach": {
            "identified_correct_file": False,
            "identified_root_cause": False,
            "distinct_strategies": 0,
            "fix_attempted": False,
            "had_viable_fix": False,
        },
        "summary": "LLM analysis failed or returned invalid output.",
    }

    if not isinstance(llm_result, dict):
        llm_result = fallback
    else:
        llm_result, issues = repair_analysis(llm_result, fallback)
        if issues:
            print(f"  WARN: {instance_id}: repaired LLM output: {', '.join(issues)}")

    # Override failure_reason if pre-classified
    if pre_class:
        llm_result["failure_reason"] = pre_class

    return {
        "schema_version": SCHEMA_VERSION,
        "analyzer": {
            "model": model,
            "prompt_hash": prompt_hash,
        },
        "instance_id": instance_id,
        **llm_result,
    }


def process_run(run_dir: Path, client, model: str, prompt_hash: str, system_prompt: str, force: bool = False, parallel: int = 1):
    """Process all steps.json files in a run directory."""
    steps_files = sorted(run_dir.glob("*/*.steps.json"))
    if not steps_files:
        print(f"No steps.json files in {run_dir.name}. Run extract_steps.py first.")
        return

    resolution_map = load_resolution_map(run_dir)

    print(f"Analyzing {len(steps_files)} instances in {run_dir.name}...")
    print(f"  Model: {model}")
    print(f"  Prompt hash: {prompt_hash}")
    print(f"  Resolution data: {len(resolution_map)} instances")

    # Filter to pending work
    pending = []
    skipped = 0
    for steps_path in steps_files:
        output_path = steps_path.with_name(
            steps_path.name.replace(".steps.json", ".analysis.json")
        )
        if output_path.exists() and not force:
            skipped += 1
        else:
            pending.append(steps_path)

    if not pending:
        print(f"  All {skipped} instances already analyzed (use --force to redo)")
        return

    processed = 0
    errors = 0
    lock = threading.Lock()

    def do_one(steps_path: Path):
        nonlocal processed, errors
        instance_id = steps_path.parent.name
        resolution = resolution_map.get(instance_id, "not_submitted")
        output_path = steps_path.with_name(
            steps_path.name.replace(".steps.json", ".analysis.json")
        )
        try:
            result = analyze_instance(
                steps_path, resolution, client, system_prompt, prompt_hash, model
            )
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2)
            with lock:
                processed += 1
                if processed % 10 == 0:
                    print(f"  {processed} analyzed...")
        except Exception as e:
            print(f"  ERROR: {instance_id}: {e}")
            with lock:
                errors += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool:
        pool.map(do_one, pending)

    print(f"  Done: {processed} analyzed, {skipped} skipped, {errors} errors")


def main():
    parser = argparse.ArgumentParser(
        description="LLM-based trajectory analysis (OpenAI-compatible API)"
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a single .steps.json file",
    )
    parser.add_argument("--run-id", help="Process a specific run")
    parser.add_argument("--all", action="store_true", help="Process all runs")
    parser.add_argument(
        "--model",
        default=os.environ.get("ANALYSIS_MODEL", DEFAULT_MODEL),
        help=f"Model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL"),
        help="Base URL for OpenAI-compatible endpoint (e.g., http://localhost:1234/v1)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
        help="API key (default: OPENAI_API_KEY env var)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing analysis.json files",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Results directory (default: results)",
    )
    parser.add_argument(
        "--parallel", "-j",
        type=int,
        default=1,
        help="Number of parallel requests (default: 1)",
    )

    args = parser.parse_args()
    results_dir = Path(args.results_dir)

    if not args.api_key and not args.base_url:
        print("ERROR: OPENAI_API_KEY environment variable or --base-url required")
        print("  For cloud APIs: export OPENAI_API_KEY=sk-...")
        print("  For local (LM Studio): --base-url http://localhost:1234/v1 --api-key lm-studio")
        sys.exit(1)

    client = create_client(base_url=args.base_url, api_key=args.api_key or "local")
    system_prompt, prompt_hash = load_prompt()

    if args.path:
        steps_path = Path(args.path)
        run_dir = steps_path.parent.parent
        resolution_map = load_resolution_map(run_dir)
        if not resolution_map:
            print(f"WARNING: No evaluation_results.json found in {run_dir}", file=sys.stderr)
            print("  Resolution status will default to 'not_submitted'", file=sys.stderr)
        instance_id = steps_path.parent.name
        resolution = resolution_map.get(instance_id, "not_submitted")

        result = analyze_instance(
            steps_path, resolution, client, system_prompt, prompt_hash, args.model
        )
        json.dump(result, sys.stdout, indent=2)
        print()

    elif args.run_id:
        run_dir = results_dir / args.run_id
        if not run_dir.exists():
            print(f"Run directory not found: {run_dir}")
            sys.exit(1)
        process_run(run_dir, client, args.model, prompt_hash, system_prompt, args.force, args.parallel)

    elif args.all:
        if not results_dir.is_dir():
            print(f"Results directory not found: {results_dir}")
            sys.exit(1)
        for run_dir in sorted(results_dir.iterdir()):
            if run_dir.is_dir() and run_dir.name.startswith("swe-"):
                process_run(run_dir, client, args.model, prompt_hash, system_prompt, args.force, args.parallel)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
