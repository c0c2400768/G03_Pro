"""logic/demo_trade.py のsell（horizon非依存化）・add(hold統合)に関する簡易テスト。"""

from __future__ import annotations

import unittest

import pandas as pd

from logic.demo_trade import ACTION_LABELS, HOLDING_ACTIONS, calc_demo_trade


class SellConsolidationTest(unittest.TestCase):
    def _price_df(self, n: int = 20) -> pd.DataFrame:
        return pd.DataFrame({
            "Date": [f"2024-01-{i:02d}" for i in range(1, n + 1)],
            "Close": [100 + i for i in range(n)],
        })

    def test_sell_produces_single_row_with_none_horizon(self) -> None:
        price_df = self._price_df()
        similar_df = pd.DataFrame({"Date": ["2024-01-15", "2024-01-16", "2024-01-17"]})

        result = calc_demo_trade(similar_df, price_df, ["sell"], [5, 10, 20], buy_date="2024-01-01")

        sell_rows = result[result["Action"] == "sell"]
        self.assertEqual(len(sell_rows), 1)
        self.assertTrue(pd.isna(sell_rows.iloc[0]["Horizon"]))

    def test_sell_is_not_excluded_by_exit_index_availability(self) -> None:
        # 類似局面3件全てがhorizon分のexit側データを持たない終盤の日付でも、
        # sellはexit側を必要としないため3件ともサンプルに含まれる
        price_df = self._price_df()
        similar_df = pd.DataFrame({"Date": ["2024-01-15", "2024-01-16", "2024-01-17"]})

        result = calc_demo_trade(similar_df, price_df, ["sell"], [20], buy_date="2024-01-01")

        self.assertEqual(result.iloc[0]["SampleSize"], 3)

    def test_sell_without_entry_price_is_excluded(self) -> None:
        price_df = self._price_df()
        similar_df = pd.DataFrame({"Date": ["2024-01-15"]})

        result = calc_demo_trade(similar_df, price_df, ["sell"], [5], buy_date=None)

        self.assertTrue(result.empty)


class AddMergedIntoHoldTest(unittest.TestCase):
    def test_add_no_longer_a_recognized_action(self) -> None:
        self.assertNotIn("add", HOLDING_ACTIONS)
        self.assertNotIn("add", ACTION_LABELS)

    def test_calc_demo_trade_ignores_unknown_add_action(self) -> None:
        price_df = pd.DataFrame({
            "Date": [f"2024-01-{i:02d}" for i in range(1, 11)],
            "Close": [100 + i for i in range(10)],
        })
        similar_df = pd.DataFrame({"Date": ["2024-01-03"]})

        result = calc_demo_trade(similar_df, price_df, ["add"], [5])

        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
