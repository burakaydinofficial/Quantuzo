#!/usr/bin/env python3
"""
Shared, dependency-free helpers for reading run folders and building leaderboard
rows / summaries.

This module has NO huggingface_hub dependency on purpose, so local-only tools
(generate_summary.py, validate_run.py) can import it without triggering the HF
install path in push_results.py. push_results.py imports from here too, so the
row schema has a single source of truth.
"""

import json
from pathlib import Path


# =============================================================================
# Constants
# =============================================================================

SCHEMA_VERSION = "1.0"
RUNS_PREFIX = "runs"
LEADERBOARD_V2_FILE = "leaderboard.v2.jsonl"  # derived, rebuilt from summaries
SUMMARY_FILE = "summary.json"

# Core numeric fields that must agree between summary.json and evaluation_results.json.
# Maps leaderboard-row key -> evaluation_results.json key.
CORE_FIELDS = {
    "total": "total_instances",
    "resolved": "resolved",
    "failed": "failed",
    "error": "error",
    "rate": "resolution_rate",
}


# =============================================================================
# Run-folder readers
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
    """Count exit statuses from per-instance trajectory files.

    Authoritative source: each instance's own *.traj.json info.exit_status.
    Do NOT use exit_statuses_*.yaml — resumed runs write more than one, and the
    early one can be a partial (e.g. a 9-instance halted session).
    """
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


def _num(value, default):
    """Coerce a numeric value to the type of `default`; return `default` otherwise.

    Keeps a null/list/string in evaluation_results.json from reaching the board.
    A no-op on well-formed data (an int stays that int, a float that float).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return type(default)(value)


def _s(value):
    """Keep a string field a string ('' otherwise), so a label can't carry an
    attacker-controlled object / number / markup onto the public board."""
    return value if isinstance(value, str) else ""


def _d(value):
    return value if isinstance(value, dict) else {}


def _clean_exit_statuses(value) -> dict | None:
    """exit_statuses is the one row field copied from the (contributor-authored) summary.
    Accept only a bounded dict[str, non-negative int] so it can't bloat or poison the board."""
    if not isinstance(value, dict):
        return None
    out: dict[str, int] = {}
    for key, count in value.items():
        if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            out[key[:100]] = count
        if len(out) >= 50:
            break
    return out or None


def build_leaderboard_row(
    metadata: dict,
    eval_results: dict | None,
    exit_statuses: dict[str, int] | None = None,
) -> dict:
    """Build a flat leaderboard row from metadata and evaluation results.

    Every field is type-coerced (labels -> str, counts -> int) and `rate` is DERIVED
    from resolved/total (never trusted), so a fabricated or malformed contributor file
    can't put a bogus headline percentage or an arbitrary object onto the board.
    """
    metadata = _d(metadata)
    ev = eval_results if isinstance(eval_results, dict) else {}
    model = _d(metadata.get("model"))
    inference = _d(metadata.get("inference"))
    agent = _d(metadata.get("agent"))

    total = _num(ev.get("total_instances"), 0)
    resolved = _num(ev.get("resolved"), 0)
    row = {
        "run_id": _s(metadata.get("run_id")),
        "timestamp": _s(metadata.get("timestamp")),
        "model_name": _s(model.get("name")),
        "model_file": _s(model.get("file")),
        "kv_type_k": _s(inference.get("kv_type_k")),
        "kv_type_v": _s(inference.get("kv_type_v")),
        "ctx_size": _num(inference.get("ctx_size"), 0),
        "accelerator": _s(inference.get("accelerator")),
        "agent_version": _s(agent.get("version")),
        "agent_branch": _s(agent.get("branch")),
        "benchmark": _s(metadata.get("benchmark")),
        "total": total,
        "resolved": resolved,
        "failed": _num(ev.get("failed"), 0),
        "error": _num(ev.get("error"), 0),
        "rate": (resolved / total * 100) if total else 0.0,
    }
    cleaned = _clean_exit_statuses(exit_statuses)
    if cleaned:
        row["exit_statuses"] = cleaned
    return row


# =============================================================================
# Summary generation + validation
# =============================================================================

def generate_summary(run_dir: Path) -> dict:
    """Build the summary.json content for a run directory (does not write).

    summary.json IS a leaderboard row plus schema_version, so the two can never
    drift. Raises ValueError if the run lacks metadata or evaluation results.
    """
    metadata = load_metadata(run_dir)
    if metadata is None:
        raise ValueError(f"no readable metadata.json in {run_dir}")
    eval_results = extract_eval_results(run_dir)
    if eval_results is None:
        raise ValueError(f"no readable evaluation_results.json in {run_dir}")
    exit_statuses = extract_exit_statuses(run_dir)
    row = build_leaderboard_row(metadata, eval_results, exit_statuses)
    return {"schema_version": SCHEMA_VERSION, **row}


def build_leaderboard_rows_local(results_dir: Path) -> tuple[dict[str, dict], list[str], list]:
    """Build leaderboard rows from a local results dir (each run's summary.json).

    Returns (rows_by_run_id, missing_run_ids, stale_summary_run_ids). Rows are built
    from AUTHORITATIVE metadata + evaluation_results.json; a run's summary.json only
    supplies the exit_statuses tally (expensive to recompute) — so a stale or tampered
    summary can never put wrong numbers or labels on the board.

    Lives here (not in push_results.py) because it touches no HuggingFace API, which
    keeps it importable — and unit-testable — without the huggingface_hub dependency.
    """
    rows: dict[str, dict] = {}
    missing: list[str] = []
    mismatched: list = []
    for run_dir in sorted(d for d in results_dir.iterdir() if d.is_dir()):
        metadata = load_metadata(run_dir)
        if not isinstance(metadata, dict):
            continue  # not a run folder (stray dir in results/) — ignore
        summary_path = run_dir / SUMMARY_FILE
        if not summary_path.exists():
            missing.append(run_dir.name)
            continue
        try:
            with open(summary_path) as f:
                summary = json.load(f)
        except (json.JSONDecodeError, OSError):
            missing.append(run_dir.name)
            continue
        eval_results = extract_eval_results(run_dir)
        if not isinstance(summary, dict) or eval_results is None:
            missing.append(run_dir.name)
            continue
        rows[run_dir.name] = build_leaderboard_row(metadata, eval_results, summary.get("exit_statuses"))
        if summary_matches_eval(summary, eval_results):
            mismatched.append(run_dir.name)
    return rows, missing, mismatched


def summary_matches_eval(summary: dict, eval_results: dict | None) -> list[tuple]:
    """Compare a summary's core numbers against evaluation_results.json.

    Returns a list of (field, expected_from_eval, got_in_summary) mismatches;
    empty list means agreement. rate is compared with a small tolerance.
    """
    if not eval_results:
        return []
    if not isinstance(summary, dict):
        # A summary that isn't a JSON object is a total mismatch, not a crash.
        return [("<summary>", "a JSON object", type(summary).__name__)]
    diffs: list[tuple] = []
    for key, eval_key in CORE_FIELDS.items():
        want = eval_results.get(eval_key, 0)
        got = summary.get(key)
        if key == "rate":
            try:
                if got is None or abs(float(got) - float(want)) > 0.01:
                    diffs.append((key, want, got))
            except (TypeError, ValueError):
                diffs.append((key, want, got))
        elif got != want:
            diffs.append((key, want, got))
    return diffs
