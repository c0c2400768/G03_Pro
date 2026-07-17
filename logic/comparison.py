"""岩間担当：比較対象自動選出処理。

interface.md（確定版）6-1〜6-7の実装規約に準拠。
- 例外は投げず、条件を満たさない場合は空のdictを返す（get_stock_data等と同じ方針）
- logic/配下のためStreamlit（st.error等）には依存しない

データソース：data/data_j.xls（JPXの東証上場銘柄一覧）。
「33業種区分」で同業種を判定し、「規模コード」（1=TOPIX Core30〜6=TOPIX Small2、
数値が小さいほど規模が大きい）で並べ替えて上位PEER_LIMIT社をpeersとする。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

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

# walk-forward検証（統計検証専用）のサンプル拡張で使う目標サンプル数
VALIDATION_TARGET_SAMPLE_SIZE = 20

# 規模コード（data_j.xls実データ：1, 2, 4, 6, 7）→ Core30=1位〜Small2=5位の5段階順位
# コード4種の間に欠番（3, 5）があるため、「隣接1段階」等は規模コードの数値差ではなく
# この順位の差で判定する
SIZE_CODE_TO_RANK: dict[int, int] = {1: 1, 2: 2, 4: 3, 6: 4, 7: 5}


@lru_cache(maxsize=1)
def load_listed_stocks() -> pd.DataFrame:
    """data/data_j.xlsを読み込み、個別株のみ（コード, 銘柄名, 33業種区分, 規模コード）に絞って返す。

    ETF・REIT等の指数連動商品や業種未設定の銘柄は除外する。
    読み込みに失敗した場合・想定した列が無い場合は空dfを返す（例外は投げない）。
    他モジュール（logic/ticker_lookup.py）からも銘柄マスタとして共有される。

    data/data_j.xlsについて：JPX（日本取引所グループ）公式サイトが公開している
    東証上場銘柄一覧のExcelファイル。JPXが定期的に（概ね月次で）内容を更新するため、
    本ファイルも継続的に古くなっていく（新規上場・上場廃止・業種区分変更等が反映
    されない）。更新する場合は、JPX公式サイト（東証上場銘柄一覧のページ）から
    最新版のExcelファイルをダウンロードし、本ファイル（data/data_j.xls）と
    同じ列構成のまま差し替えればよい。列名・シート構成が変わっていないか、
    差し替え後にload_listed_stocks()が空dfを返していないか確認すること。
    """
    columns = ["コード", "銘柄名", "33業種区分", "規模コード"]
    try:
        df = pd.read_excel(DATA_PATH)
    except Exception:
        logger.exception("data_j.xlsの読み込みに失敗しました（path=%s）", DATA_PATH)
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


def sector_company_count(ticker: str) -> int:
    """指定銘柄が属する33業種区分の銘柄数（データ上の全体数、対象銘柄自身を含む）を返す。

    業種横断検証（run_peer_universe_validation）の目標サンプル数を業種規模に応じて
    可変にするために使う。業種が特定できない場合は0を返す（例外は投げない）。
    """
    if not ticker:
        return 0

    code = ticker.strip().split(".")[0]
    sector_map, _ = _load_sector_and_size_maps()

    sector = sector_map.get(code)
    if sector is None:
        return 0

    return sum(1 for s in sector_map.values() if s == sector)


def select_peer_universe_for_validation(
    ticker: str, target_sample_size: int = VALIDATION_TARGET_SAMPLE_SIZE
) -> list[str]:
    """walk-forward検証のサンプル拡張専用に、同業種・近接規模区分からpeer銘柄を選出して返す。

    表示用の`select_comparison_targets`（PEER_LIMIT=4固定）とは別系統の関数。
    「手法自体に再現性があるか」を検証するために、なるべく多くの同種銘柄を集めることが目的。

    規模コードを5段階順位（Core30=1位〜Small2=5位）に変換し、まず対象銘柄と同一順位のみを
    対象にする。目標サンプル数（target_sample_size）に届かなければ隣接1段階まで、
    それでも届かなければ隣接2段階まで対象を広げる。隣接2段階まで広げても届かない場合は
    確保できた社数のまま返す（例外は投げない）。

    Args:
        ticker: 銘柄コード（例: "7203.T"）。
        target_sample_size: 目標サンプル数。

    Returns:
        peer銘柄コードのリスト（"XXXX.T"形式）。対象銘柄自身は含まない。
        業種・規模が特定できない場合は空リストを返す。
    """
    if not ticker:
        return []

    code = ticker.strip().split(".")[0]
    sector_map, size_rank = _load_sector_and_size_maps()

    sector = sector_map.get(code)
    if sector is None:
        return []

    same_sector = [c for c, s in sector_map.items() if s == sector and c != code]

    target_rank = SIZE_CODE_TO_RANK.get(size_rank.get(code))
    if target_rank is None:
        # 対象銘柄の規模区分が不明な場合は、規模による絞り込みをせず同業種全体から選ぶ
        selected = sorted(same_sector, key=lambda c: size_rank.get(c, 99))[:target_sample_size]
        return [f"{c}.T" for c in selected]

    def rank_of(c: str) -> int | None:
        return SIZE_CODE_TO_RANK.get(size_rank.get(c))

    candidates: list[str] = []
    for max_distance in (0, 1, 2):
        candidates = sorted(
            (c for c in same_sector if rank_of(c) is not None and abs(rank_of(c) - target_rank) <= max_distance),
            key=lambda c: (abs(rank_of(c) - target_rank), size_rank.get(c, 99)),
        )
        if len(candidates) >= target_sample_size or max_distance == 2:
            break

    return [f"{c}.T" for c in candidates[:target_sample_size]]
