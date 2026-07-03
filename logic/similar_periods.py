from __future__ import annotations

import pandas as pd

# 仕様書「類似局面の許容幅（デフォルト・スライダー初期値）」に対応
DEFAULT_TOLERANCE: dict[str, float] = {
    "RSI": 5,
    "HV": 3,
    "VolumeRatio": 0.3,
}

REQUIRED_COLUMNS = ["Date", "RSI", "HV", "BBPosition", "VolumeRatio"]


def extract_similar_periods(
    current: dict[str, float | str],
    history: pd.DataFrame,
    tolerance: dict[str, float] | None = None,
) -> pd.DataFrame:
    """現在の指標値と過去の指標dfを比較し、許容幅内に収まる類似局面の行を抽出して返す。

    Args:
        current: 現在の指標値。キーは "RSI", "HV", "BBPosition", "VolumeRatio"。
        history: 過去の指標値df。Date, RSI, HV, BBPosition, VolumeRatio列を持つ想定。
        tolerance: 各指標の許容幅。未指定時はDEFAULT_TOLERANCEを使用。
                   RSI・HV・VolumeRatioは数値、BBPositionは常に完全一致で判定。

    Returns:
        Date, RSI, HV, BBPosition, VolumeRatio列を持つDataFrame。
        条件を満たす行がない、または入力が不正な場合は空のDataFrame（列のみ）を返す。
    """
    if tolerance is None:
        tolerance = DEFAULT_TOLERANCE

    empty_result = pd.DataFrame(columns=REQUIRED_COLUMNS)

    # 異常系：必須列が揃っていない、またはhistoryが空 → 例外は投げず空dfを返す（規約6-2）
    if history is None or history.empty:
        return empty_result
    if not set(REQUIRED_COLUMNS).issubset(history.columns):
        return empty_result
    if not {"RSI", "HV", "BBPosition", "VolumeRatio"}.issubset(current.keys()):
        return empty_result

    # NaNの除去はこの関数の責任で行う（規約6-3）
    df = history.dropna(subset=["RSI", "HV", "BBPosition", "VolumeRatio"]).copy()

    if df.empty:
        return empty_result

    rsi_ok = (df["RSI"] - current["RSI"]).abs() <= tolerance["RSI"]
    hv_ok = (df["HV"] - current["HV"]).abs() <= tolerance["HV"]
    bb_ok = df["BBPosition"] == current["BBPosition"]
    volume_ok = (df["VolumeRatio"] - current["VolumeRatio"]).abs() <= tolerance["VolumeRatio"]

    mask = rsi_ok & hv_ok & bb_ok & volume_ok

    result = df.loc[mask, REQUIRED_COLUMNS].reset_index(drop=True)

    # Dateは文字列で統一（規約6-1）。datetime型で紛れ込んでいた場合の保険
    result["Date"] = result["Date"].astype(str)

    return result