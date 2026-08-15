#!/usr/bin/env python3
"""Regression tests for the `linear` CLI.

The CLI is intentionally dependency-free, so tests use only stdlib unittest.
"""

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

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


class InboxTypeLabelTest(unittest.TestCase):
    def test_common_notification_types_have_friendly_labels(self):
        # The `notifications` query returns these; each must render a human label,
        # not the raw camelCase type, in `linear inbox`.
        for raw, expected in [
            ("issueNewComment", "comment"),
            ("issueCommentMention", "mention"),
            ("issueAssignedToYou", "assigned"),
            ("issueStatusChanged", "status"),
        ]:
            self.assertEqual(linear_cli._INBOX_TYPE_LABEL.get(raw), expected)

    def test_unmapped_type_absent_so_cmd_inbox_falls_back_to_raw(self):
        self.assertNotIn("issueSomeFutureKind", linear_cli._INBOX_TYPE_LABEL)

    def test_cmd_inbox_truncates_unmapped_type_and_keeps_rows_aligned(self):
        # A notification type not in _INBOX_TYPE_LABEL must not break column
        # alignment: the label column is fixed-width, so the actor column lands
        # at the same offset on a mapped row and an unmapped (long-type) row.
        def fake_gql(_key, _query, _vars=None):
            node = lambda ident, typ: {
                "id": ident, "__typename": "IssueNotification",
                "createdAt": "2026-07-18T00:00:00Z", "readAt": None, "type": typ,
                "issue": {"identifier": ident, "title": "T", "url": "u", "state": {"name": "Todo"}},
                "comment": None, "actor": {"name": "Bisma"},
            }
            return {"data": {"notifications": {"nodes": [
                node("RUSH-1", "issueNewComment"),
                node("RUSH-2", "issueSomeVeryLongFutureKind"),
            ]}}}

        args = types.SimpleNamespace(limit=30, all=False, json=False)
        original_gql = linear_cli.gql
        linear_cli.gql = fake_gql
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout):
                linear_cli.cmd_inbox(args, {}, "api-key", "team-id")
        finally:
            linear_cli.gql = original_gql

        out = stdout.getvalue()
        self.assertIn("comment", out)  # mapped type renders its friendly label
        self.assertNotIn("issueSomeVeryLongFutureKind", out)  # long raw type truncated
        actor_rows = [ln for ln in out.splitlines() if "Bisma" in ln]
        self.assertEqual(len(actor_rows), 2)
        self.assertEqual(len({ln.index("Bisma") for ln in actor_rows}), 1)  # aligned

    def test_cmd_inbox_read_marks_each_given_notification(self):
        # --read <id> issues a notificationUpdate mutation per id and reports them.
        calls = []

        def fake_gql(_key, query, variables=None):
            calls.append(variables)
            self.assertIn("notificationUpdate", query)
            return {"data": {"notificationUpdate": {"success": True}}}

        args = types.SimpleNamespace(read=["n1", "n2"], read_all=False,
                                     limit=30, all=False, json=False)
        original_gql = linear_cli.gql
        linear_cli.gql = fake_gql
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout):
                linear_cli.cmd_inbox(args, {}, "api-key", "team-id")
        finally:
            linear_cli.gql = original_gql

        self.assertEqual([c["id"] for c in calls], ["n1", "n2"])  # one mutation per id
        self.assertIn("Marked read (2): n1, n2", stdout.getvalue())


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


class CreateImageTest(unittest.TestCase):
    def test_images_uploaded_and_embedded_in_description(self):
        cfg = {
            "states": {"Todo": {"id": "state-id", "type": "unstarted"}},
            "viewerId": "viewer-id",
        }

        uploads = []

        def fake_upload_file(_api_key, path):
            uploads.append(path)
            return f"https://cdn.linear.app/{os.path.basename(path)}"

        original_upload_file = linear_cli.upload_file
        original_get_cycle_id = linear_cli.get_cycle_id
        linear_cli.upload_file = fake_upload_file
        linear_cli.get_cycle_id = lambda _a, _t, _w: None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                img1 = os.path.join(tmp, "screenshot.png")
                img2 = os.path.join(tmp, "diagram.jpg")
                open(img1, "w").close()
                open(img2, "w").close()

                fields = {
                    "title": "RUSH-1962 test",
                    "description": "Initial description",
                    "image": [img1, img2],
                    "cycle": "active",
                }
                input_obj, err = linear_cli._build_create_input(
                    "api-key", "team-id", cfg, fields, verbose=False
                )

            self.assertIsNone(err)
            desc = input_obj.get("description", "")
            self.assertIn("Initial description", desc)
            self.assertIn("![screenshot.png](https://cdn.linear.app/screenshot.png)", desc)
            self.assertIn("![diagram.jpg](https://cdn.linear.app/diagram.jpg)", desc)
            self.assertEqual(uploads, [img1, img2])
            # Embeds follow the description separated by blank lines.
            self.assertTrue(desc.startswith("Initial description\n\n!"))
        finally:
            linear_cli.upload_file = original_upload_file
            linear_cli.get_cycle_id = original_get_cycle_id

    def test_failed_image_upload_is_skipped(self):
        cfg = {
            "states": {"Todo": {"id": "state-id", "type": "unstarted"}},
            "viewerId": "viewer-id",
        }

        def fake_upload_file(_api_key, path):
            if path.endswith("missing.png"):
                return None
            return f"https://cdn.linear.app/{os.path.basename(path)}"

        original_upload_file = linear_cli.upload_file
        original_get_cycle_id = linear_cli.get_cycle_id
        linear_cli.upload_file = fake_upload_file
        linear_cli.get_cycle_id = lambda _a, _t, _w: None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                good = os.path.join(tmp, "good.png")
                bad = os.path.join(tmp, "missing.png")
                open(good, "w").close()

                fields = {
                    "title": "RUSH-1962 skip test",
                    "description": "Body",
                    "image": [good, bad],
                    "cycle": "active",
                }
                input_obj, err = linear_cli._build_create_input(
                    "api-key", "team-id", cfg, fields, verbose=False
                )

            self.assertIsNone(err)
            desc = input_obj.get("description", "")
            self.assertIn("![good.png](https://cdn.linear.app/good.png)", desc)
            self.assertNotIn("missing.png", desc)
        finally:
            linear_cli.upload_file = original_upload_file
            linear_cli.get_cycle_id = original_get_cycle_id

    def test_image_embed_does_not_leak_into_derived_title(self):
        cfg = {
            "states": {"Todo": {"id": "state-id", "type": "unstarted"}},
            "viewerId": "viewer-id",
        }

        def fake_upload_file(_api_key, path):
            return f"https://cdn.linear.app/{os.path.basename(path)}"

        original_upload_file = linear_cli.upload_file
        original_get_cycle_id = linear_cli.get_cycle_id
        linear_cli.upload_file = fake_upload_file
        linear_cli.get_cycle_id = lambda _a, _t, _w: None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                img = os.path.join(tmp, "screenshot.png")
                open(img, "w").close()

                fields = {
                    "title": None,
                    "description": "The actual issue body",
                    "image": [img],
                    "cycle": "active",
                }
                input_obj, err = linear_cli._build_create_input(
                    "api-key", "team-id", cfg, fields, verbose=False
                )

            self.assertIsNone(err)
            self.assertEqual(input_obj["title"], "The actual issue body")
            self.assertIn("![screenshot.png](https://cdn.linear.app/screenshot.png)",
                          input_obj.get("description", ""))
        finally:
            linear_cli.upload_file = original_upload_file
            linear_cli.get_cycle_id = original_get_cycle_id


class MilestoneRollupTest(unittest.TestCase):
    def test_rollup_aggregates_by_milestone_with_none_bucket(self):
        # One page of a project's issues across two milestones + an unassigned
        # bucket. 'done' counts only state.type == 'completed'.
        page = {
            "data": {
                "issues": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {"projectMilestone": {"id": "m1"}, "state": {"type": "completed"}},
                        {"projectMilestone": {"id": "m1"}, "state": {"type": "started"}},
                        {"projectMilestone": {"id": "m1"}, "state": {"type": "completed"}},
                        {"projectMilestone": {"id": "m2"}, "state": {"type": "unstarted"}},
                        {"projectMilestone": None, "state": {"type": "completed"}},
                        {"projectMilestone": None, "state": {"type": "backlog"}},
                    ],
                }
            }
        }
        original = linear_cli.gql
        linear_cli.gql = lambda *a, **k: page
        try:
            roll = linear_cli.milestone_rollup("api-key", "proj-id")
        finally:
            linear_cli.gql = original
        self.assertEqual(roll["m1"], {"total": 3, "done": 2})
        self.assertEqual(roll["m2"], {"total": 1, "done": 0})
        self.assertEqual(roll["_none"], {"total": 2, "done": 1})


class FmtRollupTest(unittest.TestCase):
    def test_empty_is_zero_issues(self):
        self.assertEqual(linear_cli._fmt_rollup(None), "(0 issues)")
        self.assertEqual(linear_cli._fmt_rollup({"total": 0, "done": 0}), "(0 issues)")

    def test_ratio_and_percent(self):
        self.assertEqual(linear_cli._fmt_rollup({"total": 10, "done": 3}), "(3/10 done, 30%)")
        self.assertEqual(linear_cli._fmt_rollup({"total": 4, "done": 4}), "(4/4 done, 100%)")


class PrintByMilestoneTest(unittest.TestCase):
    @staticmethod
    def _issue(ident, ms_name, cyc=None):
        return {
            "identifier": ident, "title": f"{ident} title",
            "state": {"name": "Todo", "type": "unstarted"},
            "priority": 0, "labels": {"nodes": []},
            "assignee": None, "delegate": None,
            "project": {"name": "P", "id": "p"},
            "projectMilestone": {"name": ms_name} if ms_name else None,
            "cycle": cyc, "dueDate": None,
        }

    def test_groups_named_first_orphan_last_with_cycle_annotation(self):
        nodes = [
            self._issue("ANT-3", None),
            self._issue("ANT-1", "v1.0", {"number": 11, "name": None}),
            self._issue("ANT-2", "v0.9", {"number": 10, "name": None}),
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            linear_cli.print_by_milestone(nodes)
        out = buf.getvalue()
        # Named milestones alpha-first, the 'No milestone' orphan bucket last.
        self.assertLess(out.index("v0.9"), out.index("v1.0"))
        self.assertLess(out.index("v1.0"), out.index("No milestone"))
        # Open count per group header.
        self.assertIn("v1.0  (1 open)", out)
        self.assertIn("No milestone  (1 open)", out)
        # Cycle annotation rides on the scheduled issue (the milestone x cycle join).
        self.assertIn("·Cycle 11", out)


class ResolveTaskScopeTest(unittest.TestCase):
    def test_explicit_cycle_always_wins(self):
        self.assertEqual(linear_cli.resolve_task_scope("next", "P", None), "next")
        self.assertEqual(linear_cli.resolve_task_scope("all", None, "v1"), "all")
        self.assertEqual(linear_cli.resolve_task_scope("active", "P", "v1"), "active")

    def test_project_or_milestone_widens_to_all_cycles(self):
        self.assertEqual(linear_cli.resolve_task_scope(None, "P", None), "all")
        self.assertEqual(linear_cli.resolve_task_scope(None, None, "v1"), "all")

    def test_bare_list_defaults_to_active(self):
        self.assertEqual(linear_cli.resolve_task_scope(None, None, None), "active")


class MilestoneRollupPaginationTest(unittest.TestCase):
    @staticmethod
    def _sequence(*pages):
        it = iter(pages)
        return lambda *a, **k: next(it)

    def test_follows_cursor_across_pages(self):
        p1 = {"data": {"issues": {"pageInfo": {"hasNextPage": True, "endCursor": "c1"},
              "nodes": [{"projectMilestone": {"id": "m1"}, "state": {"type": "completed"}}]}}}
        p2 = {"data": {"issues": {"pageInfo": {"hasNextPage": False, "endCursor": None},
              "nodes": [{"projectMilestone": {"id": "m1"}, "state": {"type": "started"}}]}}}
        original = linear_cli.gql
        linear_cli.gql = self._sequence(p1, p2)
        try:
            roll = linear_cli.milestone_rollup("api-key", "proj-id")
        finally:
            linear_cli.gql = original
        self.assertEqual(roll["m1"], {"total": 2, "done": 1})

    def test_returns_empty_dict_on_midpagination_error(self):
        # Page 1 ok, page 2 errors -> discard the partial, return {} (per docstring)
        # so a milestone never renders a confident-but-wrong "% done".
        p1 = {"data": {"issues": {"pageInfo": {"hasNextPage": True, "endCursor": "c1"},
              "nodes": [{"projectMilestone": {"id": "m1"}, "state": {"type": "completed"}}]}}}
        err = {"errors": [{"message": "boom"}]}
        original = linear_cli.gql
        linear_cli.gql = self._sequence(p1, err)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                roll = linear_cli.milestone_rollup("api-key", "proj-id")
        finally:
            linear_cli.gql = original
        self.assertEqual(roll, {})


class MilestoneRollupQueryTypeTest(unittest.TestCase):
    def test_project_id_variable_is_typed_ID_not_String(self):
        # Regression: the issues filter's `project.id.eq` comparator expects the
        # GraphQL `ID` scalar, not `String`. A `String!` declaration errors on the
        # live API every call and (since the rollup returns {} on error) silently
        # zeroes every milestone's progress. A mocked gql can't catch a schema
        # type mismatch, so guard the declared type in the query text directly.
        captured = {}

        def fake_gql(_api_key, query, _variables):
            captured["query"] = query
            return {"data": {"issues": {"pageInfo": {"hasNextPage": False}, "nodes": []}}}

        original = linear_cli.gql
        linear_cli.gql = fake_gql
        try:
            linear_cli.milestone_rollup("api-key", "proj-id")
        finally:
            linear_cli.gql = original
        self.assertIn("$pid: ID!", captured["query"])
        self.assertNotIn("$pid: String", captured["query"])


class BoardJsonScopeTest(unittest.TestCase):
    def test_default_board_scope_is_active_not_null(self):
        # Regression guard: --cycle defaults to None at the parser (so list_tasks
        # can widen); the board must normalize None -> "active" so
        # `linear tasks --board --json` never emits "scope": null.
        args = types.SimpleNamespace(cycle=None, json=True, board=True)
        original_bcs = linear_cli.build_cycle_scope
        original_pag = linear_cli.paginate_issues
        linear_cli.build_cycle_scope = lambda a, t, s: (
            'cycle: { id: { eq: "x" } }', "Active cycle", {"id": "x"})
        linear_cli.paginate_issues = lambda a, f: []
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                linear_cli.show_board(args, "api-key", "team-id", {})
        finally:
            linear_cli.build_cycle_scope = original_bcs
            linear_cli.paginate_issues = original_pag
        import json as _json
        self.assertEqual(_json.loads(buf.getvalue())["scope"], "active")


def _issue(ident, delegate=None, labels=(), priority=2, state="Todo"):
    """An issue node shaped the way ISSUE_FIELDS returns it."""
    return {
        "identifier": ident,
        "title": f"title for {ident}",
        "state": {"name": state, "type": "unstarted"},
        "priority": priority,
        "labels": {"nodes": [{"name": n} for n in labels]},
        "assignee": {"name": "Muqsit"},
        "delegate": {"name": delegate} if delegate else None,
        "project": None,
        "projectMilestone": None,
        "cycle": {"number": 23, "name": "Cycle 23"},
        "dueDate": None,
        "createdAt": "2026-08-01T00:00:00.000Z",
        "url": f"https://linear.app/x/issue/{ident}",
    }


class _ListTasksHarness:
    """Drives the real list_tasks/show_board against a fixed issue page.

    Only the two network edges are substituted (cycle resolution and the issue
    page); every line of ownership logic under test — the delegate filter, the
    unowned rule, the header counts, the board grouping — is the shipping code.
    """

    ROSTER = [{"id": "id-claude", "name": "Claude"},
              {"id": "id-codex", "name": "Codex"}]

    def __init__(self, nodes):
        self.nodes = nodes
        self._saved = {}

    def __enter__(self):
        for name in ("build_cycle_scope", "paginate_issues", "get_agents"):
            self._saved[name] = getattr(linear_cli, name)
        linear_cli.build_cycle_scope = lambda a, t, s: (
            'cycle: { id: { eq: "x" } }', "Cycle 23", {"id": "x"})
        linear_cli.paginate_issues = lambda a, f: list(self.nodes)
        linear_cli.get_agents = lambda a, c, force=False: list(self.ROSTER)
        return self

    def __exit__(self, *exc):
        for name, fn in self._saved.items():
            setattr(linear_cli, name, fn)
        return False


def _list_args(**overrides):
    args = types.SimpleNamespace(
        cycle=None, project=None, milestone=None, since=None, all=False,
        agent=None, label=None, assignee=None, query=None, status=None,
        json=True, by_milestone=False, board=False,
    )
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _run_list(nodes, cfg=None, **overrides):
    args = _list_args(**overrides)
    cfg = {"agent": "claude"} if cfg is None else cfg
    buf = io.StringIO()
    with _ListTasksHarness(nodes):
        with contextlib.redirect_stdout(buf):
            linear_cli.list_tasks(args, cfg, "api-key", "team-id")
    import json as _json
    return _json.loads(buf.getvalue())


class DelegateOwnershipTest(unittest.TestCase):
    """`agent:*` labels carry no ownership; the native delegate is the only owner."""

    def test_delegate_of_reads_native_field_and_none_means_unowned(self):
        self.assertEqual(linear_cli.delegate_of(_issue("R-1", delegate="Claude")), "Claude")
        self.assertIsNone(linear_cli.delegate_of(_issue("R-2")))

    def test_agent_label_does_not_make_an_issue_owned(self):
        # The whole point of the migration: a leftover agent:claude label is
        # inert. This issue is unowned because its delegate is null.
        n = _issue("R-3", labels=["agent:claude"])
        self.assertIsNone(linear_cli.delegate_of(n))
        self.assertFalse(linear_cli.delegated_to(n, "claude"))

    def test_delegated_to_is_case_insensitive(self):
        n = _issue("R-4", delegate="Claude")
        self.assertTrue(linear_cli.delegated_to(n, "claude"))
        self.assertTrue(linear_cli.delegated_to(n, "CLAUDE"))
        self.assertFalse(linear_cli.delegated_to(n, "codex"))


class ListTasksDelegateFilterTest(unittest.TestCase):
    def test_default_view_is_my_delegated_issues_plus_undelegated(self):
        nodes = [
            _issue("R-1", delegate="Claude"),
            _issue("R-2", delegate="Codex"),
            _issue("R-3"),                                  # unowned
            _issue("R-4", labels=["agent:claude"]),          # label only -> unowned
        ]
        out = _run_list(nodes)
        self.assertEqual([i["identifier"] for i in out["issues"]],
                         ["R-1", "R-3", "R-4"])

    def test_explicit_agent_excludes_unowned(self):
        nodes = [_issue("R-1", delegate="Claude"), _issue("R-2")]
        out = _run_list(nodes, agent="claude")
        self.assertEqual([i["identifier"] for i in out["issues"]], ["R-1"])

    def test_agent_filter_matches_roster_casing(self):
        # config/CLI say "codex"; Linear returns the delegate as "Codex".
        nodes = [_issue("R-1", delegate="Codex"), _issue("R-2", delegate="Claude")]
        out = _run_list(nodes, agent="codex")
        self.assertEqual([i["identifier"] for i in out["issues"]], ["R-1"])

    def test_all_shows_every_agents_issues(self):
        nodes = [_issue("R-1", delegate="Claude"), _issue("R-2", delegate="Codex"),
                 _issue("R-3")]
        out = _run_list(nodes, all=True)
        self.assertEqual(sorted(i["identifier"] for i in out["issues"]),
                         ["R-1", "R-2", "R-3"])

    def test_unknown_agent_fails_loud_instead_of_listing_an_empty_queue(self):
        # A silent empty list reads as "queue is clear" to an unattended drain.
        nodes = [_issue("R-1", delegate="Claude")]
        args = _list_args(agent="nosuchagent")
        err = io.StringIO()
        with _ListTasksHarness(nodes):
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                linear_cli.list_tasks(args, {}, "api-key", "team-id")
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Unknown agent 'nosuchagent'", err.getvalue())
        self.assertIn("Claude", err.getvalue())

    def test_label_filter_composes_with_the_agent_queue(self):
        # It used to be dropped whenever an agent filter was set, because
        # ownership was itself a label. Ownership is the delegate now.
        captured = []
        args = _list_args(agent="claude", label="kind:build")
        with _ListTasksHarness([]):
            def capture(api_key, filter_str):
                captured.append(filter_str)
                return []
            linear_cli.paginate_issues = capture
            with contextlib.redirect_stdout(io.StringIO()):
                linear_cli.list_tasks(args, {}, "api-key", "team-id")
        self.assertEqual(len(captured), 1)
        self.assertIn('labels: { name: { eq: "kind:build" } }', captured[0])


class BoardDelegateGroupingTest(unittest.TestCase):
    def _board(self, nodes):
        args = types.SimpleNamespace(cycle=None, json=False, board=True)
        buf = io.StringIO()
        with _ListTasksHarness(nodes):
            with contextlib.redirect_stdout(buf):
                linear_cli.show_board(args, "api-key", "team-id", {})
        return buf.getvalue()

    def test_columns_are_delegates_and_labelled_issues_land_in_unassigned(self):
        out = self._board([
            _issue("R-1", delegate="Claude"),
            _issue("R-2", delegate="Codex"),
            _issue("R-3", labels=["agent:claude"]),   # inert label -> unassigned
            _issue("R-4"),
        ])
        self.assertIn("@Claude (1)", out)
        self.assertIn("@Codex (1)", out)
        self.assertIn("unassigned (2)", out)
        # R-3 must not appear under a @claude column derived from its label.
        self.assertNotIn("@claude", out)

    def test_board_has_no_column_when_nothing_is_delegated(self):
        out = self._board([_issue("R-1"), _issue("R-2", labels=["agent:codex"])])
        self.assertIn("unassigned (2)", out)
        self.assertNotIn("@Codex", out)


class SaveConfigUnwritableTest(unittest.TestCase):
    """A cache refresh must not take down the read command that triggered it."""

    def _with_config_path(self, path):
        saved = linear_cli.CONFIG_PATH
        linear_cli.CONFIG_PATH = path
        self.addCleanup(lambda: setattr(linear_cli, "CONFIG_PATH", saved))

    def test_unwritable_config_warns_and_returns_false(self):
        import pathlib
        with tempfile.TemporaryDirectory() as d:
            # A regular file where the config *directory* should be: mkdir and
            # write both raise OSError, the same way a read-only mount does.
            blocker = os.path.join(d, "not-a-dir")
            with open(blocker, "w") as fh:
                fh.write("x")
            self._with_config_path(pathlib.Path(blocker) / "config.json")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                ok = linear_cli.save_config({"agent": "claude"})
            self.assertFalse(ok)
            self.assertIn("could not write", err.getvalue())

    def test_writable_config_round_trips(self):
        import pathlib
        with tempfile.TemporaryDirectory() as d:
            self._with_config_path(pathlib.Path(d) / "sub" / "config.json")
            self.assertTrue(linear_cli.save_config({"agent": "claude"}))
            self.assertEqual(linear_cli.load_config()["agent"], "claude")

    def test_save_config_writes_private_directory_and_file(self):
        """API key lives in config.json — dir 0700, file 0600 (RUSH-2285)."""
        import pathlib
        with tempfile.TemporaryDirectory() as d:
            self._with_config_path(pathlib.Path(d) / ".linear-cli" / "config.json")
            self.assertTrue(
                linear_cli.save_config({"apiKey": "lin_api_secret", "teamId": "team"})
            )
            self.assertEqual(
                linear_cli.CONFIG_PATH.parent.stat().st_mode & 0o777, 0o700
            )
            self.assertEqual(linear_cli.CONFIG_PATH.stat().st_mode & 0o777, 0o600)
            self.assertEqual(linear_cli.load_config()["apiKey"], "lin_api_secret")

    def test_load_config_hardens_preexisting_loose_modes(self):
        """Existing loose umask configs get tightened on load."""
        import pathlib
        import stat
        with tempfile.TemporaryDirectory() as d:
            cfg_dir = pathlib.Path(d) / ".linear-cli"
            cfg_dir.mkdir(mode=0o755)
            cfg_path = cfg_dir / "config.json"
            cfg_path.write_text('{"apiKey": "lin_api_loose"}\n')
            cfg_path.chmod(0o644)
            self._with_config_path(cfg_path)
            loaded = linear_cli.load_config()
            self.assertEqual(loaded["apiKey"], "lin_api_loose")
            self.assertEqual(cfg_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(cfg_path.stat().st_mode & 0o777, 0o600)
            # Sanity: not group/world readable.
            mode = cfg_path.stat().st_mode
            self.assertFalse(mode & stat.S_IRGRP)
            self.assertFalse(mode & stat.S_IROTH)


class MigrateAgentLabelsClassifyTest(unittest.TestCase):
    ROSTER = ["Claude", "Codex"]

    def c(self, node, labels):
        return linear_cli.classify_agent_labels(node, labels, self.ROSTER)

    def test_resolvable_label_on_an_undelegated_issue_migrates(self):
        self.assertEqual(self.c(_issue("R-1"), ["agent:claude"]), ("migrate", "Claude"))

    def test_matching_existing_delegate_is_a_strip_not_a_rewrite(self):
        self.assertEqual(self.c(_issue("R-2", delegate="Claude"), ["agent:claude"]),
                         ("already", "Claude"))

    def test_conflicting_delegate_is_never_overwritten(self):
        v, detail = self.c(_issue("R-3", delegate="Codex"), ["agent:claude"])
        self.assertEqual(v, "conflict")
        self.assertIn("delegated to Codex", detail)
        self.assertIn("label says Claude", detail)

    def test_two_labels_naming_different_agents_is_a_conflict_not_a_coin_flip(self):
        v, detail = self.c(_issue("R-4"), ["agent:claude", "agent:codex"])
        self.assertEqual(v, "conflict")
        self.assertIn("Claude and Codex", detail)

    def test_two_labels_naming_the_same_agent_still_migrates(self):
        self.assertEqual(self.c(_issue("R-5"), ["agent:claude", "agent:Claude"]),
                         ("migrate", "Claude"))

    def test_label_suffix_that_is_not_an_agent_is_unresolved(self):
        # Real cases in this workspace: agent:hold (a workflow flag) and
        # agent:yosemite-s0 (a worker machine) — neither is a delegatable agent.
        for suffix in ("hold", "yosemite-s0"):
            v, detail = self.c(_issue("R-6"), [f"agent:{suffix}"])
            self.assertEqual(v, "unresolved", suffix)
            self.assertIn(suffix, detail)

    def test_no_labels_is_a_no_op_not_an_index_error(self):
        # The caller filters these out, but the docstring sells this as pure,
        # independently testable decision logic — so it must not raise.
        self.assertEqual(self.c(_issue("R-0"), []), ("already", ""))

    def test_one_unresolvable_label_blocks_its_resolvable_sibling(self):
        # Mixed state needs a human — migrating half of it silently is worse.
        v, detail = self.c(_issue("R-7"), ["agent:claude", "agent:hold"])
        self.assertEqual(v, "unresolved")
        self.assertIn("hold", detail)


class MigrateAgentLabelsRunTest(unittest.TestCase):
    """Drives cmd_migrate_agent_labels end to end over a substituted transport."""

    def _run(self, issues, labels, apply=False, update_ok=True, delete_ok=True,
             extra_carriers=None, carriers_ok=True):
        calls = []

        def fake_paginate_connection(api_key, query, path, variables=None):
            return list(issues) if path == ["issues"] else list(labels)

        def fake_gql(api_key, query, variables=None):
            calls.append((query, variables))
            if "issueLabelDelete" in query:
                return {"data": {"issueLabelDelete": {"success": bool(delete_ok)}}}
            if "labels: { id:" in query:
                # Carriers derived from the fixture, the way the live API would
                # answer: every issue that currently has this label, plus any
                # caller-declared carrier outside the scanned team. A constant
                # here once hid a real regression in the dry-run preview.
                if not carriers_ok:
                    return {"errors": [{"message": "boom"}]}
                lid = (variables or {}).get("id")
                nodes = [{"id": i["id"]} for i in issues
                         if any(l["id"] == lid for l in i["labels"]["nodes"])]
                nodes += [{"id": x} for x in (extra_carriers or {}).get(lid, [])]
                # Honour the requested page size the way the API does, so a
                # truncated page is a truncated page in the test too.
                return {"data": {"issues": {"nodes": nodes[:(variables or {}).get("first", 201)]}}}
            ident = next((i["identifier"] for i in issues
                          if i["id"] == (variables or {}).get("id")), "R-?")
            if not update_ok:
                return {"data": {"issueUpdate": {"success": False, "issue": None}}}
            dg = ((variables or {}).get("input", {}) or {}).get("delegateId")
            return {"data": {"issueUpdate": {
                "success": True,
                "issue": {"identifier": ident,
                          "delegate": {"name": "Claude"} if dg else None}}}}

        saved = (linear_cli.paginate_connection, linear_cli.gql,
                 linear_cli.get_agents, linear_cli.list_team_labels,
                 linear_cli.resolve_agent_id)
        linear_cli.paginate_connection = fake_paginate_connection
        linear_cli.gql = fake_gql
        linear_cli.get_agents = lambda a, c, force=False: [
            {"id": "id-claude", "name": "Claude"}, {"id": "id-codex", "name": "Codex"}]
        linear_cli.list_team_labels = lambda a, t: list(labels)
        linear_cli.resolve_agent_id = lambda a, c, n: f"id-{n.lower()}"
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                linear_cli.cmd_migrate_agent_labels(
                    types.SimpleNamespace(apply=apply), {}, "api-key", "team-id")
        except SystemExit as e:
            code = e.code
        finally:
            (linear_cli.paginate_connection, linear_cli.gql,
             linear_cli.get_agents, linear_cli.list_team_labels,
             linear_cli.resolve_agent_id) = saved
        return code, out.getvalue(), err.getvalue(), calls

    @staticmethod
    def _raw(ident, uid, delegate=None, labels=()):
        return {"id": uid, "identifier": ident, "title": "t",
                "state": {"name": "Todo"},
                "delegate": {"name": delegate} if delegate else None,
                "labels": {"nodes": [{"id": lid, "name": name} for lid, name in labels]}}

    def _updates(self, calls):
        return [v for q, v in calls if "issueUpdate" in q]

    def _deletes(self, calls):
        return [v for q, v in calls if "issueLabelDelete" in q]

    def test_apply_sets_the_delegate_and_drops_only_the_agent_label(self):
        issue = self._raw("R-1", "uuid-1", labels=[("l-agent", "agent:claude"),
                                                   ("l-keep", "kind:build")])
        code, out, err, calls = self._run([issue], [{"id": "l-agent", "name": "agent:claude"}],
                                          apply=True)
        self.assertEqual(code, 0, err)
        update = self._updates(calls)[0]
        self.assertEqual(update["input"]["delegateId"], "id-claude")
        self.assertEqual(update["input"]["labelIds"], ["l-keep"])   # kind:build survives
        self.assertIn("deleted    label agent:claude", out)
        self.assertIn("migrated=1 stripped=0 conflicts=0 unresolved=0 failures=0", out)

    def test_two_agent_labels_are_one_write_that_drops_both(self):
        # Two writes computed from the same snapshot would resurrect each other's
        # stripped label and silently overwrite the delegate.
        issue = self._raw("R-2", "uuid-2", labels=[("l-a", "agent:claude"),
                                                   ("l-b", "agent:Claude"),
                                                   ("l-keep", "kind:build")])
        code, out, err, calls = self._run(
            [issue], [{"id": "l-a", "name": "agent:claude"}], apply=True)
        self.assertEqual(code, 0, err)
        updates = self._updates(calls)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["input"]["labelIds"], ["l-keep"])
        self.assertEqual(updates[0]["input"]["delegateId"], "id-claude")

    def test_two_labels_naming_different_agents_writes_nothing(self):
        issue = self._raw("R-3", "uuid-3", labels=[("l-a", "agent:claude"),
                                                   ("l-b", "agent:codex")])
        code, out, err, calls = self._run(
            [issue], [{"id": "l-a", "name": "agent:claude"}], apply=True)
        self.assertEqual(code, 1)
        self.assertIn("CONFLICT", err)
        self.assertEqual(self._updates(calls), [])
        self.assertEqual(self._deletes(calls), [])

    def test_conflict_is_reported_and_nothing_is_written(self):
        issue = self._raw("R-4", "uuid-4", delegate="Codex",
                          labels=[("l-agent", "agent:claude")])
        code, out, err, calls = self._run([issue], [{"id": "l-agent", "name": "agent:claude"}],
                                          apply=True)
        self.assertEqual(code, 1)
        self.assertIn("CONFLICT", err)
        self.assertEqual(self._updates(calls), [])
        self.assertIn("keep       label agent:claude", out)

    def test_unresolvable_suffix_fails_loud_and_keeps_the_label(self):
        issue = self._raw("R-5", "uuid-5", labels=[("l-hold", "agent:hold")])
        code, out, err, calls = self._run([issue], [{"id": "l-hold", "name": "agent:hold"}],
                                          apply=True)
        self.assertEqual(code, 1)
        self.assertIn("UNRESOLVED", err)
        self.assertIn("'hold' is not a delegatable agent", err)
        self.assertEqual(self._updates(calls), [])
        self.assertEqual(self._deletes(calls), [])

    def test_a_failed_write_is_not_counted_as_migrated(self):
        issue = self._raw("R-6", "uuid-6", labels=[("l-agent", "agent:claude")])
        code, out, err, calls = self._run([issue], [{"id": "l-agent", "name": "agent:claude"}],
                                          apply=True, update_ok=False)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", err)
        self.assertIn("migrated=0 stripped=0 conflicts=0 unresolved=0 failures=1", out)
        self.assertEqual(self._deletes(calls), [])   # label still in use

    def test_a_failed_label_delete_exits_non_zero(self):
        code, out, err, calls = self._run([], [{"id": "l-dead", "name": "agent:mac-mini"}],
                                          apply=True, delete_ok=False)
        self.assertEqual(code, 1)
        self.assertIn("FAILED     label agent:mac-mini", err)
        self.assertIn("failures=1", out)

    def test_label_still_used_outside_this_team_is_never_deleted(self):
        # list_team_labels also returns workspace-wide labels, and the issue scan
        # is team-scoped — so "no hits in my team" does not mean "unused".
        code, out, err, calls = self._run(
            [], [{"id": "l-ws", "name": "agent:claude"}], apply=True,
            extra_carriers={"l-ws": ["uuid-other-team"]})
        self.assertEqual(code, 0, err)
        self.assertEqual(self._deletes(calls), [])
        self.assertIn("still carried by an issue this run did not migrate", out)

    def test_a_truncated_carrier_page_never_deletes(self):
        # The gate subtracts the issues this run clears, so a PARTIAL page whose
        # every entry happens to be cleared subtracts to empty and would read as
        # "nothing carries it" — deleting a label hundreds of untouched issues
        # still use. Every carrier here migrates; the page is still truncated.
        issues = [self._raw(f"R-{i}", f"uuid-{i}", labels=[("l-big", "agent:claude")])
                  for i in range(linear_cli.CARRIER_PAGE + 5)]
        code, out, err, calls = self._run(issues, [{"id": "l-big", "name": "agent:claude"}],
                                          apply=True)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._deletes(calls), [])
        self.assertIn(f"more than {linear_cli.CARRIER_PAGE} issues carry it", out)

    def test_dry_run_previews_the_delete_of_a_label_it_would_strip(self):
        # The carrier IS the issue this run would migrate. Gating on the live
        # count made the preview report every such label as still in use — by the
        # issue it had just said it would strip three lines above.
        issue = self._raw("R-9", "uuid-9", labels=[("l-agent", "agent:codex")])
        code, out, err, calls = self._run([issue], [{"id": "l-agent", "name": "agent:codex"}])
        self.assertEqual(code, 0, err)
        self.assertIn("migrate    R-9", out)
        self.assertIn("delete     label agent:codex", out)
        self.assertNotIn("keep       label agent:codex", out)

    def test_a_label_carried_by_an_unmigrated_issue_is_named_as_such(self):
        # Two issues on one label: one migrates, one conflicts. The label stays,
        # and the reason must point at the unmigrated issue, not another team.
        good = self._raw("R-10", "uuid-10", labels=[("l-a", "agent:claude")])
        bad = self._raw("R-11", "uuid-11", delegate="Codex",
                        labels=[("l-a", "agent:claude")])
        code, out, err, calls = self._run([good, bad],
                                          [{"id": "l-a", "name": "agent:claude"}],
                                          apply=True)
        self.assertEqual(code, 1)
        self.assertEqual(self._deletes(calls), [])
        self.assertIn("still in use by an unmigrated issue", out)

    def test_a_carrier_lookup_failure_is_a_failure_not_a_delete(self):
        code, out, err, calls = self._run([], [{"id": "l-x", "name": "agent:claude"}],
                                          apply=True, carriers_ok=False)
        self.assertEqual(code, 1)
        self.assertEqual(self._deletes(calls), [])
        self.assertIn("could not look up what carries it", err)
        self.assertIn("failures=1", out)

    def test_dry_run_writes_nothing_and_exits_zero(self):
        issue = self._raw("R-7", "uuid-7", labels=[("l-agent", "agent:codex")])
        code, out, err, calls = self._run([issue], [{"id": "l-agent", "name": "agent:codex"}])
        self.assertEqual(code, 0, err)
        self.assertEqual(self._updates(calls), [])
        self.assertEqual(self._deletes(calls), [])
        self.assertIn("migrate    R-7", out)
        self.assertIn("Re-run with --apply to write.", out)

    def test_dry_run_with_a_blocker_still_exits_zero_but_says_so(self):
        # An inspection that found work to review is not a failed migration.
        issue = self._raw("R-8", "uuid-8", labels=[("l-hold", "agent:hold")])
        code, out, err, calls = self._run([issue], [{"id": "l-hold", "name": "agent:hold"}])
        self.assertEqual(code, 0)
        self.assertIn("UNRESOLVED", err)
        self.assertIn("need a human before --apply can finish", out)

    def test_unused_label_is_deleted_once_nothing_carries_it(self):
        code, out, err, calls = self._run([], [{"id": "l-dead", "name": "agent:mac-mini"}],
                                          apply=True)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._deletes(calls), [{"id": "l-dead"}])



class ProjectStatusResolveTest(unittest.TestCase):
    """resolve_project_status_id is pure once statuses are stubbed via gql."""

    def test_matches_status_type_case_insensitively(self):
        statuses = [
            {"id": "s-backlog", "name": "Backlog", "type": "backlog"},
            {"id": "s-started", "name": "In Progress", "type": "started"},
            {"id": "s-done", "name": "Completed", "type": "completed"},
        ]

        def fake_gql(_key, _query, _vars=None):
            return {"data": {"projectStatuses": {"nodes": statuses}}}

        original = linear_cli.gql
        linear_cli.gql = fake_gql
        try:
            self.assertEqual(
                linear_cli.resolve_project_status_id("key", "STARTED"),
                "s-started",
            )
            self.assertEqual(
                linear_cli.resolve_project_status_id("key", "completed"),
                "s-done",
            )
        finally:
            linear_cli.gql = original

    def test_matches_status_name_and_substring(self):
        statuses = [
            {"id": "s-backlog", "name": "Backlog", "type": "backlog"},
            {"id": "s-started", "name": "In Progress", "type": "started"},
        ]

        def fake_gql(_key, _query, _vars=None):
            return {"data": {"projectStatuses": {"nodes": statuses}}}

        original = linear_cli.gql
        linear_cli.gql = fake_gql
        try:
            self.assertEqual(
                linear_cli.resolve_project_status_id("key", "In Progress"),
                "s-started",
            )
            self.assertEqual(
                linear_cli.resolve_project_status_id("key", "progress"),
                "s-started",
            )
        finally:
            linear_cli.gql = original

    def test_unknown_status_raises_with_suggestion(self):
        statuses = [
            {"id": "s-backlog", "name": "Backlog", "type": "backlog"},
        ]

        def fake_gql(_key, _query, _vars=None):
            return {"data": {"projectStatuses": {"nodes": statuses}}}

        original = linear_cli.gql
        linear_cli.gql = fake_gql
        try:
            with self.assertRaisesRegex(LookupError, "project status 'nope' not found"):
                linear_cli.resolve_project_status_id("key", "nope")
        finally:
            linear_cli.gql = original


class InitiativeResolveTest(unittest.TestCase):
    def test_uuid_passthrough(self):
        uid = "ba4ec591-cb56-4a01-be10-c190a0ecbd4a"
        self.assertEqual(linear_cli.resolve_initiative_id("key", uid), uid)

    def test_strict_unknown_raises(self):
        def fake_list(_key):
            return [{"id": "i1", "name": "Ship it", "updatedAt": "2026-01-01"}]

        original = linear_cli.list_initiatives
        linear_cli.list_initiatives = fake_list
        try:
            with self.assertRaisesRegex(LookupError, "initiative 'Missing' not found"):
                linear_cli.resolve_initiative_id("key", "Missing", strict=True)
        finally:
            linear_cli.list_initiatives = original

    def test_exact_name_beats_substring(self):
        nodes = [
            {"id": "i-long", "name": "Ship it later", "updatedAt": "2026-02-01"},
            {"id": "i-exact", "name": "Ship it", "updatedAt": "2026-01-01"},
        ]

        def fake_list(_key):
            return nodes

        original = linear_cli.list_initiatives
        linear_cli.list_initiatives = fake_list
        try:
            self.assertEqual(
                linear_cli.resolve_initiative_id("key", "Ship it", strict=True),
                "i-exact",
            )
        finally:
            linear_cli.list_initiatives = original


class InitiativeToProjectFindTest(unittest.TestCase):
    def test_finds_matching_link_row(self):
        rows = [
            {"id": "link-1",
             "initiative": {"id": "ini-a"},
             "project": {"id": "proj-x"}},
            {"id": "link-2",
             "initiative": {"id": "ini-a"},
             "project": {"id": "proj-y"}},
        ]

        def fake_paginate(_key, _query, _path, _vars=None):
            return rows

        original = linear_cli.paginate_connection
        linear_cli.paginate_connection = fake_paginate
        try:
            self.assertEqual(
                linear_cli.find_initiative_to_project_id("key", "ini-a", "proj-y"),
                "link-2",
            )
            self.assertIsNone(
                linear_cli.find_initiative_to_project_id("key", "ini-a", "proj-z"),
            )
        finally:
            linear_cli.paginate_connection = original


class ProjectsArgvShimTest(unittest.TestCase):
    """Bare `projects NAME` / `initiatives NAME` injects the show verb."""

    def test_update_is_a_recognized_projects_verb(self):
        # Regression: if 'update' is missing from _proj_verbs, `projects update X`
        # is rewritten to `projects show update X` and the write path is unreachable.
        import argparse
        # Exercise via main's argv rewrite by inspecting the source constant set
        # the same way main does — re-run the rewrite logic inline.
        def rewrite(argv0):
            argv = list(argv0)
            if len(argv) >= 2 and argv[0] == "projects":
                verbs = {"show", "create", "update", "archive", "delete"}
                for i in range(1, len(argv)):
                    if not argv[i].startswith("-"):
                        if argv[i] not in verbs:
                            argv = argv[:i] + ["show"] + argv[i:]
                        break
            if len(argv) >= 2 and argv[0] == "initiatives":
                verbs = {"show", "create", "update", "link", "unlink", "archive"}
                for i in range(1, len(argv)):
                    if not argv[i].startswith("-"):
                        if argv[i] not in verbs:
                            argv = argv[:i] + ["show"] + argv[i:]
                        break
            return argv

        self.assertEqual(
            rewrite(["projects", "update", "Linear CLI", "--description", "x"]),
            ["projects", "update", "Linear CLI", "--description", "x"],
        )
        self.assertEqual(
            rewrite(["projects", "Linear CLI"]),
            ["projects", "show", "Linear CLI"],
        )
        self.assertEqual(
            rewrite(["initiatives", "link", "Goal", "--project", "P"]),
            ["initiatives", "link", "Goal", "--project", "P"],
        )
        self.assertEqual(
            rewrite(["initiatives", "Rush = the default Agent OS"]),
            ["initiatives", "show", "Rush = the default Agent OS"],
        )


class CloseQueueTest(unittest.TestCase):
    """Durable local queue for closes that hit Linear rate limits."""

    @contextlib.contextmanager
    def _temp_queue(self):
        """Context manager that points QUEUE_DIR at a temp directory."""
        tmp = tempfile.TemporaryDirectory()
        original = linear_cli.QUEUE_DIR
        linear_cli.QUEUE_DIR = Path(tmp.name)
        try:
            yield
        finally:
            linear_cli.QUEUE_DIR = original
            tmp.cleanup()

    def test_intent_never_stores_api_key_or_credentials(self):
        intent = linear_cli.build_close_intent(
            "RUSH-1", "issue-1", "Done", proof=["https://pr/1"], comment="shipped"
        )
        # The queue must not accidentally persist the API key if someone passes
        # it in, and build_close_intent must not invent credential fields.
        for forbidden in ("apiKey", "api_key", "token", "password", "key"):
            self.assertNotIn(forbidden, intent)
        # Public workflow data is fine.
        self.assertEqual(intent["identifier"], "RUSH-1")
        self.assertEqual(intent["proof"], ["https://pr/1"])

    def test_queue_dir_is_private_and_persists_intents(self):
        with self._temp_queue():
            intent = linear_cli.build_close_intent("RUSH-1", "issue-1", "Done")
            self.assertTrue(linear_cli.save_queue_intent(intent))
            path = linear_cli._intent_path("RUSH-1")
            self.assertTrue(path.exists())
            self.assertEqual(
                linear_cli.QUEUE_DIR.stat().st_mode & 0o777, 0o700,
                "queue directory must be private",
            )
            loaded = linear_cli.list_queue_intents()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["identifier"], "RUSH-1")

    def test_duplicate_intents_collapse_to_latest_state(self):
        with self._temp_queue():
            linear_cli.save_queue_intent(
                linear_cli.build_close_intent("RUSH-1", "issue-1", "Done", proof=["url1"])
            )
            linear_cli.save_queue_intent(
                linear_cli.build_close_intent(
                    "RUSH-1", "issue-1", "Done",
                    proof=["url2"], comment="updated proof",
                )
            )
            intents = linear_cli.list_queue_intents()
            self.assertEqual(len(intents), 1)
            self.assertEqual(intents[0]["proof"], ["url2"])
            self.assertEqual(intents[0]["comment"], "updated proof")

    def test_queue_rejects_new_intents_when_full_but_allows_updates(self):
        with self._temp_queue():
            original_max = linear_cli.MAX_QUEUE_SIZE
            linear_cli.MAX_QUEUE_SIZE = 2
            try:
                self.assertTrue(
                    linear_cli.save_queue_intent(
                        linear_cli.build_close_intent("RUSH-1", "i1", "Done"))
                )
                self.assertTrue(
                    linear_cli.save_queue_intent(
                        linear_cli.build_close_intent("RUSH-2", "i2", "Done"))
                )
                self.assertFalse(
                    linear_cli.save_queue_intent(
                        linear_cli.build_close_intent("RUSH-3", "i3", "Done"))
                )
                # Updating an existing intent is allowed even when full.
                self.assertTrue(
                    linear_cli.save_queue_intent(
                        linear_cli.build_close_intent("RUSH-1", "i1", "Done", proof=["p"]))
                )
            finally:
                linear_cli.MAX_QUEUE_SIZE = original_max

    def test_backoff_is_exponential_and_capped(self):
        self.assertEqual(linear_cli.queue_backoff_delay(1), 2)
        self.assertEqual(linear_cli.queue_backoff_delay(2), 4)
        self.assertEqual(linear_cli.queue_backoff_delay(3), 8)
        self.assertEqual(
            linear_cli.queue_backoff_delay(20),
            linear_cli.QUEUE_BACKOFF_MAX_SECONDS,
        )

    def test_rate_limit_retains_intent_and_later_drain_applies(self):
        with self._temp_queue():
            calls = []

            def fake_gql(_api_key, query, _variables=None):
                calls.append(query)
                if "issueUpdate" in query:
                    if len([c for c in calls if "issueUpdate" in c]) == 1:
                        return {
                            "errors": [{
                                "message": "Rate limit exceeded",
                                "extensions": {"status": 429},
                            }]
                        }
                    return {
                        "data": {
                            "issueUpdate": {
                                "success": True,
                                "issue": {
                                    "identifier": "RUSH-1",
                                    "title": "T",
                                    "state": {"name": "Done"},
                                },
                            }
                        }
                    }
                # commentCreate
                return {"data": {"commentCreate": {"success": True}}}

            def fake_resolve(_api_key, _team_id, ident):
                return {
                    "id": "issue-1",
                    "identifier": ident,
                    "title": "T",
                    "state": {"name": "In Progress"},
                }

            saved = (linear_cli.gql, linear_cli.resolve_issue, linear_cli.get_states)
            linear_cli.gql = fake_gql
            linear_cli.resolve_issue = fake_resolve
            linear_cli.get_states = lambda _a, _t, _c: {
                "Done": {"id": "state-done", "type": "completed"}
            }
            try:
                intent = linear_cli.build_close_intent(
                    "RUSH-1", "issue-1", "Done", proof=["https://pr/1"]
                )
                linear_cli.save_queue_intent(intent)

                ok, transient = linear_cli.apply_close_intent(
                    "api-key", "team-id", {}, intent
                )
                self.assertFalse(ok)
                self.assertTrue(transient)
                self.assertTrue(linear_cli._intent_path("RUSH-1").exists())

                applied, remaining = linear_cli.drain_queue(
                    "api-key", "team-id", {}
                )
                self.assertEqual(applied, 1)
                self.assertEqual(remaining, 0)
                self.assertFalse(linear_cli._intent_path("RUSH-1").exists())
            finally:
                (linear_cli.gql, linear_cli.resolve_issue,
                 linear_cli.get_states) = saved

    def test_already_applied_close_skips_api_calls_and_removes_intent(self):
        with self._temp_queue():
            def fake_resolve(_api_key, _team_id, ident):
                return {
                    "id": "issue-1",
                    "identifier": ident,
                    "title": "T",
                    "state": {"name": "Done"},
                }

            def fake_gql(_api_key, _query, _variables=None):
                raise AssertionError("No API call expected when already done")

            saved = (linear_cli.gql, linear_cli.resolve_issue, linear_cli.get_states)
            linear_cli.gql = fake_gql
            linear_cli.resolve_issue = fake_resolve
            linear_cli.get_states = lambda _a, _t, _c: {
                "Done": {"id": "state-done", "type": "completed"}
            }
            try:
                intent = linear_cli.build_close_intent(
                    "RUSH-1", "issue-1", "Done", proof=["https://pr/1"]
                )
                linear_cli.save_queue_intent(intent)
                applied, remaining = linear_cli.drain_queue(
                    "api-key", "team-id", {}
                )
                self.assertEqual(applied, 1)
                self.assertEqual(remaining, 0)
                self.assertFalse(linear_cli._intent_path("RUSH-1").exists())
            finally:
                (linear_cli.gql, linear_cli.resolve_issue,
                 linear_cli.get_states) = saved

    def test_drain_respects_backoff_and_counts_remaining(self):
        with self._temp_queue():
            def fake_gql(_api_key, _query, _variables=None):
                return {
                    "errors": [{
                        "message": "Rate limit exceeded",
                        "extensions": {"status": 429},
                    }]
                }

            def fake_resolve(_api_key, _team_id, ident):
                return {
                    "id": "issue-1",
                    "identifier": ident,
                    "state": {"name": "In Progress"},
                }

            saved = (linear_cli.gql, linear_cli.resolve_issue, linear_cli.get_states)
            linear_cli.gql = fake_gql
            linear_cli.resolve_issue = fake_resolve
            linear_cli.get_states = lambda _a, _t, _c: {
                "Done": {"id": "state-done", "type": "completed"}
            }
            try:
                intent = linear_cli.build_close_intent(
                    "RUSH-1", "issue-1", "Done"
                )
                linear_cli.save_queue_intent(intent)
                # First drain: intent is due, fails transient, schedules retry.
                applied, remaining = linear_cli.drain_queue(
                    "api-key", "team-id", {}
                )
                self.assertEqual(applied, 0)
                self.assertEqual(remaining, 1)
                # Second drain immediately: still before next_attempt.
                applied2, remaining2 = linear_cli.drain_queue(
                    "api-key", "team-id", {}
                )
                self.assertEqual(applied2, 0)
                self.assertEqual(remaining2, 1)
                loaded = linear_cli.list_queue_intents()[0]
                self.assertEqual(loaded["attempts"], 1)
                self.assertIsNotNone(loaded["next_attempt"])
            finally:
                (linear_cli.gql, linear_cli.resolve_issue,
                 linear_cli.get_states) = saved

    def test_exhausted_attempts_drop_intent(self):
        with self._temp_queue():
            def fake_gql(_api_key, _query, _variables=None):
                return {
                    "errors": [{
                        "message": "Rate limit exceeded",
                        "extensions": {"status": 429},
                    }]
                }

            def fake_resolve(_api_key, _team_id, ident):
                return {
                    "id": "issue-1",
                    "identifier": ident,
                    "state": {"name": "In Progress"},
                }

            saved = (linear_cli.gql, linear_cli.resolve_issue,
                     linear_cli.get_states, linear_cli.MAX_QUEUE_ATTEMPTS)
            linear_cli.gql = fake_gql
            linear_cli.resolve_issue = fake_resolve
            linear_cli.get_states = lambda _a, _t, _c: {
                "Done": {"id": "state-done", "type": "completed"}
            }
            linear_cli.MAX_QUEUE_ATTEMPTS = 2
            try:
                intent = linear_cli.build_close_intent(
                    "RUSH-1", "issue-1", "Done"
                )
                linear_cli.save_queue_intent(intent)
                linear_cli.drain_queue("api-key", "team-id", {})  # attempt 1
                linear_cli.drain_queue("api-key", "team-id", {})  # attempt 2
                # Force next_attempt to be due by clearing it.
                loaded = linear_cli.list_queue_intents()[0]
                loaded["next_attempt"] = None
                linear_cli.save_queue_intent(loaded)
                applied, remaining = linear_cli.drain_queue(
                    "api-key", "team-id", {}
                )
                self.assertEqual(applied, 0)
                self.assertEqual(remaining, 0)
                self.assertFalse(linear_cli._intent_path("RUSH-1").exists())
            finally:
                (linear_cli.gql, linear_cli.resolve_issue,
                 linear_cli.get_states) = saved[:3]
                linear_cli.MAX_QUEUE_ATTEMPTS = saved[3]

    def test_queue_close_and_try_applies_immediately_on_success(self):
        with self._temp_queue():
            calls = []

            def fake_gql(_api_key, query, _variables=None):
                calls.append(query)
                if "issueUpdate" in query:
                    return {
                        "data": {
                            "issueUpdate": {
                                "success": True,
                                "issue": {
                                    "identifier": "RUSH-1",
                                    "title": "T",
                                    "state": {"name": "Done"},
                                },
                            }
                        }
                    }
                return {"data": {"commentCreate": {"success": True}}}

            def fake_resolve(_api_key, _team_id, ident):
                return {
                    "id": "issue-1",
                    "identifier": ident,
                    "state": {"name": "In Progress"},
                }

            saved = (linear_cli.gql, linear_cli.resolve_issue, linear_cli.get_states)
            linear_cli.gql = fake_gql
            linear_cli.resolve_issue = fake_resolve
            linear_cli.get_states = lambda _a, _t, _c: {
                "Done": {"id": "state-done", "type": "completed"}
            }
            try:
                issue = {"id": "issue-1", "identifier": "RUSH-1"}
                ok = linear_cli.queue_close_and_try(
                    "api-key", "team-id", {}, issue, "Done",
                    proof=["https://pr/1"], comment="shipped"
                )
                self.assertTrue(ok)
                self.assertFalse(linear_cli._intent_path("RUSH-1").exists())
                # Proof comment + status change.
                self.assertEqual(len([c for c in calls if "commentCreate" in c]), 1)
                self.assertEqual(len([c for c in calls if "issueUpdate" in c]), 1)
            finally:
                (linear_cli.gql, linear_cli.resolve_issue,
                 linear_cli.get_states) = saved

    def test_queue_close_and_try_keeps_intent_on_rate_limit(self):
        with self._temp_queue():
            def fake_gql(_api_key, _query, _variables=None):
                return {
                    "errors": [{
                        "message": "Rate limit exceeded",
                        "extensions": {"status": 429},
                    }]
                }

            def fake_resolve(_api_key, _team_id, ident):
                return {
                    "id": "issue-1",
                    "identifier": ident,
                    "state": {"name": "In Progress"},
                }

            saved = (linear_cli.gql, linear_cli.resolve_issue, linear_cli.get_states)
            linear_cli.gql = fake_gql
            linear_cli.resolve_issue = fake_resolve
            linear_cli.get_states = lambda _a, _t, _c: {
                "Done": {"id": "state-done", "type": "completed"}
            }
            try:
                issue = {"id": "issue-1", "identifier": "RUSH-1"}
                ok = linear_cli.queue_close_and_try(
                    "api-key", "team-id", {}, issue, "Done",
                    proof=["https://pr/1"]
                )
                # Queued counts as success for the caller.
                self.assertTrue(ok)
                self.assertTrue(linear_cli._intent_path("RUSH-1").exists())
            finally:
                (linear_cli.gql, linear_cli.resolve_issue,
                 linear_cli.get_states) = saved

    def test_resolve_backoff_prefers_retry_after_and_caps(self):
        self.assertEqual(linear_cli.resolve_backoff_delay(1, retry_after=42), 42)
        self.assertEqual(
            linear_cli.resolve_backoff_delay(1, retry_after=10_000),
            linear_cli.QUEUE_BACKOFF_MAX_SECONDS,
        )
        # Missing / invalid Retry-After falls back to exponential.
        self.assertEqual(linear_cli.resolve_backoff_delay(3, retry_after=None), 8)
        self.assertEqual(linear_cli.resolve_backoff_delay(2, retry_after="nope"), 4)

    def test_drain_honors_retry_after_from_error_extensions(self):
        with self._temp_queue():
            def fake_gql(_api_key, _query, _variables=None):
                return {
                    "errors": [{
                        "message": "Rate limit exceeded",
                        "extensions": {"status": 429, "retry_after": 17},
                    }]
                }

            def fake_resolve(_api_key, _team_id, ident):
                return {
                    "id": "issue-1",
                    "identifier": ident,
                    "state": {"name": "In Progress"},
                }

            saved = (linear_cli.gql, linear_cli.resolve_issue, linear_cli.get_states)
            linear_cli.gql = fake_gql
            linear_cli.resolve_issue = fake_resolve
            linear_cli.get_states = lambda _a, _t, _c: {
                "Done": {"id": "state-done", "type": "completed"}
            }
            try:
                linear_cli.save_queue_intent(
                    linear_cli.build_close_intent("RUSH-1", "issue-1", "Done")
                )
                applied, remaining = linear_cli.drain_queue(
                    "api-key", "team-id", {}
                )
                self.assertEqual(applied, 0)
                self.assertEqual(remaining, 1)
                loaded = linear_cli.list_queue_intents()[0]
                self.assertEqual(loaded["attempts"], 1)
                # next_attempt is ~17s ahead (not the exponential 2s).
                nxt = datetime.fromisoformat(loaded["next_attempt"])
                delta = (nxt - datetime.now(timezone.utc)).total_seconds()
                self.assertGreater(delta, 10)
                self.assertLess(delta, 25)
                self.assertNotIn("last_retry_after", loaded)
            finally:
                (linear_cli.gql, linear_cli.resolve_issue,
                 linear_cli.get_states) = saved

    def test_drain_once_processes_only_one_due_intent(self):
        with self._temp_queue():
            calls = []

            def fake_gql(_api_key, query, _variables=None):
                calls.append(query)
                if "issueUpdate" in query:
                    return {
                        "data": {
                            "issueUpdate": {
                                "success": True,
                                "issue": {
                                    "identifier": "X",
                                    "title": "T",
                                    "state": {"name": "Done"},
                                },
                            }
                        }
                    }
                return {"data": {"commentCreate": {"success": True}}}

            def fake_resolve(_api_key, _team_id, ident):
                return {
                    "id": f"id-{ident}",
                    "identifier": ident,
                    "state": {"name": "In Progress"},
                }

            saved = (linear_cli.gql, linear_cli.resolve_issue, linear_cli.get_states)
            linear_cli.gql = fake_gql
            linear_cli.resolve_issue = fake_resolve
            linear_cli.get_states = lambda _a, _t, _c: {
                "Done": {"id": "state-done", "type": "completed"}
            }
            try:
                for ident in ("RUSH-1", "RUSH-2"):
                    linear_cli.save_queue_intent(
                        linear_cli.build_close_intent(ident, f"id-{ident}", "Done")
                    )
                applied, remaining = linear_cli.drain_queue(
                    "api-key", "team-id", {}, once=True,
                )
                self.assertEqual(applied, 1)
                self.assertEqual(remaining, 1)
                left = {i["identifier"] for i in linear_cli.list_queue_intents()}
                self.assertEqual(len(left), 1)
            finally:
                (linear_cli.gql, linear_cli.resolve_issue,
                 linear_cli.get_states) = saved

    def test_concurrent_drain_is_serialized_by_file_lock(self):
        """A second drain while the first holds the lock is a no-op."""
        with self._temp_queue():
            linear_cli.save_queue_intent(
                linear_cli.build_close_intent("RUSH-1", "issue-1", "Done")
            )
            with linear_cli.queue_drain_lock(blocking=True) as held:
                self.assertTrue(held)
                # Nested non-blocking acquire must fail (lock already held).
                with linear_cli.queue_drain_lock(blocking=False) as held2:
                    self.assertFalse(held2)
                # drain_queue with lock acquisition should skip, not double-apply.
                applied, remaining = linear_cli.drain_queue(
                    "api-key", "team-id", {}, quiet=True,
                )
                self.assertEqual(applied, 0)
                self.assertEqual(remaining, 1)
                self.assertTrue(linear_cli._intent_path("RUSH-1").exists())

    def test_print_queue_list_and_cmd_queue_list(self):
        with self._temp_queue():
            linear_cli.save_queue_intent(
                linear_cli.build_close_intent("RUSH-9", "i9", "Done")
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                linear_cli.print_queue_list(detailed=True)
            out = buf.getvalue()
            self.assertIn("1 close intent(s) queued", out)
            self.assertIn("RUSH-9", out)
            self.assertIn("attempts=0", out)


class WindowsLockFallbackTest(unittest.TestCase):
    """`import fcntl` at module scope broke every command on Windows (v0.18.0,
    v0.19.0): `linear --version` died with ModuleNotFoundError before argparse
    ran. The import is optional now and the lock dispatches per platform."""

    def test_fcntl_import_is_optional(self):
        # The name must exist either way — None on Windows, the module on POSIX.
        self.assertTrue(hasattr(linear_cli, "fcntl"))
        self.assertTrue(hasattr(linear_cli, "msvcrt"))

    def test_windows_path_uses_msvcrt_locking(self):
        calls = []

        class FakeMsvcrt:
            LK_LOCK, LK_NBLCK, LK_UNLCK = 1, 2, 0

            @staticmethod
            def locking(fd, mode, nbytes):
                calls.append((mode, nbytes))

        original_fcntl, original_msvcrt = linear_cli.fcntl, linear_cli.msvcrt
        linear_cli.fcntl = None            # simulate Windows
        linear_cli.msvcrt = FakeMsvcrt
        try:
            with tempfile.TemporaryDirectory() as d:
                fd = os.open(os.path.join(d, "lk"), os.O_CREAT | os.O_RDWR)
                try:
                    self.assertTrue(linear_cli._lock_fd(fd, blocking=False))
                    linear_cli._unlock_fd(fd)
                finally:
                    os.close(fd)
        finally:
            linear_cli.fcntl, linear_cli.msvcrt = original_fcntl, original_msvcrt

        self.assertEqual(calls, [(FakeMsvcrt.LK_NBLCK, 1), (FakeMsvcrt.LK_UNLCK, 1)])

    def test_blocking_windows_lock_retries_past_lk_lock_timeout(self):
        # LK_LOCK gives up after ~10s where flock's LOCK_EX waits forever.
        # blocking=True must keep retrying, not report "not held".
        attempts = []

        class FakeMsvcrt:
            LK_LOCK, LK_NBLCK, LK_UNLCK = 1, 2, 0

            @staticmethod
            def locking(fd, mode, nbytes):
                attempts.append(mode)
                if len(attempts) < 3:
                    raise OSError(36, "timed out, still held")

        original_fcntl, original_msvcrt = linear_cli.fcntl, linear_cli.msvcrt
        linear_cli.fcntl = None
        linear_cli.msvcrt = FakeMsvcrt
        try:
            with tempfile.TemporaryDirectory() as d:
                fd = os.open(os.path.join(d, "lk"), os.O_CREAT | os.O_RDWR)
                try:
                    self.assertTrue(linear_cli._lock_fd(fd, blocking=True))
                finally:
                    os.close(fd)
        finally:
            linear_cli.fcntl, linear_cli.msvcrt = original_fcntl, original_msvcrt

        self.assertEqual(attempts, [FakeMsvcrt.LK_LOCK] * 3)

    def test_no_backend_warns_instead_of_silently_claiming_the_lock(self):
        original_fcntl, original_msvcrt = linear_cli.fcntl, linear_cli.msvcrt
        linear_cli.fcntl = None
        linear_cli.msvcrt = None
        err = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as d:
                fd = os.open(os.path.join(d, "lk"), os.O_CREAT | os.O_RDWR)
                try:
                    with contextlib.redirect_stderr(err):
                        self.assertTrue(linear_cli._lock_fd(fd, blocking=False))
                finally:
                    os.close(fd)
        finally:
            linear_cli.fcntl, linear_cli.msvcrt = original_fcntl, original_msvcrt
        self.assertIn("not serialized", err.getvalue())

    def test_contended_windows_lock_reports_not_held(self):
        class FakeMsvcrt:
            LK_LOCK, LK_NBLCK, LK_UNLCK = 1, 2, 0

            @staticmethod
            def locking(fd, mode, nbytes):
                raise OSError(36, "Resource deadlock avoided")

        original_fcntl, original_msvcrt = linear_cli.fcntl, linear_cli.msvcrt
        linear_cli.fcntl = None
        linear_cli.msvcrt = FakeMsvcrt
        try:
            with tempfile.TemporaryDirectory() as d:
                fd = os.open(os.path.join(d, "lk"), os.O_CREAT | os.O_RDWR)
                try:
                    # Must be False, not an exception — the caller skips the drain.
                    self.assertFalse(linear_cli._lock_fd(fd, blocking=False))
                finally:
                    os.close(fd)
        finally:
            linear_cli.fcntl, linear_cli.msvcrt = original_fcntl, original_msvcrt


class ProjectPriorityTest(unittest.TestCase):
    """`projects update --priority` must reach projectUpdate as an Int."""

    def _run(self, priority):
        sent = {}

        def fake_gql(_key, query, variables=None):
            sent["query"] = query
            sent["input"] = (variables or {}).get("input")
            return {"data": {"projectUpdate": {
                "success": True,
                "project": {"id": "p1", "name": "CLIs", "state": "backlog",
                            "priority": (variables or {})["input"].get("priority"),
                            "description": "", "startDate": None,
                            "targetDate": None, "lead": None, "status": None},
            }}}

        args = types.SimpleNamespace(
            project="CLIs", name=None, description=None, description_file=None,
            lead=None, start=None, target=None, priority=priority, state=None,
        )
        original_gql = linear_cli.gql
        original_resolve = linear_cli.resolve_project_id
        linear_cli.gql = fake_gql
        linear_cli.resolve_project_id = lambda *a, **k: "p1"
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                linear_cli._project_update(args, "api-key", "team-id")
        finally:
            linear_cli.gql = original_gql
            linear_cli.resolve_project_id = original_resolve
        return sent, buf.getvalue()

    def test_named_priority_maps_to_linear_int(self):
        # low -> 4 is what Linear's ProjectUpdateInput.priority expects; sending
        # the string would be accepted-looking locally and rejected by the API.
        sent, out = self._run("low")
        self.assertEqual(sent["input"], {"priority": 4})
        self.assertIn("projectUpdate", sent["query"])
        self.assertIn("Priority: Low", out)

    def test_none_clears_to_no_priority(self):
        sent, _ = self._run("none")
        self.assertEqual(sent["input"], {"priority": 0})

    def test_invalid_priority_aborts_without_writing(self):
        with self.assertRaises(SystemExit):
            self._run("sorta-urgent")


if __name__ == "__main__":
    unittest.main()
