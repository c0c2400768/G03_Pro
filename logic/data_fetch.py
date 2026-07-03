"""太刀岡担当：株価・指数データ取得と基準日100正規化（logic/data_fetch.py）。

実装規約（仕様書6章）への対応：
- 6-1: Dateは列として持ち、文字列（YYYY-MM-DD）で統一。indexには設定しない
- 6-2: 取得失敗時は例外を投げず「列だけあって行数0」の空DataFrameを返す。UI表示はしない
- 6-3: NaNはそのまま残す（dropnaしない）
- 6-4: yfinanceで統一。日経平均は ^N225
- 6-6: 取得系関数に @st.cache_data(ttl=3600) を付与
- 6-7: 型ヒント＋1行docstring
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import yfinance as yf

# 取得失敗時に返す空DataFrameの列定義（呼び出し元は df.empty でチェックする）
STOCK_COLUMNS: list[str] = ["Date", "Open", "High", "Low", "Close", "Volume"]
INDEX_COLUMNS: list[str] = ["Date", "Close"]

# UI上の日本語表記 → yfinanceのperiod文字列。既にyfinance形式ならそのまま通す
_PERIOD_MAP: dict[str, str] = {
    "6ヶ月": "6mo",
    "1年": "1y",
    "2年": "2y",
    "3年": "3y",
    "5年": "5y",
    "10年": "10y",
    "全期間": "max",
}

# 日経平均のティッカー（仕様書6-4で確定）
NIKKEI_TICKER: str = "^N225"


def _to_yf_period(period: str) -> str:
    """日本語の期間表記をyfinanceのperiod文字列に変換する（未知の値はそのまま返す）。"""
    return _PERIOD_MAP.get(period, period)


def _empty_df(columns: list[str]) -> pd.DataFrame:
    """列だけを持つ行数0のDataFrameを返す（仕様書6-2の失敗時戻り値）。"""
    return pd.DataFrame(columns=columns)


def _history_to_df(history: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """yfinanceのhistory結果をDate文字列列＋指定列のDataFrameに整形する。"""
    if history is None or history.empty:
        return _empty_df(columns)
    df = history.reset_index()
    # 日本株はタイムゾーン付きのdatetimeで返るため、文字列 YYYY-MM-DD に変換（6-1）
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    missing = [c for c in columns if c not in df.columns]
    if missing:
        return _empty_df(columns)
    return df[columns].copy()


@st.cache_data(ttl=3600)
def get_stock_data(ticker: str, period: str) -> pd.DataFrame:
    """銘柄コードと期間から株価df（Date, Open, High, Low, Close, Volume）を返す。失敗時は空df。"""
    try:
        history = yf.Ticker(ticker).history(
            period=_to_yf_period(period), auto_adjust=False
        )
        return _history_to_df(history, STOCK_COLUMNS)
    except Exception:
        # 銘柄コード不正・通信エラー等。例外は投げず空dfを返す（6-2）
        return _empty_df(STOCK_COLUMNS)


@st.cache_data(ttl=3600)
def get_index_data(period: str) -> pd.DataFrame:
    """期間を指定して日経平均（^N225）のdf（Date, Close）を返す。失敗時は空df。"""
    try:
        history = yf.Ticker(NIKKEI_TICKER).history(
            period=_to_yf_period(period), auto_adjust=False
        )
        return _history_to_df(history, INDEX_COLUMNS)
    except Exception:
        return _empty_df(INDEX_COLUMNS)


def normalize_to_100(df: pd.DataFrame, base_date: str) -> pd.DataFrame:
    """Close列を持つdfを基準日=100に正規化し、df（Date, Normalized）を返す。失敗時は空df。

    基準日が休場日等でdfに存在しない場合は、基準日以降で最初に存在する日を基準にする。
    基準日以降のデータが1件もない場合・基準値がNaN/0の場合は空dfを返す。
    """
    result_columns = ["Date", "Normalized"]
    if df is None or df.empty or "Close" not in df.columns or "Date" not in df.columns:
        return _empty_df(result_columns)

    # Dateは文字列 YYYY-MM-DD なので辞書順比較で日付比較になる（6-1）
    base_candidates = df.loc[df["Date"] >= base_date]
    if base_candidates.empty:
        return _empty_df(result_columns)

    base_close = base_candidates.iloc[0]["Close"]
    if pd.isna(base_close) or base_close == 0:
        return _empty_df(result_columns)

    out = pd.DataFrame(
        {
            "Date": df["Date"].values,
            "Normalized": (df["Close"] / base_close * 100).values,
        }
    )
    # NaNはそのまま残す（6-3）
    return out