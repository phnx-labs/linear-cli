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


class MigrateAgentLabelsClassifyTest(unittest.TestCase):
    ROSTER = ["Claude", "Codex"]

    def test_resolvable_label_on_an_undelegated_issue_migrates(self):
        v, detail = linear_cli.classify_agent_label_issue(
            _issue("R-1"), "agent:claude", self.ROSTER)
        self.assertEqual(v, "migrate")
        self.assertEqual(detail, "Claude")

    def test_matching_existing_delegate_is_a_strip_not_a_rewrite(self):
        v, detail = linear_cli.classify_agent_label_issue(
            _issue("R-2", delegate="Claude"), "agent:claude", self.ROSTER)
        self.assertEqual(v, "already")
        self.assertEqual(detail, "Claude")

    def test_conflicting_delegate_is_never_overwritten(self):
        v, detail = linear_cli.classify_agent_label_issue(
            _issue("R-3", delegate="Codex"), "agent:claude", self.ROSTER)
        self.assertEqual(v, "conflict")
        self.assertIn("delegated to Codex", detail)
        self.assertIn("label says Claude", detail)

    def test_label_suffix_that_is_not_an_agent_is_unresolved(self):
        # Real cases in this workspace: agent:hold (a workflow flag) and
        # agent:yosemite-s0 (a worker machine) — neither is a delegatable agent.
        for suffix in ("hold", "yosemite-s0"):
            v, detail = linear_cli.classify_agent_label_issue(
                _issue("R-4"), f"agent:{suffix}", self.ROSTER)
            self.assertEqual(v, "unresolved", suffix)
            self.assertIn(suffix, detail)


class MigrateAgentLabelsRunTest(unittest.TestCase):
    """Drives cmd_migrate_agent_labels end to end over a substituted transport."""

    def _run(self, issues, labels, apply=False):
        calls = []

        def fake_paginate_connection(api_key, query, path, variables=None):
            if path == ["issues"]:
                return list(issues)
            return list(labels)

        def fake_gql(api_key, query, variables=None):
            calls.append((query, variables))
            if "issueLabelDelete" in query:
                return {"data": {"issueLabelDelete": {"success": True}}}
            ident = next((i["identifier"] for i in issues
                          if i["id"] == (variables or {}).get("id")), "R-?")
            dg = ((variables or {}).get("input", {}) or {}).get("delegateId")
            return {"data": {"issueUpdate": {
                "success": True,
                "issue": {"identifier": ident,
                          "delegate": {"name": "Claude"} if dg else None,
                          "labels": {"nodes": []}}}}}

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

    def test_apply_sets_the_delegate_and_drops_only_the_agent_label(self):
        issue = {"id": "uuid-1", "identifier": "R-1", "title": "t",
                 "state": {"name": "Todo"}, "delegate": None,
                 "labels": {"nodes": [{"id": "l-agent", "name": "agent:claude"},
                                      {"id": "l-keep", "name": "kind:build"}]}}
        code, out, err, calls = self._run([issue], [{"id": "l-agent", "name": "agent:claude"}],
                                          apply=True)
        self.assertEqual(code, 0, err)
        update = next(v for q, v in calls if "issueUpdate" in q)
        self.assertEqual(update["input"]["delegateId"], "id-claude")
        self.assertEqual(update["input"]["labelIds"], ["l-keep"])   # kind:build survives
        self.assertIn("deleted", out)

    def test_conflict_is_reported_and_nothing_is_written(self):
        issue = {"id": "uuid-2", "identifier": "R-2", "title": "t",
                 "state": {"name": "Todo"}, "delegate": {"name": "Codex"},
                 "labels": {"nodes": [{"id": "l-agent", "name": "agent:claude"}]}}
        code, out, err, calls = self._run([issue], [{"id": "l-agent", "name": "agent:claude"}],
                                          apply=True)
        self.assertEqual(code, 1)
        self.assertIn("CONFLICT", err)
        self.assertFalse([q for q, _ in calls if "issueUpdate" in q])
        # The label is still in use, so it must survive.
        self.assertNotIn("deleted", out)
        self.assertIn("keep      label agent:claude", out)

    def test_unresolvable_suffix_fails_loud_and_keeps_the_label(self):
        issue = {"id": "uuid-3", "identifier": "R-3", "title": "t",
                 "state": {"name": "Todo"}, "delegate": None,
                 "labels": {"nodes": [{"id": "l-hold", "name": "agent:hold"}]}}
        code, out, err, calls = self._run([issue], [{"id": "l-hold", "name": "agent:hold"}],
                                          apply=True)
        self.assertEqual(code, 1)
        self.assertIn("UNRESOLVED", err)
        self.assertIn("'hold' is not a delegatable agent", err)
        self.assertFalse([q for q, _ in calls if "issueUpdate" in q])
        self.assertFalse([q for q, _ in calls if "issueLabelDelete" in q])

    def test_dry_run_writes_nothing(self):
        issue = {"id": "uuid-4", "identifier": "R-4", "title": "t",
                 "state": {"name": "Todo"}, "delegate": None,
                 "labels": {"nodes": [{"id": "l-agent", "name": "agent:codex"}]}}
        code, out, err, calls = self._run([issue], [{"id": "l-agent", "name": "agent:codex"}])
        self.assertEqual(code, 0, err)
        self.assertEqual(calls, [])
        self.assertIn("migrate   R-4", out)
        self.assertIn("Dry run only", out)

    def test_unused_label_is_deleted_once_nothing_carries_it(self):
        code, out, err, calls = self._run([], [{"id": "l-dead", "name": "agent:mac-mini"}],
                                          apply=True)
        self.assertEqual(code, 0, err)
        self.assertEqual([v for q, v in calls if "issueLabelDelete" in q],
                         [{"id": "l-dead"}])


if __name__ == "__main__":
    unittest.main()
