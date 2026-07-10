"""logic/csv_export.py の sell（売却）固定値の空欄表示に関する簡易テスト。"""

from __future__ import annotations

import unittest
from datetime import datetime

import pandas as pd

from logic.csv_export import build_decision_support_export
from logic.decision_rating import SELL_FIXED_RATING, SELL_FIXED_RISK_LEVEL


def _sell_ranked_df() -> pd.DataFrame:
    return pd.DataFrame([{
        "Rank": 1, "Action": "sell", "Horizon": None, "AvgReturn": 0.03,
        "WinRate": None, "MaxLoss": None, "MaxDrawdown": None,
        "AvgHoldDays": 0.0, "SampleSize": None,
        "RiskLevel": SELL_FIXED_RISK_LEVEL, "Rating": SELL_FIXED_RATING,
    }])


class BuildDecisionSupportExportSellTest(unittest.TestCase):
    def _data_row(self) -> str:
        text = build_decision_support_export(
            _sell_ranked_df(), "7203.T", "すでに保有している", datetime(2026, 1, 1)
        )
        return text.strip().split("\n")[-1]

    def test_none_valued_metrics_render_as_dash(self) -> None:
        # Horizon（元々sell対応済み）に加え、WinRate/MaxLoss/MaxDrawdown/SampleSizeも
        # sellではNoneのため、例外を起こさず既存の「―」表記で出力される（計5箇所）
        data_row = self._data_row()
        self.assertEqual(data_row.count("―"), 5)

    def test_empty_rating_renders_as_dash(self) -> None:
        # RatingはSELL_FIXED_RATING（空文字列）のため、画面表示と同じダッシュに変換される
        data_row = self._data_row()
        self.assertTrue(data_row.endswith(SELL_FIXED_RISK_LEVEL))

    def test_no_exception_raised_for_sell_row(self) -> None:
        try:
            build_decision_support_export(_sell_ranked_df(), "7203.T", "すでに保有している")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"sell行のCSVエクスポートで例外が発生した: {exc}")


if __name__ == "__main__":
    unittest.main()
