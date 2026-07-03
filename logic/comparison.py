"""岩間担当：比較対象自動選出処理。

interface.md（確定版）6-1〜6-7の実装規約に準拠。
- 例外は投げず、条件を満たさない場合は空のdictを返す（get_stock_data等と同じ方針）
- logic/配下のためStreamlit（st.error等）には依存しない

データソース：data/data_j.xls（JPXの東証上場銘柄一覧）。
「33業種区分」で同業種を判定し、「規模コード」（1=TOPIX Core30〜6=TOPIX Small2、
数値が小さいほど規模が大きい）で並べ替えて上位PEER_LIMIT社をpeersとする。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "data_j.xls"

MARKET_INDEX = "^N225"

# 個別株のみを比較対象とする市場区分（ETF・REIT等の指数連動商品は除外）
_STOCK_MARKET_SEGMENTS = {
    "プライム（内国株式）",
    "スタンダード（内国株式）",
    "グロース（内国株式）",
    "PRO Market",
}

# 同業他社として提示する最大社数（仕様：3〜4社程度）
PEER_LIMIT = 4


@lru_cache(maxsize=1)
def load_listed_stocks() -> pd.DataFrame:
    """data/data_j.xlsを読み込み、個別株のみ（コード, 銘柄名, 33業種区分, 規模コード）に絞って返す。

    ETF・REIT等の指数連動商品や業種未設定の銘柄は除外する。
    読み込みに失敗した場合・想定した列が無い場合は空dfを返す（例外は投げない）。
    他モジュール（logic/ticker_lookup.py）からも銘柄マスタとして共有される。
    """
    columns = ["コード", "銘柄名", "33業種区分", "規模コード"]
    try:
        df = pd.read_excel(DATA_PATH)
    except Exception:
        return pd.DataFrame(columns=columns)

    required = {"コード", "銘柄名", "市場・商品区分", "33業種区分", "規模コード"}
    if not required.issubset(df.columns):
        return pd.DataFrame(columns=columns)

    df = df[df["市場・商品区分"].isin(_STOCK_MARKET_SEGMENTS) & (df["33業種区分"] != "-")]
    return df[columns].copy()


@lru_cache(maxsize=1)
def _load_sector_and_size_maps() -> tuple[dict[str, str], dict[str, int]]:
    """銘柄コード→業種名 と 銘柄コード→規模順位 のdictを作る（例外は投げない）。"""
    stocks = load_listed_stocks()

    sector_map: dict[str, str] = {}
    size_rank: dict[str, int] = {}
    for code, sector, size_code in zip(stocks["コード"], stocks["33業種区分"], stocks["規模コード"]):
        code = str(code)
        sector_map[code] = sector
        try:
            size_rank[code] = int(size_code)
        except (TypeError, ValueError):
            size_rank[code] = 99  # 規模区分が不明な銘柄は並べ替えで末尾に回す

    return sector_map, size_rank


def select_comparison_targets(ticker: str) -> dict[str, str | list[str]]:
    """指定銘柄の業種から比較対象（日経平均・同業他社）を自動選出して返す。

    Args:
        ticker: 銘柄コード（例: "7203.T"）。

    Returns:
        {"market_index": str, "peers": list[str]} 形式のdict。
        業種が特定できない場合、peersは空リストを返す（例外は投げない）。
    """
    if not ticker:
        return {"market_index": MARKET_INDEX, "peers": []}

    code = ticker.strip().split(".")[0]
    sector_map, size_rank = _load_sector_and_size_maps()

    sector = sector_map.get(code)
    if sector is None:
        return {"market_index": MARKET_INDEX, "peers": []}

    peer_codes = sorted(
        (c for c, s in sector_map.items() if s == sector and c != code),
        key=lambda c: size_rank.get(c, 99),
    )[:PEER_LIMIT]

    return {"market_index": MARKET_INDEX, "peers": [f"{c}.T" for c in peer_codes]}
