"""Helpers de range en catalog_lib."""
from __future__ import annotations

import unittest

from catalog_lib import (
    align_numeric_range_to_progression,
    ensure_unique_ascending_range,
    pad_range_three_to_four,
)


class PadRangeThreeToFourTests(unittest.TestCase):
    def test_leaves_non_three_unchanged(self) -> None:
        self.assertEqual(pad_range_three_to_four([1, 2]), [1, 2])
        self.assertEqual(pad_range_three_to_four([1, 2, 3, 4]), [1, 2, 3, 4])

    def test_default_repeats_last(self) -> None:
        self.assertEqual(pad_range_three_to_four([10, 20, 30]), [10, 20, 30, 30])

    def test_far_kingdom_repeats_middle(self) -> None:
        moons = [{"kingdom": "cascade", "moon": i} for i in range(1, 31)]
        moons[29] = {"kingdom": "moon", "moon": 1}
        self.assertEqual(
            pad_range_three_to_four([10, 20, 30], moons=moons),
            [10, 20, 20, 30],
        )


class EnsureUniqueAscendingRangeTests(unittest.TestCase):
    def test_dedupes_and_sorts(self) -> None:
        self.assertEqual(ensure_unique_ascending_range([3, 1, 2, 2, 1]), [1, 2, 3])

    def test_align_numeric_does_not_pad_to_progression(self) -> None:
        self.assertEqual(
            align_numeric_range_to_progression([5, 5, 10], ["e", "m", "l", "n"]),
            [5, 10],
        )


if __name__ == "__main__":
    unittest.main()
