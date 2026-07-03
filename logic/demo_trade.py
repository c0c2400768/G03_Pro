"""岩間担当：デモトレード計算処理（logic/demo_trade.py）"""

from __future__ import annotations

import pandas as pd

RESULT_COLUMNS = ["Action", "Horizon", "AvgReturn", "WinRate", "MaxLoss", "MaxDrawdown", "AvgHoldDays"]

HOLDING_ACTIONS = ["hold", "sell", "partial_sell", "add", "stop_loss"]
NEW_ACTIONS = ["buy_today", "wait", "split_buy", "skip"]

ACTION_LABELS = {
    "hold": "保有継続", "sell": "売却", "partial_sell": "一部売却",
    "add": "追加購入", "stop_loss": "損切り設定",
    "buy_today": "当日購入", "wait": "待機", "split_buy": "分割購入", "skip": "見送り",
}


def _simulate(action: str, window: pd.Series, wait_days: int, stop_loss_pct: float) -> dict | None:
    """1回の取引を評価する。windowはentry日を0番目とした終値の系列。"""
    entry = window.iloc[0]
    horizon = len(window) - 1
    if horizon < 1 or entry == 0:
        return None

    if action in ("hold", "add", "buy_today"):
        exit_p = window.iloc[-1]
        return {"ret": (exit_p - entry) / entry, "dd": (window.min() - entry) / entry, "hold_days": horizon}

    if action in ("sell", "skip"):
        return {"ret": 0.0, "dd": 0.0, "hold_days": 0}

    if action == "partial_sell":
        exit_p = window.iloc[-1]
        return {"ret": 0.5 * (exit_p - entry) / entry, "dd": 0.5 * (window.min() - entry) / entry, "hold_days": horizon}

    if action == "stop_loss":
        threshold = entry * (1 - stop_loss_pct)
        for i, p in enumerate(window):
            if p <= threshold:
                return {"ret": -stop_loss_pct, "dd": -stop_loss_pct, "hold_days": i}
        exit_p = window.iloc[-1]
        return {"ret": (exit_p - entry) / entry, "dd": (window.min() - entry) / entry, "hold_days": horizon}

    if action == "wait":
        wd = min(wait_days, horizon - 1)
        if wd < 1:
            return None
        buy_p = window.iloc[wd]
        sub = window.iloc[wd:]
        return {"ret": (sub.iloc[-1] - buy_p) / buy_p, "dd": (sub.min() - buy_p) / buy_p, "hold_days": horizon - wd}

    if action == "split_buy":
        idxs = sorted(set([0, horizon // 2, horizon]))
        avg_cost = sum(window.iloc[i] for i in idxs) / len(idxs)
        exit_p = window.iloc[-1]
        return {"ret": (exit_p - avg_cost) / avg_cost, "dd": (window.min() - avg_cost) / avg_cost, "hold_days": horizon}

    return None


def calc_demo_trade(
    similar_df: pd.DataFrame,
    price_df: pd.DataFrame,
    actions: list[str],
    horizons: list[int] | None = None,
    wait_days: int = 5,
    stop_loss_pct: float = 0.05,
) -> pd.DataFrame:
    """類似局面の各日付を起点に、投資行動ごとのデモ売買成績を集計して返す。"""
    if horizons is None:
        horizons = [5, 10, 20]

    empty = pd.DataFrame(columns=RESULT_COLUMNS)
    if similar_df is None or similar_df.empty or price_df is None or price_df.empty:
        return empty
    if "Date" not in similar_df.columns or not {"Date", "Close"}.issubset(price_df.columns):
        return empty

    price = price_df.reset_index(drop=True).copy()
    price["Date"] = price["Date"].astype(str)
    rows = []

    for action in actions:
        for horizon in horizons:
            rets, dds, holds = [], [], []
            for date in similar_df["Date"].astype(str):
                matches = price.index[price["Date"] == date]
                if len(matches) == 0:
                    continue
                entry_idx = matches[0]
                exit_idx = entry_idx + horizon
                if exit_idx >= len(price):
                    continue
                window = price.loc[entry_idx:exit_idx, "Close"]
                trade = _simulate(action, window, wait_days, stop_loss_pct)
                if trade is None:
                    continue
                rets.append(trade["ret"])
                dds.append(trade["dd"])
                holds.append(trade["hold_days"])

            if not rets:
                continue
            r = pd.Series(rets)
            rows.append({
                "Action": action, "Horizon": horizon,
                "AvgReturn": r.mean(), "WinRate": (r > 0).mean(),
                "MaxLoss": r.min(), "MaxDrawdown": min(dds), "AvgHoldDays": sum(holds) / len(holds),
            })

    return pd.DataFrame(rows, columns=RESULT_COLUMNS) if rows else empty