"""logic/decision_rating.py の単体銘柄ゲート（apply_significance_cap）に関する簡易テスト。"""

from __future__ import annotations

import unittest

import pandas as pd

from logic.decision_rating import (
    RATING_CONSIDERABLE,
    RATING_NOT_RECOMMENDED,
    RATING_RECOMMENDED,
    add_action_ratings,
    apply_significance_cap,
)


class ApplySignificanceCapTest(unittest.TestCase):
    def test_non_recommended_rating_passes_through_unchanged(self) -> None:
        self.assertEqual(
            apply_significance_cap(RATING_CONSIDERABLE, 0.9, 0.1, False, 0.1), RATING_CONSIDERABLE
        )
        self.assertEqual(
            apply_significance_cap(RATING_NOT_RECOMMENDED, 0.9, 0.1, False, 0.1), RATING_NOT_RECOMMENDED
        )

    def test_insufficient_sample_downgrades_to_considerable(self) -> None:
        rating = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_hit_rate=0.9,
            single_stock_avg_return=0.05,
            single_stock_insufficient_sample=True,
            peer_avg_return=0.05,
        )
        self.assertEqual(rating, RATING_CONSIDERABLE)

    def test_hit_rate_above_half_and_matching_direction_keeps_recommended(self) -> None:
        rating = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_hit_rate=0.6,
            single_stock_avg_return=0.02,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(rating, RATING_RECOMMENDED)

        rating_both_negative = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_hit_rate=0.6,
            single_stock_avg_return=-0.02,
            single_stock_insufficient_sample=False,
            peer_avg_return=-0.01,
        )
        self.assertEqual(rating_both_negative, RATING_RECOMMENDED)

    def test_hit_rate_not_above_half_downgrades(self) -> None:
        rating = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_hit_rate=0.5,
            single_stock_avg_return=0.02,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(rating, RATING_CONSIDERABLE)

    def test_mismatched_direction_downgrades(self) -> None:
        rating = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_hit_rate=0.7,
            single_stock_avg_return=0.02,
            single_stock_insufficient_sample=False,
            peer_avg_return=-0.01,
        )
        self.assertEqual(rating, RATING_CONSIDERABLE)

    def test_missing_values_downgrade(self) -> None:
        self.assertEqual(
            apply_significance_cap(RATING_RECOMMENDED, None, 0.02, False, 0.01), RATING_CONSIDERABLE
        )
        self.assertEqual(
            apply_significance_cap(RATING_RECOMMENDED, 0.7, None, False, 0.01), RATING_CONSIDERABLE
        )
        self.assertEqual(
            apply_significance_cap(RATING_RECOMMENDED, 0.7, 0.02, False, None), RATING_CONSIDERABLE
        )


class AddActionRatingsTest(unittest.TestCase):
    def _sample_df(self) -> pd.DataFrame:
        # AvgReturn+, WinRate>=0.5, MaxDrawdown低リスク -> スコア3（推奨相当）の行を用意
        return pd.DataFrame(
            [{"Action": "buy_today", "Horizon": 20, "AvgReturn": 0.05, "WinRate": 0.6, "MaxDrawdown": -0.01}]
        )

    def test_recommended_rating_kept_when_gate_conditions_met(self) -> None:
        df = add_action_ratings(
            self._sample_df(),
            single_stock_hit_rate=0.6,
            single_stock_avg_return=0.02,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(df.iloc[0]["Rating"], RATING_RECOMMENDED)

    def test_recommended_rating_downgraded_when_gate_conditions_not_met(self) -> None:
        df = add_action_ratings(
            self._sample_df(),
            single_stock_hit_rate=0.4,
            single_stock_avg_return=0.02,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(df.iloc[0]["Rating"], RATING_CONSIDERABLE)

    def test_recommended_rating_downgraded_when_insufficient_sample(self) -> None:
        df = add_action_ratings(
            self._sample_df(),
            single_stock_hit_rate=0.9,
            single_stock_avg_return=0.05,
            single_stock_insufficient_sample=True,
            peer_avg_return=0.05,
        )
        self.assertEqual(df.iloc[0]["Rating"], RATING_CONSIDERABLE)


if __name__ == "__main__":
    unittest.main()