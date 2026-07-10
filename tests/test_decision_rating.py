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
    SELL_FIXED_RATING,
    SELL_FIXED_RISK_LEVEL,
    SKIP_FIXED_RATING,
    SKIP_FIXED_RISK_LEVEL,
    add_action_ratings,
    apply_hit_rate_floor,
    apply_significance_cap,
    judge_sector_validity,
    rank_rated_actions,
    rate_action_row,
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


class RateActionRowSellTest(unittest.TestCase):
    def test_sell_returns_fixed_values_without_scoring(self) -> None:
        # sellは購入価格・現在値から一意に決まる確定値であり、他の引数（avg_return等が
        # Noneでも）に関わらずスコア計算を経由せず固定のRiskLevel/Rating、Score=Noneを返す
        result = rate_action_row(
            "sell",
            avg_return=0.05, win_rate=None, max_drawdown=None, horizon=None, hv=None,
            single_stock_hit_rate=None, single_stock_avg_return=None, single_stock_p_value=None,
            single_stock_p_value_is_reference=False, single_stock_insufficient_sample=True,
            peer_avg_return=None,
        )
        self.assertEqual(result["RiskLevel"], SELL_FIXED_RISK_LEVEL)
        self.assertEqual(result["Rating"], SELL_FIXED_RATING)
        self.assertIsNone(result["Score"])

    def test_sell_fixed_values_differ_from_skip(self) -> None:
        # 「見送り」と区別できるよう、固定値は別の値にする
        self.assertNotEqual(SELL_FIXED_RISK_LEVEL, SKIP_FIXED_RISK_LEVEL)
        self.assertNotEqual(SELL_FIXED_RATING, SKIP_FIXED_RATING)


class RankRatedActionsSellPlacementTest(unittest.TestCase):
    def _rated_row(self, action: str, avg_return: float, score, rating: str, risk_level: str) -> dict:
        return {
            "Action": action, "Horizon": None, "AvgReturn": avg_return,
            "Score": score, "Rating": rating, "RiskLevel": risk_level,
        }

    def test_sell_placed_after_scored_group_and_before_skip(self) -> None:
        rated_df = pd.DataFrame([
            self._rated_row("sell", 0.05, None, SELL_FIXED_RATING, SELL_FIXED_RISK_LEVEL),
            self._rated_row("hold", 0.01, 0, RATING_CONSIDERABLE, "中"),
            self._rated_row("buy_today", 0.05, 3, RATING_RECOMMENDED, "低"),
            self._rated_row("skip", 0.0, None, SKIP_FIXED_RATING, SKIP_FIXED_RISK_LEVEL),
        ])

        ranked_df = rank_rated_actions(rated_df)

        # スコア対象群（推奨→検討可の評価順）→ sell（固定配置）→ skip（固定配置）の順になる
        self.assertEqual(list(ranked_df["Action"]), ["buy_today", "hold", "sell", "skip"])

    def test_duplicate_sell_rows_collapse_to_one_placed_before_skip(self) -> None:
        rated_df = pd.DataFrame([
            self._rated_row("sell", 0.05, None, SELL_FIXED_RATING, SELL_FIXED_RISK_LEVEL),
            self._rated_row("sell", 0.05, None, SELL_FIXED_RATING, SELL_FIXED_RISK_LEVEL),
            self._rated_row("hold", 0.01, 0, RATING_CONSIDERABLE, "中"),
        ])

        ranked_df = rank_rated_actions(rated_df)

        self.assertEqual((ranked_df["Action"] == "sell").sum(), 1)
        self.assertEqual(ranked_df.iloc[-1]["Action"], "sell")

    def test_sell_never_outranks_scored_group_regardless_of_avg_return(self) -> None:
        # sellは採点対象外のため、AvgReturnがスコア対象群より高くても順位には影響しない
        # （select_recommended_actionがscored群の先頭を返すことの前提を保証する）
        rated_df = pd.DataFrame([
            self._rated_row("sell", 0.50, None, SELL_FIXED_RATING, SELL_FIXED_RISK_LEVEL),
            self._rated_row("hold", 0.01, 0, RATING_CONSIDERABLE, "中"),
        ])

        ranked_df = rank_rated_actions(rated_df)

        self.assertEqual(ranked_df.iloc[0]["Action"], "hold")
        self.assertEqual(ranked_df.iloc[1]["Action"], "sell")


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