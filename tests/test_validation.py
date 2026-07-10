"""logic/validation.py の検証地点数の動的算出に関する簡易テスト。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from logic.validation import (
    DEFAULT_TARGET_SAMPLE_SIZE,
    LARGE_SECTOR_TARGET_SAMPLE_SIZE,
    MAX_VALIDATION_POINTS,
    MIN_VALIDATION_POINTS,
    _determine_target_points,
    _determine_target_sample_size,
    _determine_validation_points,
    run_single_stock_validation,
)


class DetermineTargetPointsTest(unittest.TestCase):
    def test_small_data_clamps_to_minimum(self) -> None:
        # verifiable_range=119, evaluation_horizon_days=20 -> 119//20=5 -> 下限8にクランプ
        target = _determine_target_points(total_rows=200, min_lookback_days=60, evaluation_horizon_days=20)
        self.assertEqual(target, MIN_VALIDATION_POINTS)

    def test_large_data_clamps_to_maximum(self) -> None:
        # verifiable_range=919 -> 919//20=45 -> 上限25にクランプ
        target = _determine_target_points(total_rows=1000, min_lookback_days=60, evaluation_horizon_days=20)
        self.assertEqual(target, MAX_VALIDATION_POINTS)

    def test_mid_size_data_uses_computed_value(self) -> None:
        # verifiable_range=300 -> 300//20=15（上下限の範囲内なのでそのまま採用）
        target = _determine_target_points(total_rows=381, min_lookback_days=60, evaluation_horizon_days=20)
        self.assertEqual(target, 15)

    def test_insufficient_data_returns_minimum(self) -> None:
        target = _determine_target_points(total_rows=10, min_lookback_days=60, evaluation_horizon_days=20)
        self.assertEqual(target, MIN_VALIDATION_POINTS)


class DetermineValidationPointsSpacingTest(unittest.TestCase):
    def _min_interval(self, points: list[int]) -> int:
        return min(b - a for a, b in zip(points, points[1:]))

    def test_spacing_never_narrower_than_evaluation_horizon(self) -> None:
        # 下限8地点が要求されても、データ量的に間隔20営業日を保てる地点数までしか配置しない
        points = _determine_validation_points(
            total_rows=200, min_lookback_days=60, evaluation_horizon_days=20, target_points=8
        )
        self.assertLess(len(points), 8)
        self.assertGreaterEqual(self._min_interval(points), 20)

    def test_requested_points_honored_when_data_sufficient(self) -> None:
        points = _determine_validation_points(
            total_rows=381, min_lookback_days=60, evaluation_horizon_days=20, target_points=15
        )
        self.assertEqual(len(points), 15)
        self.assertGreaterEqual(self._min_interval(points), 20)

    def test_upper_bound_points_still_respect_spacing(self) -> None:
        points = _determine_validation_points(
            total_rows=1000, min_lookback_days=60, evaluation_horizon_days=20, target_points=25
        )
        self.assertEqual(len(points), 25)
        self.assertGreaterEqual(self._min_interval(points), 20)


class RunSingleStockValidationDynamicTargetTest(unittest.TestCase):
    def test_requested_points_defaults_to_minimum_when_data_insufficient(self) -> None:
        price_df = pd.DataFrame({"Date": [f"2024-01-{i:02d}" for i in range(1, 11)], "Close": range(10)})
        result = run_single_stock_validation(price_df)
        self.assertEqual(result["requested_points"], MIN_VALIDATION_POINTS)
        self.assertEqual(result["actual_points"], 0)

    def test_explicit_target_points_overrides_dynamic_calculation(self) -> None:
        price_df = pd.DataFrame({"Date": [f"2024-01-{i:02d}" for i in range(1, 11)], "Close": range(10)})
        result = run_single_stock_validation(price_df, target_points=3)
        self.assertEqual(result["requested_points"], 3)


class DetermineTargetSampleSizeTest(unittest.TestCase):
    def test_large_sector_uses_raised_target(self) -> None:
        with patch("logic.validation.sector_company_count", return_value=50):
            self.assertEqual(_determine_target_sample_size("1000.T"), LARGE_SECTOR_TARGET_SAMPLE_SIZE)

    def test_small_sector_keeps_default_target(self) -> None:
        with patch("logic.validation.sector_company_count", return_value=49):
            self.assertEqual(_determine_target_sample_size("1000.T"), DEFAULT_TARGET_SAMPLE_SIZE)


if __name__ == "__main__":
    unittest.main()