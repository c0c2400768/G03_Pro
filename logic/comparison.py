"""岩間担当：比較対象自動選出処理。

interface.md（確定版）6-1〜6-7の実装規約に準拠。
- 例外は投げず、条件を満たさない場合は空のdictを返す（get_stock_data等と同じ方針）
- logic/配下のためStreamlit（st.error等）には依存しない

【注意】peers（比較対象銘柄）の選定ロジックはinterface.mdに定義がないため、
本実装は「業種コード→主要銘柄リスト」の静的対応表による仮実装。
実運用時はTOPIX業種分類データや外部APIへの差し替えを想定。
"""

from __future__ import annotations

# 仮実装：業種コード（先頭2桁の銘柄コード帯や業種名）→ 比較対象ティッカーのリスト
# 実データに差し替える前提のプレースホルダー
SECTOR_PEERS: dict[str, list[str]] = {
    "automobile": ["7203.T", "7267.T", "7201.T"],   # トヨタ・ホンダ・日産
    "electronics": ["6758.T", "6752.T", "6501.T"],   # ソニーG・パナソニック・日立
    "retail": ["9983.T", "3382.T", "8267.T"],        # ファーストリテ・セブン&アイ・イオン
    "telecom": ["9432.T", "9433.T", "9434.T"],       # NTT・KDDI・ソフトバンク
}

# 銘柄コード → 業種コードの仮マッピング（本来は外部データに置き換える想定）
TICKER_SECTOR_MAP: dict[str, str] = {
    "7203.T": "automobile",
    "7267.T": "automobile",
    "7201.T": "automobile",
    "6758.T": "electronics",
    "6752.T": "electronics",
    "6501.T": "electronics",
    "9983.T": "retail",
    "3382.T": "retail",
    "8267.T": "retail",
    "9432.T": "telecom",
    "9433.T": "telecom",
    "9434.T": "telecom",
}

MARKET_INDEX = "^N225"


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

    sector = TICKER_SECTOR_MAP.get(ticker)
    if sector is None:
        return {"market_index": MARKET_INDEX, "peers": []}

    # 自分自身は比較対象から除外
    peers = [t for t in SECTOR_PEERS.get(sector, []) if t != ticker]

    return {"market_index": MARKET_INDEX, "peers": peers}