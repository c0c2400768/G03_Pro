"""logic/comparison.py の sector_company_count に関する簡易テスト。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from logic.comparison import sector_company_count


class SectorCompanyCountTest(unittest.TestCase):
    def _fixture(self):
        # 業種A:対象銘柄含め3社、業種B:1社のみ
        sector_map = {"1000": "業種A", "1001": "業種A", "1002": "業種A", "2000": "業種B"}
        size_rank = {c: 1 for c in sector_map}
        return sector_map, size_rank

    def test_counts_all_companies_in_the_same_sector(self) -> None:
        with patch("logic.comparison._load_sector_and_size_maps", return_value=self._fixture()):
            self.assertEqual(sector_company_count("1000.T"), 3)

    def test_unknown_ticker_returns_zero(self) -> None:
        with patch("logic.comparison._load_sector_and_size_maps", return_value=self._fixture()):
            self.assertEqual(sector_company_count("9999.T"), 0)

    def test_empty_ticker_returns_zero(self) -> None:
        self.assertEqual(sector_company_count(""), 0)


if __name__ == "__main__":
    unittest.main()
