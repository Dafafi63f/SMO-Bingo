"""Helpers de inventado de ranges (fix_bingo_group_ranges)."""
from __future__ import annotations

import unittest

from fix_bingo_group_ranges import invent_count_range, invent_count_range_for_len
from ranges_tools import lockout_high_range_variance


class InventCountRangeTests(unittest.TestCase):
    def test_tiny_pools(self) -> None:
        self.assertEqual(invent_count_range(1), [1, 1, 1, 1])
        self.assertEqual(invent_count_range(2), [1, 1, 2, 2])
        self.assertEqual(invent_count_range(3), [1, 2, 3, 3])

    def test_empty_cap(self) -> None:
        self.assertEqual(invent_count_range(0), [])

    def test_output_nondecreasing_and_within_cap(self) -> None:
        for cap in (4, 5, 7, 12, 25, 40, 80, 120):
            with self.subTest(cap=cap):
                values = invent_count_range(cap)
                self.assertEqual(len(values), 4)
                self.assertEqual(values, sorted(values))
                self.assertLessEqual(values[-1], cap)
                self.assertGreaterEqual(values[0], 1)

    def test_for_len_matches_requested_length(self) -> None:
        values = invent_count_range_for_len(20, 3)
        self.assertEqual(len(values), 3)
        self.assertEqual(values, sorted(values))


class LockoutRangeVarianceTests(unittest.TestCase):
    def test_warns_when_max_over_3x_min(self) -> None:
        self.assertTrue(lockout_high_range_variance([3, 6, 9, 12]))
        self.assertFalse(lockout_high_range_variance([4, 6, 8, 12]))
        self.assertFalse(lockout_high_range_variance([2]))


if __name__ == "__main__":
    unittest.main()
