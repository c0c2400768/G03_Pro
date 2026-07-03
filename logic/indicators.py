"""及川担当：テクニカル指標計算（logic/indicators.py）。

interface.md（確定版）6-1〜6-7の実装規約に準拠。
- Dateは列として保持し、文字列（YYYY-MM-DD）で扱う
- NaNはdropnaせずそのまま返す（除去は呼び出し側の責任）
- logic/配下のためStreamlitには依存しない

【注意】RSI・BB等の具体的な計算パラメータ（平滑化方法・標準偏差の扱い等）は
interface.mdに数式までの規定がないため、一般的な標準計算式で暫定実装した。
及川さんの意図と異なる場合は差し替えが必要。
"""

from __future__ import annotations

import pandas as pd


def calc_rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """終値の変動から単純移動平均ベースのRSIを計算して返す。"""
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame(columns=["Date", "RSI"])

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss != 0, 100)  # 損失ゼロの場合はRSI=100とする

    result = pd.DataFrame({"Date": df["Date"].astype(str), "RSI": rsi})
    return result


def calc_bollinger(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """終値のn日移動平均±2標準偏差でボリンジャーバンドを計算して返す。"""
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame(columns=["Date", "Upper", "Middle", "Lower"])

    middle = df["Close"].rolling(window=window).mean()
    std = df["Close"].rolling(window=window).std()

    result = pd.DataFrame({
        "Date": df["Date"].astype(str),
        "Upper": middle + 2 * std,
        "Middle": middle,
        "Lower": middle - 2 * std,
    })
    return result


def calc_bb_position(price_df: pd.DataFrame, bb_df: pd.DataFrame) -> pd.DataFrame:
    """終値がボリンジャーバンドの上限/中央/下限のどこに位置するかを判定して返す。"""
    if price_df is None or price_df.empty or bb_df is None or bb_df.empty:
        return pd.DataFrame(columns=["Date", "BBPosition"])

    merged = price_df[["Date", "Close"]].merge(bb_df, on="Date", how="left")

    def judge(row: pd.Series) -> str | float:
        if pd.isna(row["Upper"]) or pd.isna(row["Lower"]):
            return float("nan")
        if row["Close"] >= row["Upper"]:
            return "upper"
        if row["Close"] <= row["Lower"]:
            return "lower"
        return "mid"

    result = pd.DataFrame({
        "Date": merged["Date"].astype(str),
        "BBPosition": merged.apply(judge, axis=1),
    })
    return result


def calc_hv(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """終値の対数リターンから年率換算のヒストリカルボラティリティ(%)を計算して返す。"""
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame(columns=["Date", "HV"])

    log_return = (df["Close"] / df["Close"].shift(1)).apply(
        lambda x: pd.NA if pd.isna(x) or x <= 0 else x
    )
    import numpy as np

    log_return = np.log(df["Close"] / df["Close"].shift(1))
    hv = log_return.rolling(window=window).std() * (252 ** 0.5) * 100

    result = pd.DataFrame({"Date": df["Date"].astype(str), "HV": hv})
    return result


def calc_volume_ratio(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """当日出来高がn日平均出来高の何倍かを計算して返す。"""
    if df is None or df.empty or "Volume" not in df.columns:
        return pd.DataFrame(columns=["Date", "VolumeRatio"])

    avg_volume = df["Volume"].rolling(window=window).mean()
    ratio = df["Volume"] / avg_volume

    result = pd.DataFrame({"Date": df["Date"].astype(str), "VolumeRatio": ratio})
    return result


def calc_deviation(stock_df: pd.DataFrame, index_df: pd.DataFrame) -> pd.DataFrame:
    """正規化済みの株価と指数の乖離率(%)を計算して返す。"""
    required = {"Date", "Normalized"}
    if stock_df is None or index_df is None:
        return pd.DataFrame(columns=["Date", "Deviation"])
    if not required.issubset(stock_df.columns) or not required.issubset(index_df.columns):
        return pd.DataFrame(columns=["Date", "Deviation"])

    merged = stock_df.merge(
        index_df, on="Date", suffixes=("_stock", "_index"), how="left"
    )
    deviation = merged["Normalized_stock"] - merged["Normalized_index"]

    result = pd.DataFrame({"Date": merged["Date"].astype(str), "Deviation": deviation})
    return result