"""岩間担当：デモトレード計算処理（logic/demo_trade.py）"""

from __future__ import annotations

import pandas as pd

RESULT_COLUMNS = [
    "Action", "Horizon", "AvgReturn", "WinRate", "MaxLoss", "MaxDrawdown",
    "AvgHoldDays", "AvgWaitDays", "SampleSize",
]

HOLDING_ACTIONS = ["hold", "sell", "partial_sell", "add", "stop_loss"]
NEW_ACTIONS = ["buy_today", "wait", "split_buy", "skip"]

ACTION_LABELS = {
    "hold": "保有継続", "sell": "売却", "partial_sell": "一部売却",
    "add": "追加購入", "stop_loss": "損切り設定",
    "buy_today": "当日購入", "wait": "待機", "split_buy": "分割購入", "skip": "見送り",
}


def _simulate(
    action: str,
    window: pd.Series,
    wait_ratio: float,
    stop_loss_pct: float,
    entry_price: float | None,
) -> dict | None:
    """1回の取引を評価する。windowはentry日を0番目とした終値の系列。

    entry_price: 「すでに保有している」立場での取得価格（sellの損益算出に使用）。
    戻り値のwait_daysは「待機」行動のみ0以外になり、他の行動は常に0。
    """
    entry = window.iloc[0]
    horizon = len(window) - 1
    if horizon < 1 or entry == 0:
        return None

    if action in ("hold", "add", "buy_today"):
        exit_p = window.iloc[-1]
        return {
            "ret": (exit_p - entry) / entry, "dd": (window.min() - entry) / entry,
            "hold_days": horizon, "wait_days": 0,
        }

    if action == "sell":
        # 「売却」は新規のwindowで評価するのではなく、取得価格(entry_price)を
        # 基準にこれまでの含み損益を確定させる行動。取得価格が分からない場合は
        # 損益を算出できないため、この局面は集計対象から除外する（Noneを返す）。
        if entry_price is None or entry_price == 0:
            return None
        now_price = window.iloc[0]
        ret = (now_price - entry_price) / entry_price
        # 売却後は以降の値動きに晒されないため、ddはretと同一値とみなす
        return {"ret": ret, "dd": ret, "hold_days": 0, "wait_days": 0}

    if action == "skip":
        # 「見送り」は新規購入を行わない行動のため、損益は常に発生しない
        return {"ret": 0.0, "dd": 0.0, "hold_days": 0, "wait_days": 0}

    if action == "partial_sell":
        exit_p = window.iloc[-1]
        return {
            "ret": 0.5 * (exit_p - entry) / entry, "dd": 0.5 * (window.min() - entry) / entry,
            "hold_days": horizon, "wait_days": 0,
        }

    if action == "stop_loss":
        threshold = entry * (1 - stop_loss_pct)
        for i, p in enumerate(window):
            if p <= threshold:
                return {"ret": -stop_loss_pct, "dd": -stop_loss_pct, "hold_days": i, "wait_days": 0}
        exit_p = window.iloc[-1]
        return {
            "ret": (exit_p - entry) / entry, "dd": (window.min() - entry) / entry,
            "hold_days": horizon, "wait_days": 0,
        }

    if action == "wait":
        # 待機日数 = horizon × wait_ratio を切り捨てで算出する
        # （四捨五入だとwait_ratioが1.0に近い場合にwd==horizonとなり得て
        #   「待機のみでhold_daysが常に0」という不安定な境界になるため、切り捨てで回避する）。
        # 0〜horizonの範囲にクランプし、wait_ratioが想定外の値でも必ず結果を返す。
        wd = max(0, min(int(horizon * wait_ratio), horizon))
        buy_p = window.iloc[wd]
        sub = window.iloc[wd:]
        return {
            "ret": (sub.iloc[-1] - buy_p) / buy_p, "dd": (sub.min() - buy_p) / buy_p,
            "hold_days": horizon - wd, "wait_days": wd,
        }

    if action == "split_buy":
        idxs = sorted(set([0, horizon // 2, horizon]))
        avg_cost = sum(window.iloc[i] for i in idxs) / len(idxs)
        exit_p = window.iloc[-1]
        return {
            "ret": (exit_p - avg_cost) / avg_cost, "dd": (window.min() - avg_cost) / avg_cost,
            "hold_days": horizon, "wait_days": 0,
        }

    return None


def resolve_entry_price(price_df: pd.DataFrame, buy_date: str | None) -> float | None:
    """buy_date（購入日）に対応する終値を取得価格として返す。

    休場日等でbuy_date当日のデータが無い場合は、直後の最初の営業日を使う
    （normalize_to_100の基準日解決と同じ方針）。該当日が無ければNoneを返す。
    price_df/pages側（例: トップ画面での取得価格プレビュー表示）からも
    呼べるよう公開関数にしている。例外は投げない（get_stock_data等と同じ方針）。
    """
    if buy_date is None or price_df is None or price_df.empty or "Date" not in price_df.columns:
        return None
    price = price_df.copy()
    price["Date"] = price["Date"].astype(str)
    candidates = price.loc[price["Date"] >= str(buy_date)]
    if candidates.empty:
        return None
    return candidates.iloc[0]["Close"]


def calc_demo_trade(
    similar_df: pd.DataFrame,
    price_df: pd.DataFrame,
    actions: list[str],
    horizons: list[int] | None = None,
    buy_date: str | None = None,
    wait_ratio: float = 0.2,
    stop_loss_pct: float = 0.05,
) -> pd.DataFrame:
    """類似局面の各日付を起点に、投資行動ごとのデモ売買成績を集計して返す。

    buy_date: 「すでに保有している」立場での取得価格算出に使う購入日。
              sellの損益はこの日の終値を基準に計算する。未指定の場合、
              sellの局面は算出できないため結果から除外される。
    wait_ratio: 「待機」行動での待機日数をhorizonに対する比率で指定する
                （待機日数 = int(horizon * wait_ratio)、切り捨て）。
    """
    if horizons is None:
        horizons = [5, 10, 20]

    empty = pd.DataFrame(columns=RESULT_COLUMNS)
    if similar_df is None or similar_df.empty or price_df is None or price_df.empty:
        return empty
    if "Date" not in similar_df.columns or not {"Date", "Close"}.issubset(price_df.columns):
        return empty

    price = price_df.reset_index(drop=True).copy()
    price["Date"] = price["Date"].astype(str)
    entry_price = resolve_entry_price(price, buy_date)
    rows = []

    for action in actions:
        for horizon in horizons:
            rets, dds, holds, waits = [], [], [], []
            for date in similar_df["Date"].astype(str):
                matches = price.index[price["Date"] == date]
                if len(matches) == 0:
                    continue
                entry_idx = matches[0]
                exit_idx = entry_idx + horizon
                if exit_idx >= len(price):
                    continue
                window = price.loc[entry_idx:exit_idx, "Close"]
                trade = _simulate(action, window, wait_ratio, stop_loss_pct, entry_price)
                if trade is None:
                    continue
                rets.append(trade["ret"])
                dds.append(trade["dd"])
                holds.append(trade["hold_days"])
                waits.append(trade["wait_days"])

            if not rets:
                continue
            r = pd.Series(rets)
            rows.append({
                "Action": action, "Horizon": horizon,
                "AvgReturn": r.mean(), "WinRate": (r > 0).mean(),
                "MaxLoss": r.min(), "MaxDrawdown": min(dds),
                "AvgHoldDays": sum(holds) / len(holds),
                "AvgWaitDays": sum(waits) / len(waits),
                "SampleSize": len(rets),
            })

    return pd.DataFrame(rows, columns=RESULT_COLUMNS) if rows else empty