#!/usr/bin/env python3
"""
Unit tests for the summary/leaderboard/validation tooling.

Stdlib-only (unittest) and hermetic — every fixture is built in a temp dir, so
these run from a clean checkout with no HuggingFace access and no downloaded runs.

    python3 -m unittest discover -s tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import leaderboard_lib as lib  # noqa: E402
import validate_run as vr  # noqa: E402
import generate_summary as gs  # noqa: E402

SRC_PATCH = "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n+    return 1\n"
TEST_PATCH = "diff --git a/tests/test_x.py b/tests/test_x.py\n+++ b/tests/test_x.py\n+assert True\n"


def setUpModule():
    # tiny test benchmark so 2-instance fixtures satisfy the exact-size gate
    vr.SUBSET_SIZES["swe-bench-unit"] = 2


def tearDownModule():
    vr.SUBSET_SIZES.pop("swe-bench-unit", None)


def write_run(root, run_id="swe-lite-m-kv-f16-f16-20260101_000000",
              total=2, resolved=1, failed=None, error=0, submitted=None,
              patch=SRC_PATCH, with_summary=False, summary_overrides=None,
              benchmark="swe-bench-unit"):
    """Build a `total`-instance, internally-consistent run folder; return (run_dir, first_iid)."""
    run = Path(root) / run_id
    run.mkdir(parents=True, exist_ok=True)
    if failed is None:
        failed = max(0, total - resolved - error)
    if submitted is None:
        submitted = total if patch.strip() else 0
    iids = [f"proj__proj-{i}" for i in range(total)]
    (run / "metadata.json").write_text(json.dumps({
        "run_id": run_id, "timestamp": "2026-01-01T00:00:00Z", "benchmark": benchmark,
        "model": {"name": "m", "file": "m.gguf"},
        "inference": {"accelerator": "gpu", "ctx_size": 65536, "kv_type_k": "f16", "kv_type_v": "f16"},
        "agent": {"name": "mini-swe-agent", "branch": "v2", "version": "2.2.4"},
    }))
    (run / "evaluation_results.json").write_text(json.dumps({
        "total_instances": total, "resolved": resolved, "failed": failed, "error": error,
        "predictions_submitted": submitted,
        "resolution_rate": (resolved / total * 100) if total else 0.0,
        "instances": {"resolved_ids": iids[:resolved], "unresolved_ids": [], "error_ids": []},
    }))
    preds = {}
    for i, iid in enumerate(iids):
        (run / iid).mkdir(exist_ok=True)
        (run / iid / f"{iid}.traj.json").write_text(json.dumps(
            {"instance_id": iid, "info": {"exit_status": "Submitted"}, "messages": []}))
        preds[iid] = {"model_patch": patch if i < submitted else "", "model_name_or_path": "local/m"}
    (run / "preds.json").write_text(json.dumps(preds))
    if with_summary:
        summary = lib.generate_summary(run)
        if summary_overrides:
            summary.update(summary_overrides)
        (run / "summary.json").write_text(json.dumps(summary))
    return run, iids[0]


class TestLeaderboardLib(unittest.TestCase):
    def test_build_row_maps_fields(self):
        meta = {"run_id": "r", "timestamp": "t", "benchmark": "b",
                "model": {"name": "m", "file": "f"},
                "inference": {"accelerator": "gpu", "ctx_size": 42, "kv_type_k": "q8_0", "kv_type_v": "q4_0"},
                "agent": {"version": "2.2.4", "branch": "v2"}}
        ev = {"total_instances": 300, "resolved": 100, "failed": 190, "error": 10, "resolution_rate": 33.3}
        row = lib.build_leaderboard_row(meta, ev, {"Submitted": 300})
        self.assertEqual(row["kv_type_k"], "q8_0")
        self.assertEqual((row["resolved"], row["total"], row["error"]), (100, 300, 10))
        self.assertEqual(row["exit_statuses"], {"Submitted": 300})

    def test_build_row_missing_eval_is_zeros_and_omits_exit_statuses(self):
        row = lib.build_leaderboard_row({"run_id": "r"}, None, None)
        self.assertEqual((row["resolved"], row["total"], row["rate"]), (0, 0, 0.0))
        self.assertNotIn("exit_statuses", row)

    def test_summary_matches_eval(self):
        ev = {"total_instances": 20, "resolved": 12, "failed": 8, "error": 0, "resolution_rate": 60.0}
        good = {"total": 20, "resolved": 12, "failed": 8, "error": 0, "rate": 60.0}
        self.assertEqual(lib.summary_matches_eval(good, ev), [])
        self.assertEqual(lib.summary_matches_eval({**good, "resolved": 11}, ev)[0][0], "resolved")
        # rate tolerance
        self.assertEqual(lib.summary_matches_eval({**good, "rate": 60.004}, ev), [])
        self.assertEqual(lib.summary_matches_eval(good, None), [])

    def test_build_row_coerces_bad_numerics(self):
        # null / list / string numeric fields must not reach the board
        ev = {"total_instances": 300, "resolved": None, "failed": [1], "error": 5, "resolution_rate": "x"}
        row = lib.build_leaderboard_row({"run_id": "r"}, ev, None)
        self.assertEqual((row["total"], row["resolved"], row["failed"], row["error"]), (300, 0, 0, 5))
        self.assertEqual(row["rate"], 0.0)

    def test_generate_summary_ok_and_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp)
            summary = lib.generate_summary(run)
            self.assertEqual(summary["schema_version"], lib.SCHEMA_VERSION)
            self.assertEqual((summary["resolved"], summary["total"]), (1, 2))
            self.assertEqual(summary["exit_statuses"], {"Submitted": 2})
            # summary (minus schema_version) == build_leaderboard_row(metadata, eval, exit_statuses)
            row = lib.build_leaderboard_row(lib.load_metadata(run), lib.extract_eval_results(run),
                                            lib.extract_exit_statuses(run))
            self.assertEqual({k: v for k, v in summary.items() if k != "schema_version"}, row)
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            self.assertRaises(ValueError, lib.generate_summary, empty)


class TestValidateRun(unittest.TestCase):
    def test_patch_touches_tests(self):
        self.assertEqual(vr.patch_touches_tests(TEST_PATCH), ["tests/test_x.py"])
        self.assertEqual(vr.patch_touches_tests(SRC_PATCH), [])
        self.assertEqual(vr.patch_touches_tests(""), [])
        # agent scratch reproduction scripts at the repo root are NOT the test suite
        self.assertEqual(vr.patch_touches_tests("+++ b/test_fix.py\n+++ b/test_edge_cases.py"), [])
        self.assertEqual(vr.patch_touches_tests("+++ b/reproduce_bug.py"), [])
        # real suite locations still flag
        self.assertEqual(vr.patch_touches_tests("+++ b/conftest.py"), ["conftest.py"])
        self.assertEqual(vr.patch_touches_tests("+++ b/pkg/tests/test_x.py"), ["pkg/tests/test_x.py"])

    def test_orphaned_prediction_detected_when_counts_match(self):
        # A prediction whose trajectory is missing while the trajectory COUNT still
        # matches total_instances — only the set-difference check catches this, so
        # deleting that check must turn this test red.
        with tempfile.TemporaryDirectory() as tmp:
            run, iid = write_run(tmp)
            (run / iid).rename(run / "proj__proj-99")  # traj now filed under a different id
            rep = vr.validate_local(run)
            self.assertTrue(rep.failed)
            self.assertTrue(any("no trajectory" in m for _, m in rep.findings),
                            f"orphan check did not fire: {rep.findings}")

    def test_instances_as_list_does_not_crash(self):
        # run_evaluation.py's fallback writes instances as a list; with preds present
        # and counts consistent, that must FLAG (gaming checks skipped), not FAIL or crash.
        rep = vr.Report()
        ev = {"total_instances": 300, "resolved": 5, "failed": 100, "error": 0,
              "predictions_submitted": 300, "instances": [{"instance_id": "x"}]}
        preds = {f"i{k}": {"model_patch": "x"} for k in range(300)}
        vr._check_eval_and_resolves(rep, "run", {"run_id": "run", "benchmark": "swe-bench-lite"},
                                    ev, preds, 300, None)
        self.assertFalse(rep.failed)
        self.assertTrue(any("instances" in m for _, m in rep.findings))

    def test_validate_local_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp, with_summary=True)
            rep = vr.validate_local(run)
            self.assertFalse(rep.failed)
            msgs = " ".join(m for _, m in rep.findings)
            self.assertIn("non-empty patches", msgs)  # the gaming check actually ran
            self.assertIn("match", msgs)              # the summary-vs-eval check ran

    def test_validate_local_nondict_summary_fails_not_crashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp)
            (run / "summary.json").write_text("[]")  # valid JSON, not an object
            rep = vr.validate_local(run)             # must not raise
            self.assertTrue(rep.failed)

    def test_validate_local_nondict_preds_fails_not_crashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp)
            (run / "preds.json").write_text("[]")
            rep = vr.validate_local(run)             # must not raise
            self.assertTrue(rep.failed)

    def test_validate_local_scalar_summary_no_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp)
            (run / "summary.json").write_text("5")   # JSON scalar (not list/dict)
            rep = vr.validate_local(run)             # must not raise (was a TypeError)
            self.assertTrue(rep.failed)

    def test_partial_run_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp, benchmark="swe-bench-lite", total=1)  # 1 of 300
            rep = vr.validate_local(run)
            self.assertTrue(rep.failed)
            self.assertTrue(any("partial" in m for _, m in rep.findings))

    def test_check_handles_weird_types_no_crash(self):
        # null numeric fields + non-dict/str preds values must not crash the gate
        rep = vr.Report()
        ev = {"total_instances": 300, "resolved": None, "failed": None, "error": 0,
              "predictions_submitted": None, "instances": {"resolved_ids": ["a", "b"]}}
        preds = {"a": "oops", "b": {"model_patch": 123}, "c": {"model_patch": "x"}}
        vr._check_eval_and_resolves(rep, "run", {"run_id": "run", "benchmark": "swe-bench-lite"},
                                    ev, preds, 300, None)  # must not raise
        self.assertTrue(any("EMPTY patches" in m for _, m in rep.findings))

    def test_resolved_exceeds_nonempty_patches_fails(self):
        # anti-gaming: claim 300 resolved with 0 non-empty patches, instances as a list
        rep = vr.Report()
        ev = {"total_instances": 300, "resolved": 300, "failed": 0, "error": 0,
              "predictions_submitted": 300, "instances": []}
        preds = {f"i{k}": {"model_patch": ""} for k in range(300)}
        vr._check_eval_and_resolves(rep, "run", {"run_id": "run", "benchmark": "swe-bench-lite"},
                                    ev, preds, 300, None)
        self.assertTrue(rep.failed)
        self.assertTrue(any("only 0 non-empty" in m for _, m in rep.findings))

    def test_nondict_eval_fails_not_crashes(self):
        rep = vr.Report()
        vr._check_eval_and_resolves(rep, "run", {"run_id": "run"}, [], None, None, None)  # eval is a list
        self.assertTrue(rep.failed)
        self.assertTrue(any("evaluation_results.json is not a JSON object" in m for _, m in rep.findings))

    def test_nondict_metadata_fails_not_crashes(self):
        rep = vr.Report()
        ev = {"total_instances": 300, "resolved": 0, "failed": 0, "error": 0, "instances": {}}
        vr._check_eval_and_resolves(rep, "run", [1, 2], ev, None, 300, None)  # metadata is a list
        self.assertTrue(any("metadata.json is not a JSON object" in m for _, m in rep.findings))

    def test_null_eval_field_fails(self):
        # a present-but-null numeric field would otherwise publish null onto the board
        rep = vr.Report()
        ev = {"total_instances": 1, "resolved": None, "failed": 0, "error": 0, "instances": {}}
        vr._check_eval_and_resolves(rep, "run", {"run_id": "run"},
                                    ev, {"proj__proj-1": {"model_patch": "x"}}, 1, None)
        self.assertTrue(rep.failed)
        self.assertTrue(any("not a number" in m for _, m in rep.findings))

    def test_resolved_without_preds_fails(self):
        rep = vr.Report()
        ev = {"total_instances": 300, "resolved": 5, "failed": 0, "error": 0,
              "predictions_submitted": 5, "instances": {"resolved_ids": []}}
        vr._check_eval_and_resolves(rep, "run", {"run_id": "run", "benchmark": "swe-bench-lite"},
                                    ev, None, 300, None)  # preds absent, but claims resolves
        self.assertTrue(rep.failed)
        self.assertTrue(any("no readable preds.json" in m for _, m in rep.findings))

    def test_validate_local_empty_resolved_patch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp, patch="   ")  # resolved but empty patch
            rep = vr.validate_local(run)
            self.assertTrue(rep.failed)
            self.assertTrue(any("EMPTY" in m for _, m in rep.findings))

    def test_validate_local_summary_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp, with_summary=True, summary_overrides={"resolved": 999})
            self.assertTrue(vr.validate_local(run).failed)

    def test_validate_local_test_touching_patch_flags_not_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp, patch=TEST_PATCH)
            rep = vr.validate_local(run)
            self.assertFalse(rep.failed)  # flag, not fail
            self.assertTrue(any(lvl == "FLAG" and "test file" in m for lvl, m in rep.findings))


class TestPrScope(unittest.TestCase):
    """Pure PR-scope logic (the security gate), tested without HuggingFace."""

    def _main_tree(self):
        return {"leaderboard.jsonl": "L", "README.md": "R",
                "runs/old/metadata.json": "a", "runs/old/preds.json": "b"}

    def test_legit_single_run_add_passes(self):
        main = self._main_tree()
        pr = {**main, "runs/new/metadata.json": "m", "runs/new/preds.json": "p"}
        run_id, findings = vr.pr_scope_findings(main, pr)
        self.assertEqual(run_id, "new")
        self.assertFalse(any(lvl == "FAIL" for lvl, _ in findings))

    def test_editing_leaderboard_fails(self):
        main = self._main_tree()
        pr = {**main, "runs/new/metadata.json": "m", "leaderboard.v2.jsonl": "X"}
        _, findings = vr.pr_scope_findings(main, pr)
        self.assertTrue(any(lvl == "FAIL" and "outside" in m for lvl, m in findings))

    def test_modifying_other_run_fails(self):
        main = self._main_tree()
        pr = {**main, "runs/new/metadata.json": "m", "runs/old/preds.json": "TAMPERED"}
        _, findings = vr.pr_scope_findings(main, pr)
        self.assertTrue(any(lvl == "FAIL" and "outside" in m for lvl, m in findings))

    def test_deleting_existing_file_fails(self):
        main = self._main_tree()
        pr = {k: v for k, v in main.items() if k != "runs/old/preds.json"}
        pr["runs/new/metadata.json"] = "m"
        _, findings = vr.pr_scope_findings(main, pr)
        self.assertTrue(any(lvl == "FAIL" and "outside" in m for lvl, m in findings))

    def test_two_new_runs_fails(self):
        main = self._main_tree()
        pr = {**main, "runs/a/metadata.json": "1", "runs/b/metadata.json": "2"}
        run_id, findings = vr.pr_scope_findings(main, pr)
        self.assertIsNone(run_id)
        self.assertTrue(any(lvl == "FAIL" and "exactly one" in m for lvl, m in findings))


class TestRebuildLocal(unittest.TestCase):
    def test_clean_mismatch_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_run(tmp, run_id="swe-clean-20260101_000000", with_summary=True)
            write_run(tmp, run_id="swe-stale-20260102_000000", with_summary=True,
                      summary_overrides={"resolved": 999, "rate": 99.9})
            write_run(tmp, run_id="swe-nosum-20260103_000000", with_summary=False)
            (Path(tmp) / "not-a-run").mkdir()  # stray dir (no metadata) must be ignored
            rows, missing, mismatched = lib.build_leaderboard_rows_local(Path(tmp))
            self.assertEqual(set(rows), {"swe-clean-20260101_000000", "swe-stale-20260102_000000"})
            self.assertEqual(missing, ["swe-nosum-20260103_000000"])  # stray dir not reported
            self.assertEqual(mismatched, ["swe-stale-20260102_000000"])
            # the row is built from metadata+eval, so it carries EVAL's numbers, not the stale summary's
            self.assertEqual(rows["swe-stale-20260102_000000"]["resolved"], 1)
            self.assertNotIn("schema_version", rows["swe-clean-20260101_000000"])

    def test_summary_without_eval_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp, run_id="swe-noeval-20260104_000000", with_summary=True)
            (run / "evaluation_results.json").unlink()  # summary present, eval gone
            rows, missing, _ = lib.build_leaderboard_rows_local(Path(tmp))
            self.assertNotIn("swe-noeval-20260104_000000", rows)  # not trusted without eval
            self.assertIn("swe-noeval-20260104_000000", missing)


class TestNeedsSummary(unittest.TestCase):
    def test_needs_summary_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, _ = write_run(tmp, with_summary=False)
            self.assertTrue(gs.needs_summary(run))                      # missing
            gs.write_summary(run)
            self.assertFalse(gs.needs_summary(run))                     # current
            good = json.loads((run / "summary.json").read_text())
            (run / "summary.json").write_text(json.dumps({**good, "resolved": 42}))
            self.assertTrue(gs.needs_summary(run))                      # stale
            (run / "summary.json").write_text("[]")                     # non-dict, must not crash
            self.assertTrue(gs.needs_summary(run))


if __name__ == "__main__":
    unittest.main()
