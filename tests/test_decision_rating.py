"""logic/decision_rating.py の単体銘柄ゲート（apply_significance_cap）に関する簡易テスト。"""

from __future__ import annotations

import unittest

import pandas as pd

from logic.decision_rating import (
    RATING_CONSIDERABLE,
    RATING_NOT_RECOMMENDED,
    RATING_RECOMMENDED,
    SECTOR_VALIDITY_CAUTION,
    SECTOR_VALIDITY_CONSISTENT,
    SECTOR_VALIDITY_REFERENCE,
    SECTOR_VALIDITY_UNJUDGEABLE,
    add_action_ratings,
    apply_hit_rate_floor,
    apply_significance_cap,
    judge_sector_validity,
    rank_rated_actions,
    rating_to_mark,
    risk_level,
)


class ApplySignificanceCapTest(unittest.TestCase):
    def test_non_recommended_rating_passes_through_unchanged(self) -> None:
        self.assertEqual(
            apply_significance_cap(RATING_CONSIDERABLE, 0.1, 0.01, False, False, 0.1), RATING_CONSIDERABLE
        )
        self.assertEqual(
            apply_significance_cap(RATING_NOT_RECOMMENDED, 0.1, 0.01, False, False, 0.1), RATING_NOT_RECOMMENDED
        )

    def test_insufficient_sample_leaves_rating_unchanged(self) -> None:
        # サンプル不足の場合はp値自体が算出できないため判定ロジックには組み込まず、
        # rating（推奨）をそのまま返す（注意書きは呼び出し元のpages側で別途表示する）
        rating = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_avg_return=0.05,
            single_stock_p_value=None,
            single_stock_p_value_is_reference=False,
            single_stock_insufficient_sample=True,
            peer_avg_return=0.05,
        )
        self.assertEqual(rating, RATING_RECOMMENDED)

    def test_significant_pvalue_and_matching_direction_keeps_recommended(self) -> None:
        rating = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_avg_return=0.02,
            single_stock_p_value=0.03,
            single_stock_p_value_is_reference=False,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(rating, RATING_RECOMMENDED)

        rating_both_negative = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_avg_return=-0.02,
            single_stock_p_value=0.03,
            single_stock_p_value_is_reference=False,
            single_stock_insufficient_sample=False,
            peer_avg_return=-0.01,
        )
        self.assertEqual(rating_both_negative, RATING_RECOMMENDED)

    def test_normal_pvalue_at_or_above_005_downgrades(self) -> None:
        rating = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_avg_return=0.02,
            single_stock_p_value=0.05,
            single_stock_p_value_is_reference=False,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(rating, RATING_CONSIDERABLE)

    def test_reference_pvalue_uses_wider_010_threshold(self) -> None:
        # p_value_is_reference=Trueの場合は通常より緩い0.10未満なら推奨を維持
        rating_kept = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_avg_return=0.02,
            single_stock_p_value=0.08,
            single_stock_p_value_is_reference=True,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(rating_kept, RATING_RECOMMENDED)

        rating_downgraded = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_avg_return=0.02,
            single_stock_p_value=0.10,
            single_stock_p_value_is_reference=True,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(rating_downgraded, RATING_CONSIDERABLE)

    def test_mismatched_direction_downgrades(self) -> None:
        rating = apply_significance_cap(
            RATING_RECOMMENDED,
            single_stock_avg_return=0.02,
            single_stock_p_value=0.01,
            single_stock_p_value_is_reference=False,
            single_stock_insufficient_sample=False,
            peer_avg_return=-0.01,
        )
        self.assertEqual(rating, RATING_CONSIDERABLE)

    def test_missing_values_downgrade(self) -> None:
        self.assertEqual(
            apply_significance_cap(RATING_RECOMMENDED, None, 0.01, False, False, 0.01), RATING_CONSIDERABLE
        )
        self.assertEqual(
            apply_significance_cap(RATING_RECOMMENDED, 0.02, None, False, False, 0.01), RATING_CONSIDERABLE
        )
        self.assertEqual(
            apply_significance_cap(RATING_RECOMMENDED, 0.02, 0.01, False, False, None), RATING_CONSIDERABLE
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
            hv=None,
            single_stock_hit_rate=0.6,
            single_stock_avg_return=0.02,
            single_stock_p_value=0.03,
            single_stock_p_value_is_reference=False,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(df.iloc[0]["Rating"], RATING_RECOMMENDED)

    def test_recommended_rating_downgraded_when_gate_conditions_not_met(self) -> None:
        df = add_action_ratings(
            self._sample_df(),
            hv=None,
            single_stock_hit_rate=0.4,
            single_stock_avg_return=0.02,
            single_stock_p_value=0.2,
            single_stock_p_value_is_reference=False,
            single_stock_insufficient_sample=False,
            peer_avg_return=0.01,
        )
        self.assertEqual(df.iloc[0]["Rating"], RATING_CONSIDERABLE)

    def test_recommended_rating_unchanged_when_insufficient_sample(self) -> None:
        # サンプル不足はapply_significance_capのロジックには組み込まれない（判定は変更しない）ため、
        # apply_hit_rate_floorも検討可のみが対象で推奨は素通りし、元のスコア3（推奨）のまま残る。
        # 統計的有意性が未確認である旨は、判定ロジックとは別にpages側で注意書きとして表示する。
        df = add_action_ratings(
            self._sample_df(),
            hv=None,
            single_stock_hit_rate=0.9,
            single_stock_avg_return=0.05,
            single_stock_p_value=None,
            single_stock_p_value_is_reference=False,
            single_stock_insufficient_sample=True,
            peer_avg_return=0.05,
        )
        self.assertEqual(df.iloc[0]["Rating"], RATING_RECOMMENDED)


class RatingToMarkTest(unittest.TestCase):
    def test_each_rating_maps_to_its_mark(self) -> None:
        self.assertEqual(rating_to_mark(RATING_RECOMMENDED), "◯")
        self.assertEqual(rating_to_mark(RATING_CONSIDERABLE), "△")
        self.assertEqual(rating_to_mark(RATING_NOT_RECOMMENDED), "×")

    def test_unknown_rating_falls_back_to_cross_mark(self) -> None:
        self.assertEqual(rating_to_mark("不明"), "×")


class RiskLevelHvRelativeTest(unittest.TestCase):
    def test_falls_back_to_fixed_threshold_when_hv_missing(self) -> None:
        # 固定閾値：3%未満=低、3〜6%=中、6%超=高
        self.assertEqual(risk_level(-0.02, hv=None, horizon=20), "低")
        self.assertEqual(risk_level(-0.05, hv=None, horizon=20), "中")
        self.assertEqual(risk_level(-0.08, hv=None, horizon=20), "高")

    def test_falls_back_to_fixed_threshold_when_horizon_missing(self) -> None:
        # sell行等horizon概念が無い（None）場合も固定閾値にフォールバックする
        self.assertEqual(risk_level(-0.02, hv=30.0, horizon=None), "低")

    def test_uses_hv_relative_threshold_when_both_present(self) -> None:
        # 想定変動幅 = (30/100) × √(20/252) ≈ 0.0845、低閾値≈0.0507、高閾値≈0.1014
        self.assertEqual(risk_level(-0.03, hv=30.0, horizon=20), "低")
        self.assertEqual(risk_level(-0.07, hv=30.0, horizon=20), "中")
        self.assertEqual(risk_level(-0.15, hv=30.0, horizon=20), "高")


class ApplyHitRateFloorTest(unittest.TestCase):
    def test_non_considerable_rating_passes_through_unchanged(self) -> None:
        self.assertEqual(apply_hit_rate_floor(RATING_RECOMMENDED, 0.1, False), RATING_RECOMMENDED)
        self.assertEqual(apply_hit_rate_floor(RATING_NOT_RECOMMENDED, 0.9, False), RATING_NOT_RECOMMENDED)

    def test_gray_zone_hit_rate_keeps_considerable(self) -> None:
        # 40%〜50%はグレーゾーンとして格下げしない
        self.assertEqual(apply_hit_rate_floor(RATING_CONSIDERABLE, 0.45, False), RATING_CONSIDERABLE)

    def test_hit_rate_below_threshold_downgrades_to_not_recommended(self) -> None:
        self.assertEqual(apply_hit_rate_floor(RATING_CONSIDERABLE, 0.39, False), RATING_NOT_RECOMMENDED)

    def test_insufficient_sample_downgrades_to_not_recommended(self) -> None:
        self.assertEqual(apply_hit_rate_floor(RATING_CONSIDERABLE, 0.9, True), RATING_NOT_RECOMMENDED)


class RankRatedActionsSellDedupTest(unittest.TestCase):
    def test_duplicate_sell_rows_collapse_to_one_within_normal_ranking(self) -> None:
        rated_df = pd.DataFrame([
            {"Action": "sell", "Horizon": None, "AvgReturn": 0.05, "Score": 3, "Rating": RATING_RECOMMENDED},
            {"Action": "sell", "Horizon": None, "AvgReturn": 0.05, "Score": 3, "Rating": RATING_RECOMMENDED},
            {"Action": "hold", "Horizon": 20, "AvgReturn": 0.01, "Score": 0, "Rating": RATING_CONSIDERABLE},
        ])

        ranked_df = rank_rated_actions(rated_df)

        self.assertEqual((ranked_df["Action"] == "sell").sum(), 1)
        # skipと違い固定最下位ではなく、通常の評価順ソートに含まれる（推奨のsellが1位）
        self.assertEqual(ranked_df.iloc[0]["Action"], "sell")


class JudgeSectorValidityTest(unittest.TestCase):
    def test_small_sample_is_unjudgeable(self) -> None:
        self.assertEqual(judge_sector_validity(0.01, 0.02, 0.01, 4), SECTOR_VALIDITY_UNJUDGEABLE)

    def test_mismatched_direction_is_caution(self) -> None:
        self.assertEqual(judge_sector_validity(0.01, 0.02, -0.01, 10), SECTOR_VALIDITY_CAUTION)

    def test_significant_pvalue_with_matching_direction_is_consistent(self) -> None:
        self.assertEqual(judge_sector_validity(0.03, 0.02, 0.01, 10), SECTOR_VALIDITY_CONSISTENT)

    def test_non_significant_pvalue_with_matching_direction_is_reference(self) -> None:
        self.assertEqual(judge_sector_validity(0.2, 0.02, 0.01, 10), SECTOR_VALIDITY_REFERENCE)

    def test_missing_pvalue_with_matching_direction_is_reference(self) -> None:
        self.assertEqual(judge_sector_validity(None, 0.02, 0.01, 10), SECTOR_VALIDITY_REFERENCE)


if __name__ == "__main__":
    unittest.main()