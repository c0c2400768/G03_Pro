"""岩間担当：銘柄コード⇔銘柄名の対応（logic/ticker_lookup.py）。

data/data_j.xls（東証上場銘柄一覧）を銘柄マスタとして使い、画面表示・入力補助のための
コード⇔銘柄名の変換を提供する。logic/配下のためStreamlitには依存しない。
銘柄マスタの読み込み自体はlogic/comparison.pyのload_listed_stocks()を共有する。
"""

from __future__ import annotations

from functools import lru_cache

from logic.comparison import load_listed_stocks


@lru_cache(maxsize=1)
def _code_to_name_map() -> dict[str, str]:
    """銘柄コード→銘柄名のdictを作る（銘柄マスタが読み込めない場合は空dict）。"""
    stocks = load_listed_stocks()
    return {str(code): name for code, name in zip(stocks["コード"], stocks["銘柄名"])}


@lru_cache(maxsize=1)
def list_tickers() -> list[dict[str, str]]:
    """選択UI用に、コード・銘柄名・ティッカー(.T付き)のdictのリストを銘柄名順で返す。"""
    return sorted(
        (
            {"code": code, "name": name, "ticker": f"{code}.T"}
            for code, name in _code_to_name_map().items()
        ),
        key=lambda item: (item["name"], item["code"]),
    )


def get_company_name(ticker: str) -> str:
    """ティッカー（例: "7203.T"）から銘柄名を返す。対応が無い場合はticker自体を返す。"""
    if not ticker:
        return ticker
    code = ticker.strip().split(".")[0]
    return _code_to_name_map().get(code, ticker)
