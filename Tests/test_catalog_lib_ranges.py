"""Helpers de range en catalog_lib."""
from __future__ import annotations

import unittest

from catalog_lib import (
    align_numeric_range_to_progression,
    ensure_unique_ascending_range,
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
