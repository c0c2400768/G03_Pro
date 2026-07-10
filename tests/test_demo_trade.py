"""logic/demo_trade.py のsell（確定値化）・add(hold統合)に関する簡易テスト。"""

from __future__ import annotations

import unittest

import pandas as pd

from logic.demo_trade import (
    ACTION_LABELS,
    HOLDING_ACTIONS,
    calc_demo_trade,
    calc_unrealized_return,
    latest_close_price,
)


class CalcUnrealizedReturnTest(unittest.TestCase):
    def test_computes_return_from_purchase_and_current_price(self) -> None:
        self.assertAlmostEqual(calc_unrealized_return(100.0, 110.0), 0.10)
        self.assertAlmostEqual(calc_unrealized_return(100.0, 90.0), -0.10)

    def test_none_purchase_price_returns_none(self) -> None:
        self.assertIsNone(calc_unrealized_return(None, 110.0))

    def test_none_current_price_returns_none(self) -> None:
        self.assertIsNone(calc_unrealized_return(100.0, None))

    def test_zero_purchase_price_returns_none(self) -> None:
        self.assertIsNone(calc_unrealized_return(0, 110.0))

    def test_zero_current_price_returns_none(self) -> None:
        self.assertIsNone(calc_unrealized_return(100.0, 0))

    def test_nan_values_return_none(self) -> None:
        self.assertIsNone(calc_unrealized_return(float("nan"), 110.0))
        self.assertIsNone(calc_unrealized_return(100.0, float("nan")))


class LatestClosePriceTest(unittest.TestCase):
    def test_returns_last_close(self) -> None:
        price_df = pd.DataFrame({"Close": [100.0, 101.0, 102.0]})
        self.assertEqual(latest_close_price(price_df), 102.0)

    def test_falls_back_to_last_non_nan_when_trailing_nan(self) -> None:
        price_df = pd.DataFrame({"Close": [100.0, 101.0, float("nan")]})
        self.assertEqual(latest_close_price(price_df), 101.0)

    def test_empty_df_returns_none(self) -> None:
        self.assertIsNone(latest_close_price(pd.DataFrame(columns=["Close"])))

    def test_none_df_returns_none(self) -> None:
        self.assertIsNone(latest_close_price(None))


class SellConfirmedValueTest(unittest.TestCase):
    def _price_df(self, n: int = 20) -> pd.DataFrame:
        return pd.DataFrame({
            "Date": [f"2024-01-{i:02d}" for i in range(1, n + 1)],
            "Close": [100 + i for i in range(n)],
        })

    def test_sell_produces_single_confirmed_value_row_with_none_horizon(self) -> None:
        # 購入価格（2024-01-01の終値=100）→ 現在値（price_dfの最新終値=119）の確定リターン。
        # 予測分布ではないため、WinRate/MaxLoss/MaxDrawdown/SampleSizeはNoneになる。
        price_df = self._price_df()
        similar_df = pd.DataFrame({"Date": ["2024-01-15", "2024-01-16", "2024-01-17"]})

        result = calc_demo_trade(similar_df, price_df, ["sell"], [5, 10, 20], buy_date="2024-01-01")

        sell_rows = result[result["Action"] == "sell"]
        self.assertEqual(len(sell_rows), 1)
        row = sell_rows.iloc[0]
        self.assertTrue(pd.isna(row["Horizon"]))
        self.assertAlmostEqual(row["AvgReturn"], (119 - 100) / 100)
        self.assertIsNone(row["WinRate"])
        self.assertIsNone(row["MaxLoss"])
        self.assertIsNone(row["MaxDrawdown"])
        self.assertIsNone(row["SampleSize"])

    def test_sell_result_independent_of_similar_periods_content(self) -> None:
        # sellはもはや類似局面をサンプリングしないため、similar_dfの中身（終盤の日付で
        # horizon分のexit側データが無い場合を含む）に関わらず同じ確定リターンになる
        price_df = self._price_df()
        similar_df_few = pd.DataFrame({"Date": ["2024-01-15"]})
        similar_df_late = pd.DataFrame({"Date": ["2024-01-18", "2024-01-19", "2024-01-20"]})

        result_few = calc_demo_trade(similar_df_few, price_df, ["sell"], [20], buy_date="2024-01-01")
        result_late = calc_demo_trade(similar_df_late, price_df, ["sell"], [20], buy_date="2024-01-01")

        self.assertEqual(len(result_few), 1)
        self.assertEqual(len(result_late), 1)
        self.assertAlmostEqual(result_few.iloc[0]["AvgReturn"], result_late.iloc[0]["AvgReturn"])

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
