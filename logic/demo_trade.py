from __future__ import annotations

import pandas as pd

RESULT_COLUMNS = [
    "Action", "Horizon", "AvgReturn", "WinRate", "MaxLoss", "MaxDrawdown", "AvgHoldDays",
]

VALID_ACTIONS = {"buy", "sell"}  # buy=買い（ロング）, sell=空売り（ショート）


def calc_demo_trade(
    similar_df: pd.DataFrame,
    price_df: pd.DataFrame,
    actions: list[str],
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """類似局面の各日付を起点に、指定した投資行動・保有日数でのデモ売買成績を集計して返す。

    Args:
        similar_df: extract_similar_periodsの出力（Date列を含む）。
        price_df: get_stock_dataの出力（Date, Closeを含む）。
        actions: シミュレートする投資行動のリスト。"buy"（買い）または"sell"（空売り）。
        horizons: 保有日数（営業日数）のリスト。未指定時は[5, 10, 20]。

    Returns:
        Action, Horizon, AvgReturn, WinRate, MaxLoss, MaxDrawdown, AvgHoldDays列を持つDataFrame。
        有効な取引が1件もない組み合わせは結果から除外される。
    """
    if horizons is None:
        horizons = [5, 10, 20]

    empty_result = pd.DataFrame(columns=RESULT_COLUMNS)

    if similar_df is None or similar_df.empty:
        return empty_result
    if price_df is None or price_df.empty:
        return empty_result
    if "Date" not in similar_df.columns or not {"Date", "Close"}.issubset(price_df.columns):
        return empty_result

    price = price_df.reset_index(drop=True).copy()
    price["Date"] = price["Date"].astype(str)

    rows = []

    for action in actions:
        if action not in VALID_ACTIONS:
            continue  # 未定義のactionは無視する（例外は投げない）

        for horizon in horizons:
            returns = []
            drawdowns = []
            hold_days = []

            for date in similar_df["Date"].astype(str):
                matches = price.index[price["Date"] == date]
                if len(matches) == 0:
                    continue
                entry_idx = matches[0]
                exit_idx = entry_idx + horizon
                if exit_idx >= len(price):
                    continue  # 保有期間分の未来データが足りない場合はスキップ

                entry_price = price.loc[entry_idx, "Close"]
                exit_price = price.loc[exit_idx, "Close"]
                window = price.loc[entry_idx:exit_idx, "Close"]

                if entry_price == 0:
                    continue

                if action == "buy":
                    ret = (exit_price - entry_price) / entry_price
                    drawdown = (window.min() - entry_price) / entry_price
                else:  # sell（空売り）
                    ret = (entry_price - exit_price) / entry_price
                    drawdown = (entry_price - window.max()) / entry_price

                returns.append(ret)
                drawdowns.append(drawdown)
                hold_days.append(horizon)

            if not returns:
                continue  # 有効な取引がない組み合わせは結果に含めない

            returns_series = pd.Series(returns)

            rows.append({
                "Action": action,
                "Horizon": horizon,
                "AvgReturn": returns_series.mean(),
                "WinRate": (returns_series > 0).mean(),
                "MaxLoss": returns_series.min(),
                "MaxDrawdown": min(drawdowns),
                "AvgHoldDays": sum(hold_days) / len(hold_days),
            })

    if not rows:
        return empty_result

    return pd.DataFrame(rows, columns=RESULT_COLUMNS)