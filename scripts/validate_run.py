#!/usr/bin/env python3
"""
Validate a benchmark run before it lands on the leaderboard.

Two modes:
  Local:  python3 scripts/validate_run.py <run_dir>
  PR:     python3 scripts/validate_run.py --repo R --pr N     (read-only, via HF)

Checks (see docs / plan):
  1. Structure      metadata + evaluation_results present, >=1 trajectory, folder==run_id
  2. Eval consistency  resolved+failed+error<=total; preds==trajectories; submitted count matches
  3. Summary agree     summary.json numbers match evaluation_results.json (+ exit_statuses locally)
  4. No gamed resolves every resolved patch is non-empty; FLAG resolved patches touching tests
  5. PR scope (PR only) touches only runs/<run_id>/**; leaderboard*/README/.gitattributes/other runs untouched

Exit code is non-zero if any FAIL is reported. FLAG is advisory (does not fail).
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from leaderboard_lib import (  # noqa: E402
    RUNS_PREFIX,
    SUMMARY_FILE,
    extract_eval_results,
    extract_exit_statuses,
    load_metadata,
    summary_matches_eval,
)

# Files that are part of the repo's TEST SUITE (a tests/ dir or conftest.py). Deliberately
# does NOT match bare test_*.py at the repo root — those are almost always the agent's own
# scratch reproduction scripts, not the suite, and flagging them is pure noise (verified
# against real runs: ~27 of 29 "touches tests" hits were agent repro scripts).
TEST_FILE_RE = re.compile(r"(^|/)(tests?|testing)/|(^|/)conftest\.py$", re.I)


class Report:
    def __init__(self):
        self.findings: list[tuple[str, str]] = []  # (level, message)

    def ok(self, msg: str) -> None:
        self.findings.append(("OK", msg))

    def fail(self, msg: str) -> None:
        self.findings.append(("FAIL", msg))

    def flag(self, msg: str) -> None:
        self.findings.append(("FLAG", msg))

    @property
    def failed(self) -> bool:
        return any(level == "FAIL" for level, _ in self.findings)

    def print(self, title: str) -> None:
        icon = {"OK": "  ok  ", "FAIL": " FAIL ", "FLAG": " flag "}
        n_fail = sum(level == "FAIL" for level, _ in self.findings)
        n_flag = sum(level == "FLAG" for level, _ in self.findings)
        print(f"\n=== validate: {title} ===")
        for level, msg in self.findings:
            print(f"[{icon[level]}] {msg}")
        print(f"--- {'FAILED' if self.failed else 'passed'} ({n_fail} fail, {n_flag} flag) ---")


def patch_touches_tests(patch: str) -> list[str]:
    files = re.findall(r"^\+\+\+ b/(.+)$", patch or "", re.M)
    files += re.findall(r"^diff --git a/(\S+)", patch or "", re.M)
    return sorted({f for f in files if TEST_FILE_RE.search(f)})


# Full-run instance counts per benchmark; only these labels are accepted, and a run
# must have exactly this many instances (blocks partial/filtered and off-allowlist runs).
SUBSET_SIZES = {"swe-bench-lite": 300, "swe-bench-verified": 500, "swe-bench-full": 2294}
MAX_INSTANCES = 10000  # far above any real benchmark (full = 2294) — a DoS/plausibility ceiling
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")  # safe for use in file paths


def _as_int(value) -> int:
    """Coerce a possibly-null / non-numeric field to int (0 on anything else)."""
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _patch_of(preds: dict, iid: str) -> str:
    """Safely extract an instance's model_patch as a string ('' if absent/wrong type)."""
    entry = preds.get(iid)
    patch = entry.get("model_patch") if isinstance(entry, dict) else None
    return patch if isinstance(patch, str) else ""


def _check_eval_and_resolves(rep: "Report", run_id: str, metadata: dict | None,
                             eval_results: dict, preds: dict | None,
                             n_traj: int | None, summary: dict | None) -> None:
    """Rules 2-4 shared by local and PR modes (given already-loaded dicts)."""
    # The container types are attacker-controlled in PR mode — guard them, not just
    # their inner values, so a non-object JSON file yields a clean FAIL, not a crash.
    if not isinstance(eval_results, dict):
        rep.fail("evaluation_results.json is not a JSON object")
        return
    if metadata is not None and not isinstance(metadata, dict):
        rep.fail("metadata.json is not a JSON object")
        metadata = None

    # Core numeric fields, if present, must be real numbers. Otherwise build_leaderboard_row
    # would publish a null/garbage value while _as_int silently reads it as 0 here.
    for field in ("total_instances", "resolved", "failed", "error"):
        value = eval_results.get(field)
        if field in eval_results and not (isinstance(value, (int, float)) and not isinstance(value, bool)):
            rep.fail(f"evaluation_results.json field '{field}' is not a number: {value!r}")

    # Rule 1 (partial): folder/run_id agreement
    if metadata and metadata.get("run_id") not in (None, run_id):
        rep.fail(f"metadata.run_id ({metadata.get('run_id')}) != folder ({run_id})")

    # Rule 2: eval consistency (coerce in case a numeric field is null/non-numeric)
    total = _as_int(eval_results.get("total_instances"))
    resolved = _as_int(eval_results.get("resolved"))
    failed = _as_int(eval_results.get("failed"))
    error = _as_int(eval_results.get("error"))
    submitted = _as_int(eval_results.get("predictions_submitted"))
    if total > MAX_INSTANCES:
        rep.fail(f"implausibly large run (total={total} > {MAX_INSTANCES}) — refusing to process")
        return
    if resolved + failed + error > total:
        rep.fail(f"resolved+failed+error ({resolved+failed+error}) > total ({total})")
    else:
        rep.ok(f"eval counts consistent (r={resolved} f={failed} e={error} / {total})")
    if n_traj is not None and n_traj != total:
        rep.fail(f"trajectory count ({n_traj}) != total_instances ({total})")

    # Benchmark must be a known full dataset of exactly its canonical size — blocks a
    # partial/filtered run AND an off-allowlist label (e.g. "swe-bench-tiny") that would
    # otherwise skip the size gate entirely.
    benchmark = (metadata or {}).get("benchmark")
    benchmark = benchmark.strip() if isinstance(benchmark, str) else benchmark
    expected = SUBSET_SIZES.get(benchmark)
    if expected is None:
        rep.fail(f"unknown benchmark {benchmark!r} — must be one of {sorted(SUBSET_SIZES)}")
    elif total != expected:
        rep.fail(f"total ({total}) != {benchmark} size ({expected}) — partial/filtered or malformed run")

    # rate is DERIVED for the board, but a fabricated resolution_rate signals tampering.
    rate = eval_results.get("resolution_rate")
    if total and isinstance(rate, (int, float)) and not isinstance(rate, bool):
        if abs(rate - resolved / total * 100) > 0.1:
            rep.fail(f"resolution_rate ({rate}) != resolved/total ({resolved / total * 100:.2f}%)")

    # evaluation_results.json writes "instances" as a dict on the normal path, but
    # as a list on run_evaluation.py's fallback/empty paths — guard the type.
    inst = eval_results.get("instances")
    ids = inst.get("resolved_ids") if isinstance(inst, dict) else None
    resolved_ids = set(ids) if isinstance(ids, list) else set()
    if len(resolved_ids) > MAX_INSTANCES:
        rep.fail(f"implausibly many resolved_ids ({len(resolved_ids)}) — refusing to process")
        return
    if not isinstance(inst, dict) and (eval_results.get("resolved", 0) or 0) > 0:
        rep.flag("eval 'instances' is not a dict with *_ids — gaming checks skipped")

    if preds is not None and not isinstance(preds, dict):
        rep.fail("preds.json is not a JSON object (dict keyed by instance_id)")
        preds = None
    if isinstance(preds, dict) and len(preds) > MAX_INSTANCES:
        rep.fail(f"implausibly many preds entries ({len(preds)}) — refusing to process")
        return
    if preds is not None:
        if n_traj is not None and len(preds) != n_traj:
            rep.fail(f"preds.json entries ({len(preds)}) != trajectories ({n_traj})")
        nonempty = [k for k in preds if _patch_of(preds, k).strip()]
        if submitted and len(nonempty) != submitted:
            rep.flag(f"predictions_submitted ({submitted}) != non-empty patches ({len(nonempty)})")
        # Rule 4: gamed resolves. You can't resolve more instances than you submitted
        # non-empty patches for — this catches inflated counts even when `instances`
        # lacks resolved_ids (so the empty-patch check below would otherwise be skipped).
        if resolved > len(nonempty):
            rep.fail(f"claims {resolved} resolved but only {len(nonempty)} non-empty patches")
        empty_resolved = [i for i in resolved_ids if not _patch_of(preds, i).strip()]
        if empty_resolved:
            rep.fail(f"{len(empty_resolved)} resolved instances have EMPTY patches: {empty_resolved[:5]}")
        else:
            rep.ok(f"all {len(resolved_ids)} resolved instances have non-empty patches")
        test_touchers = [i for i in resolved_ids if patch_touches_tests(_patch_of(preds, i))]
        if test_touchers:
            rep.flag(f"{len(test_touchers)} resolved patches touch test files: {test_touchers[:5]}")
        else:
            rep.ok("no resolved patch touches test files")

    # A run claiming resolves with no patches to check can't be verified — don't pass it.
    if preds is None and resolved > 0:
        rep.fail(f"claims {resolved} resolved but no readable preds.json to verify patches")

    # Rule 3: summary agreement
    if summary is not None:
        diffs = summary_matches_eval(summary, eval_results)
        if diffs:
            rep.fail(f"summary.json disagrees with eval: {diffs}")
        else:
            rep.ok("summary.json numbers match evaluation_results.json")
    else:
        rep.flag("no summary.json (run generate_summary.py --fill-missing)")


# ----------------------------------------------------------------------------
# Local mode
# ----------------------------------------------------------------------------

def validate_local(run_dir: Path) -> Report:
    rep = Report()
    run_id = run_dir.name
    metadata = load_metadata(run_dir)
    eval_results = extract_eval_results(run_dir)
    traj_dirs = {p.parent.name for p in run_dir.glob("*/*.traj.json")}

    if metadata is None:
        rep.fail("missing/unreadable metadata.json")
    if eval_results is None:
        rep.fail("missing/unreadable evaluation_results.json")
    if not traj_dirs:
        rep.fail("no *.traj.json trajectories found")
    if eval_results is None or metadata is None or not traj_dirs:
        return rep

    preds = None
    preds_path = run_dir / "preds.json"
    if preds_path.exists():
        try:
            with open(preds_path) as f:
                preds = json.load(f)
        except (json.JSONDecodeError, OSError):
            rep.fail("preds.json unreadable")

    summary = None
    summary_path = run_dir / SUMMARY_FILE
    if summary_path.exists():
        try:
            with open(summary_path) as f:
                summary = json.load(f)
        except (json.JSONDecodeError, OSError):
            rep.fail("summary.json unreadable")

    _check_eval_and_resolves(rep, run_id, metadata, eval_results, preds, len(traj_dirs), summary)

    # Name the instances behind a preds/trajectory mismatch and say how to fix it. This case
    # cannot self-heal: the agent's resume skips any instance already keyed in preds.json, so
    # an instance whose sandbox died (prediction written, trajectory never saved) stays broken
    # until its key is removed.
    if isinstance(preds, dict) and traj_dirs:
        orphans = sorted(set(preds) - traj_dirs)
        if orphans:
            rep.fail(f"{len(orphans)} prediction(s) have no trajectory: {orphans[:5]} — remove "
                     f"these keys from preds.json and re-run generate (resume skips instances "
                     f"already listed in preds.json, so they cannot be regenerated otherwise)")

    # Rule 3 extra (local only): exit_statuses tally vs trajectories
    if isinstance(summary, dict) and "exit_statuses" in summary:
        actual = extract_exit_statuses(run_dir)
        if actual and summary["exit_statuses"] != actual:
            rep.fail(f"summary.exit_statuses != trajectories: {summary['exit_statuses']} vs {actual}")
        else:
            rep.ok("summary.exit_statuses matches trajectories")
    return rep


# ----------------------------------------------------------------------------
# PR mode (read-only, via HuggingFace)
# ----------------------------------------------------------------------------

def pr_scope_findings(main_tree: dict, pr_tree: dict) -> tuple[str | None, list[tuple[str, str]]]:
    """Pure PR-scope check (no I/O). Returns (run_id, [(level, message), ...]).

    Enforces Rule 5: exactly one NEW run folder is added, and EVERY changed path
    (add / modify / remove) lives under runs/<that run>/ — so a PR can't touch the
    leaderboard, another run, or stray files. run_id is None if not exactly one.
    """
    findings: list[tuple[str, str]] = []

    def run_dirs(tree: dict) -> set[str]:
        return {p.split("/")[1] for p in tree
                if p.startswith(f"{RUNS_PREFIX}/") and len(p.split("/")) >= 3}

    new_runs = run_dirs(pr_tree) - run_dirs(main_tree)
    if len(new_runs) != 1:
        findings.append(("FAIL", f"PR must add exactly one new run (found {sorted(new_runs)})"))
        return None, findings
    run_id = next(iter(new_runs))
    findings.append(("OK", f"PR adds exactly one new run: {run_id}"))

    changed = {p for p in set(main_tree) | set(pr_tree)
               if main_tree.get(p) != pr_tree.get(p)}
    out_of_scope = sorted(p for p in changed
                          if not p.startswith(f"{RUNS_PREFIX}/{run_id}/"))
    if out_of_scope:
        findings.append(("FAIL",
                         f"PR changes {len(out_of_scope)} path(s) outside runs/{run_id}/: {out_of_scope[:5]}"))
    else:
        findings.append(("OK", f"PR touches only runs/{run_id}/ ({len(changed)} files)"))
    return run_id, findings


def validate_pr(repo: str, pr: int) -> Report:
    from huggingface_hub import HfApi, hf_hub_download  # lazy: HF only for PR mode
    api = HfApi()
    ref = f"refs/pr/{pr}"
    rep = Report()

    def file_tree(revision: str) -> dict[str, str]:
        """Map every file path -> content id (blob_id, or LFS sha) at a revision.

        Uses repo_info(files_metadata=True) — portable back to old huggingface_hub
        (list_repo_tree only exists in >=0.23).
        """
        info = api.repo_info(repo_id=repo, repo_type="dataset", revision=revision,
                             files_metadata=True)
        out: dict[str, str] = {}
        for sibling in info.siblings or []:
            cid = getattr(sibling, "blob_id", None)
            if cid is None:
                lfs = getattr(sibling, "lfs", None)
                cid = lfs.get("sha256") if isinstance(lfs, dict) else None
            out[sibling.rfilename] = cid
        return out

    try:
        main_tree = file_tree("main")
        pr_tree = file_tree(ref)
    except Exception as e:
        rep.fail(f"could not list repo trees ({e})")
        return rep

    # Rule 5: scope (pure logic in pr_scope_findings, unit-tested without HF).
    run_id, scope = pr_scope_findings(main_tree, pr_tree)
    for level, msg in scope:
        (rep.ok if level == "OK" else rep.fail)(msg)

    if run_id is None:
        return rep
    if not RUN_ID_RE.match(run_id):
        rep.fail(f"run_id contains unsafe characters: {run_id!r}")
        return rep

    def fetch(name: str):
        try:
            path = hf_hub_download(repo_id=repo, repo_type="dataset", revision=ref,
                                   filename=f"{RUNS_PREFIX}/{run_id}/{name}")
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            rep.flag(f"could not fetch {name} from PR ({e})")
            return None

    metadata = fetch("metadata.json")
    eval_results = fetch("evaluation_results.json")
    preds = fetch("preds.json")
    summary = fetch(SUMMARY_FILE) if f"{RUNS_PREFIX}/{run_id}/{SUMMARY_FILE}" in pr_tree else None
    if metadata is None:
        rep.fail("PR run has no readable metadata.json")
    if eval_results is None:
        rep.fail("PR run has no readable evaluation_results.json")
        return rep

    # Count distinct instance dirs holding a trajectory (matches local mode, which
    # counts parent dirs) so an extra .traj.json in one dir can't diverge the count.
    n_traj = len({p.split("/")[2] for p in pr_tree
                  if p.startswith(f"{RUNS_PREFIX}/{run_id}/") and p.endswith(".traj.json")
                  and len(p.split("/")) >= 4})

    _check_eval_and_resolves(rep, run_id, metadata, eval_results, preds, n_traj, summary)
    rep.flag("PR mode does not recompute exit_statuses from trajectories (run local validate after merge)")
    return rep


def main():
    parser = argparse.ArgumentParser(description="Validate a benchmark run")
    parser.add_argument("run_dir", nargs="?", help="Local run directory")
    parser.add_argument("--repo", help="HF dataset repo for PR mode")
    parser.add_argument("--pr", type=int, help="PR number for PR mode")
    args = parser.parse_args()

    if args.pr is not None:
        repo = args.repo or "burakaydinofficial/Quantuzo"
        rep = validate_pr(repo, args.pr)
        rep.print(f"{repo} PR #{args.pr}")
    elif args.run_dir:
        run_dir = Path(args.run_dir)
        rep = validate_local(run_dir)
        rep.print(run_dir.name)
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(1 if rep.failed else 0)


if __name__ == "__main__":
    main()
