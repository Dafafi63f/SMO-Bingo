"""Tests de regeneración incremental."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from regenerate_lib import (
    RegenerateStep,
    build_steps,
    load_state,
    record_step_success,
    step_input_fingerprint,
    step_needs_run,
)


class RegenerateLibTests(unittest.TestCase):
    def test_stamp_combined_always_runs(self) -> None:
        """El stamp del Combined debe correr aunque el JSON no haya cambiado."""
        step = next(s for s in build_steps() if s.id == "stamp_combined")
        self.assertTrue(step.always)
        state: dict = {"version": 1, "steps": {}}
        record_step_success(step, state)
        needs, reason = step_needs_run(
            step, state=state, force=False, upstream_dirty=False
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "always")

    def test_always_flag_forces_run(self) -> None:
        step = RegenerateStep(
            "demo",
            "demo",
            ("Files/regenerate_lib.py",),
            ("Files/regenerate_all.py",),
            lambda: 0,
            always=True,
        )
        state: dict = {"version": 1, "steps": {}}
        record_step_success(step, state)
        needs, reason = step_needs_run(
            step, state=state, force=False, upstream_dirty=False
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "always")

    def test_skip_when_inputs_unchanged(self) -> None:
        step = RegenerateStep(
            "demo",
            "demo",
            ("Files/regenerate_lib.py",),
            ("Files/regenerate_all.py",),
            lambda: 0,
        )
        state: dict = {"version": 1, "steps": {}}
        record_step_success(step, state)
        needs, reason = step_needs_run(
            step, state=state, force=False, upstream_dirty=False
        )
        self.assertFalse(needs)
        self.assertEqual(reason, "up to date")

    def test_rerun_when_upstream_dirty(self) -> None:
        step = RegenerateStep(
            "demo",
            "demo",
            ("Files/regenerate_lib.py",),
            ("Files/regenerate_all.py",),
            lambda: 0,
        )
        state: dict = {"version": 1, "steps": {}}
        record_step_success(step, state)
        needs, reason = step_needs_run(
            step, state=state, force=False, upstream_dirty=True
        )
        self.assertTrue(needs)
        self.assertEqual(reason, "upstream")

    def test_output_excluded_from_input_fingerprint(self) -> None:
        step = RegenerateStep(
            "palabras",
            "palabras",
            ("Catalog/palabras_inventario.json", "Files/regenerate_lib.py"),
            ("Catalog/palabras_inventario.json",),
            lambda: 0,
        )
        fps = step_input_fingerprint(step)
        self.assertNotIn("Catalog/palabras_inventario.json", fps)
        self.assertIn("Files/regenerate_lib.py", fps)

    def test_load_state_missing_file(self) -> None:
        with patch("regenerate_lib.STATE_PATH", Path("/nonexistent/state.json")):
            data = load_state()
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["steps"], {})

    def test_load_state_bad_json(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            with patch("regenerate_lib.STATE_PATH", path):
                data = load_state()
            self.assertEqual(data["steps"], {})


if __name__ == "__main__":
    unittest.main()
