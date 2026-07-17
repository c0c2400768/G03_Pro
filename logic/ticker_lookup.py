"""岩間担当：銘柄コード⇔銘柄名の対応（logic/ticker_lookup.py）。

data/data_j.xls（東証上場銘柄一覧）を銘柄マスタとして使い、画面表示・入力補助のための
コード⇔銘柄名の変換を提供する。logic/配下のためStreamlitには依存しない。
銘柄マスタの読み込み自体はlogic/comparison.pyのload_listed_stocks()を共有する。
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

from logic.comparison import load_listed_stocks


def normalize_search_text(text: str) -> str:
    """検索用にNFKC正規化＋小文字化した文字列を返す（全角半角・大文字小文字の違いを吸収する）。"""
    return unicodedata.normalize("NFKC", text).lower()


@lru_cache(maxsize=1)
def _code_to_name_map() -> dict[str, str]:
    """銘柄コード→銘柄名のdictを作る（銘柄マスタが読み込めない場合は空dict）。"""
    stocks = load_listed_stocks()
    return {str(code): name for code, name in zip(stocks["コード"], stocks["銘柄名"])}


@lru_cache(maxsize=1)
def list_tickers() -> list[dict[str, str]]:
    """選択UI用に、コード・銘柄名・ティッカー(.T付き)・検索用正規化文字列のdictを銘柄名順で返す。"""
    return sorted(
        (
            {
                "code": code,
                "name": name,
                "ticker": f"{code}.T",
                "search_key": normalize_search_text(f"{name} {code}"),
            }
            for code, name in _code_to_name_map().items()
        ),
        key=lambda item: (item["name"], item["code"]),
    )


def search_tickers(keyword: str) -> list[dict[str, str]]:
    """検索キーワード（全角半角・大文字小文字を問わない部分一致）で銘柄を絞り込んで返す。

    keywordが空文字列の場合はlist_tickers()の全件をそのまま返す。
    """
    if not keyword or not keyword.strip():
        return list_tickers()
    normalized_keyword = normalize_search_text(keyword.strip())
    return [t for t in list_tickers() if normalized_keyword in t["search_key"]]


def get_company_name(ticker: str) -> str:
    """ティッカー（例: "7203.T"）から銘柄名を返す。対応が無い場合はticker自体を返す。"""
    if not ticker:
        return ticker
    code = ticker.strip().split(".")[0]
    return _code_to_name_map().get(code, ticker)
