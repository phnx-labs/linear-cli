#!/usr/bin/env python3
"""Regression tests for the `linear` CLI.

The CLI is intentionally dependency-free, so tests use only stdlib unittest.
"""

import contextlib
import importlib.util
import io
import os
import sys
import types
import unittest
from importlib.machinery import SourceFileLoader

# The CLI is a single file named `linear` (no .py extension) — load it by path
# with an explicit source loader (spec_from_file_location can't guess a loader
# for an extension-less file).
_HERE = os.path.dirname(os.path.abspath(__file__))
_loader = SourceFileLoader("linear_cli", os.path.join(_HERE, "linear"))
_spec = importlib.util.spec_from_loader("linear_cli", _loader)
linear_cli = importlib.util.module_from_spec(_spec)
_loader.exec_module(linear_cli)


class CycleLabelTest(unittest.TestCase):
    def test_named_cycle_uses_name(self):
        self.assertEqual(
            linear_cli.cycle_label({"name": "Jun W4 — Land $10K MRR", "number": 19}),
            "Jun W4 — Land $10K MRR",
        )

    def test_numbered_nameless_cycle_falls_back_to_number(self):
        self.assertEqual(linear_cli.cycle_label({"name": None, "number": 20}), "Cycle 20")

    def test_number_zero_is_not_treated_as_missing(self):
        self.assertEqual(linear_cli.cycle_label({"name": None, "number": 0}), "Cycle 0")

    def test_none_node_is_no_cycle(self):
        self.assertEqual(linear_cli.cycle_label(None), "no cycle")

    def test_empty_node_is_no_cycle(self):
        self.assertEqual(linear_cli.cycle_label({}), "no cycle")

    def test_empty_name_falls_back_to_number(self):
        self.assertEqual(linear_cli.cycle_label({"name": "", "number": 7}), "Cycle 7")


class BulkUpdateTest(unittest.TestCase):
    def test_collect_update_identifiers_dedupes_positional_and_stdin_in_order(self):
        self.assertEqual(
            linear_cli.collect_update_identifiers(
                ["RUSH-1", "RUSH-2", "RUSH-1"],
                ["RUSH-3 RUSH-2\n", "RUSH-4\n"],
            ),
            ["RUSH-1", "RUSH-2", "RUSH-3", "RUSH-4"],
        )

    def test_bulk_update_continues_after_missing_issue_and_rolls_up_errors(self):
        args = types.SimpleNamespace()
        seen = []

        def resolve_issue(_api_key, _team_id, ident):
            seen.append(ident)
            if ident == "RUSH-404":
                return None
            return {"id": ident.lower(), "identifier": ident}

        def apply_update(_args, _cfg, _api_key, _team_id, issue, **_kwargs):
            if issue["identifier"] == "RUSH-3":
                raise RuntimeError("boom")
            return True

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                linear_cli.run_bulk_update(
                    args,
                    {},
                    "api-key",
                    "team-id",
                    ["RUSH-1", "RUSH-404", "RUSH-3"],
                    resolve_issue_fn=resolve_issue,
                    apply_update_fn=apply_update,
                )

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(seen, ["RUSH-1", "RUSH-404", "RUSH-3"])
        self.assertIn("[1/3] RUSH-1", stdout.getvalue())
        self.assertIn("[2/3] RUSH-404 -> not found", stdout.getvalue())
        self.assertIn("[3/3] RUSH-3", stdout.getvalue())
        self.assertIn("error: boom", stderr.getvalue())
        self.assertIn("1/3 updated. Failed: RUSH-404, RUSH-3", stderr.getvalue())

    def test_cmd_update_dedupes_stdin_and_keeps_going_after_bad_ticket(self):
        args = types.SimpleNamespace(
            done=False,
            proof=[],
            identifier=["RUSH-1", "RUSH-1", "RUSH-404"],
            stdin=True,
            project=None,
            milestone=None,
        )
        seen = []
        original_resolve_issue = linear_cli.resolve_issue
        original_apply_update = linear_cli._apply_update
        original_stdin = sys.stdin

        def resolve_issue(_api_key, _team_id, ident):
            seen.append(ident)
            if ident == "RUSH-404":
                return None
            return {"id": ident.lower(), "identifier": ident}

        def apply_update(_args, _cfg, _api_key, _team_id, _issue, **_kwargs):
            return True

        linear_cli.resolve_issue = resolve_issue
        linear_cli._apply_update = apply_update
        sys.stdin = io.StringIO("RUSH-2 RUSH-2\n")
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    linear_cli.cmd_update(args, {}, "api-key", "team-id")
        finally:
            linear_cli.resolve_issue = original_resolve_issue
            linear_cli._apply_update = original_apply_update
            sys.stdin = original_stdin

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(seen, ["RUSH-1", "RUSH-404", "RUSH-2"])
        self.assertIn("[1/3] RUSH-1", stdout.getvalue())
        self.assertIn("[2/3] RUSH-404 -> not found", stdout.getvalue())
        self.assertIn("[3/3] RUSH-2", stdout.getvalue())
        self.assertIn("2/3 updated. Failed: RUSH-404", stderr.getvalue())


class CycleScopeTest(unittest.TestCase):
    def test_active_scope_uses_active_cycle_id(self):
        meta = {"id": "active-id", "name": "Active", "number": 10}
        self.assertEqual(
            linear_cli.build_cycle_scope_from_resolved("active", active_meta=meta),
            ('cycle: { id: { eq: "active-id" } }', "Active", meta),
        )

    def test_next_scope_uses_next_cycle_id(self):
        meta = {"id": "next-id", "name": None, "number": 11}
        self.assertEqual(
            linear_cli.build_cycle_scope_from_resolved("next", next_meta=meta),
            ('cycle: { id: { eq: "next-id" } }', "Cycle 11", meta),
        )

    def test_all_scope_has_no_cycle_constraint(self):
        self.assertEqual(
            linear_cli.build_cycle_scope_from_resolved("all"),
            ("", "All issues", None),
        )

    def test_none_and_backlog_scope_filter_for_null_cycle(self):
        self.assertEqual(
            linear_cli.build_cycle_scope_from_resolved("none"),
            ("cycle: { null: true }", "Backlog (no cycle)", None),
        )
        self.assertEqual(
            linear_cli.build_cycle_scope_from_resolved("backlog"),
            ("cycle: { null: true }", "Backlog (no cycle)", None),
        )

    def test_named_scope_uses_resolved_cycle_id(self):
        node = {"id": "named-id", "name": "Launch", "number": 12}
        self.assertEqual(
            linear_cli.build_cycle_scope_from_resolved("Launch", cycle_node=node),
            ('cycle: { id: { eq: "named-id" } }', "Launch", node),
        )

    def test_raw_id_scope_keeps_user_supplied_label(self):
        node = {"id": "raw-id", "name": None}
        self.assertEqual(
            linear_cli.build_cycle_scope_from_resolved("raw-id", cycle_node=node),
            ('cycle: { id: { eq: "raw-id" } }', "raw-id", node),
        )


class NameResolutionTest(unittest.TestCase):
    def test_exact_match_beats_newer_substring_match(self):
        nodes = [
            {"id": "new-substring", "name": "Launch Plan", "updatedAt": "2026-07-17T00:00:00Z"},
            {"id": "old-exact", "name": "Launch", "updatedAt": "2026-07-01T00:00:00Z"},
        ]
        self.assertEqual(
            linear_cli._select_named_node(nodes, "Launch", "project")["id"],
            "old-exact",
        )

    def test_unknown_strict_name_raises_lookup_error(self):
        with self.assertRaisesRegex(LookupError, "project 'Missing' not found"):
            linear_cli._select_named_node([], "Missing", "project", strict=True)

    def test_ambiguous_name_picks_most_recent_and_warns(self):
        nodes = [
            {"id": "old", "name": "Launch A", "updatedAt": "2026-07-01T00:00:00Z"},
            {"id": "new", "name": "Launch B", "updatedAt": "2026-07-16T00:00:00Z"},
        ]
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            match = linear_cli._select_named_node(nodes, "Launch", "milestone")
        self.assertEqual(match["id"], "new")
        self.assertIn("matched 2 milestones", stderr.getvalue())
        self.assertIn("picked 'Launch B'", stderr.getvalue())

    def test_cycle_resolution_accepts_number_and_uses_updated_at_for_ambiguity(self):
        cycles = [
            {"id": "old", "number": 1, "name": "Sprint Alpha", "updatedAt": "2026-07-01T00:00:00Z"},
            {"id": "number", "number": 42, "name": "Other", "updatedAt": "2026-07-02T00:00:00Z"},
            {"id": "new", "number": 2, "name": "Sprint Beta", "updatedAt": "2026-07-17T00:00:00Z"},
        ]
        self.assertEqual(linear_cli._select_cycle_node(cycles, "42")["id"], "number")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            match = linear_cli._select_cycle_node(cycles, "Sprint")
        self.assertEqual(match["id"], "new")
        self.assertIn("matched 2 cycles", stderr.getvalue())

    def test_label_wrapper_uses_prefetched_labels_without_network_logic(self):
        original = linear_cli.list_team_labels
        labels = [
            {"id": "old", "name": "bug urgent", "updatedAt": "2026-07-01T00:00:00Z"},
            {"id": "new", "name": "bug backlog", "updatedAt": "2026-07-17T00:00:00Z"},
        ]
        linear_cli.list_team_labels = lambda _api_key, _team_id: labels
        try:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                match = linear_cli.resolve_label_by_value("api-key", "team-id", "bug")
            self.assertEqual(match["id"], "new")
            self.assertIn("matched 2 labels", stderr.getvalue())
            with self.assertRaisesRegex(LookupError, "label 'missing' not found"):
                linear_cli.resolve_label_by_value("api-key", "team-id", "missing", strict=True)
        finally:
            linear_cli.list_team_labels = original


if __name__ == "__main__":
    unittest.main()
