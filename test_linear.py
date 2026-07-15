#!/usr/bin/env python3
"""Regression tests for the `linear` CLI. Dependency-free (stdlib unittest) so it
runs anywhere with `python3 test_linear.py` — this repo ships no pytest harness.

Focus: cycle_label(), the fix for numbered (nameless) Linear cycles rendering as
'None' / 'no cycle'. Linear auto-numbered cycles have name=None and only a
number, so display must fall back to `Cycle {number}` rather than collapsing a
present-but-nameless cycle to "no cycle"."""

import importlib.util
import os
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
        # The core bug: a present cycle with name=None must render as its number,
        # not "no cycle".
        self.assertEqual(linear_cli.cycle_label({"name": None, "number": 20}), "Cycle 20")

    def test_number_zero_is_not_treated_as_missing(self):
        # `or number` would drop cycle 0; the guard is `number is not None`.
        self.assertEqual(linear_cli.cycle_label({"name": None, "number": 0}), "Cycle 0")

    def test_none_node_is_no_cycle(self):
        self.assertEqual(linear_cli.cycle_label(None), "no cycle")

    def test_empty_node_is_no_cycle(self):
        self.assertEqual(linear_cli.cycle_label({}), "no cycle")

    def test_empty_name_falls_back_to_number(self):
        self.assertEqual(linear_cli.cycle_label({"name": "", "number": 7}), "Cycle 7")


if __name__ == "__main__":
    unittest.main()
