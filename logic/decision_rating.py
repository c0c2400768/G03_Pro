"""岩間担当：投資行動の推奨/検討可/非推奨判定ロジック（logic/decision_rating.py）。

既存の集計処理（logic/demo_trade.pyのcalc_demo_trade）は変更せず、その出力
（Action, Horizon, AvgReturn, WinRate, MaxDrawdown等）を元に判定を行う処理を
この関数群に分離する。interface.md 6-2の方針に従い、logic/配下のため
Streamlitには依存せず、例外は投げず不正な入力には空のdfを返す。
"""

from __future__ import annotations

import pandas as pd

# リスク（最大ドローダウンの絶対値）の閾値。3%未満=低、3%以上6%以下=中、6%超=高
RISK_LOW_THRESHOLD = 0.03
RISK_HIGH_THRESHOLD = 0.06

# 業種横断検証（新規実装2）のp値がこの値以上の場合、統計的有意性が確認できていない
# とみなし、判定ロジックの最終段階で「推奨」を「検討可」に抑える安全装置の閾値
PEER_PVALUE_SIGNIFICANCE_THRESHOLD = 0.05

RATING_RECOMMENDED = "推奨"
RATING_CONSIDERABLE = "検討可"
RATING_NOT_RECOMMENDED = "非推奨"

# 採点対象外（「見送り」）に固定で表示する判定・リスク表記
SKIP_ACTION = "skip"
SKIP_FIXED_RATING = RATING_NOT_RECOMMENDED
SKIP_FIXED_RISK_LEVEL = "なし"

# 比較表の並び替えで使う評価の優先順位（数値が大きいほど上位）
RATING_RANK = {RATING_RECOMMENDED: 2, RATING_CONSIDERABLE: 1, RATING_NOT_RECOMMENDED: 0}

RATING_COLUMNS = ["RiskLevel", "Score", "Rating"]


def _return_score(avg_return: float) -> int:
    """平均リターン：プラスなら+1点、マイナス（0を含む）なら-1点。"""
    return 1 if avg_return > 0 else -1


def _win_rate_score(win_rate: float) -> int:
    """勝率：50%以上なら+1点、50%未満なら-1点。"""
    return 1 if win_rate >= 0.5 else -1


def risk_level(max_drawdown: float) -> str:
    """最大ドローダウンの絶対値からリスク区分（低/中/高）を判定する。"""
    risk = abs(max_drawdown)
    if risk < RISK_LOW_THRESHOLD:
        return "低"
    if risk <= RISK_HIGH_THRESHOLD:
        return "中"
    return "高"


def _risk_score(max_drawdown: float) -> int:
    return {"低": 1, "中": 0, "高": -1}[risk_level(max_drawdown)]


def compute_score(avg_return: float, win_rate: float, max_drawdown: float) -> int:
    """平均リターン・勝率・リスクの3項目を採点し、合計スコア（-3〜+3）を返す。"""
    return _return_score(avg_return) + _win_rate_score(win_rate) + _risk_score(max_drawdown)


def score_to_rating(score: int) -> str:
    """スコアから推奨/検討可/非推奨を判定する（2点以上=推奨、0〜1点=検討可、-1点以下=非推奨）。"""
    if score >= 2:
        return RATING_RECOMMENDED
    if score >= 0:
        return RATING_CONSIDERABLE
    return RATING_NOT_RECOMMENDED


def apply_peer_significance_cap(rating: str, peer_p_value: float | None) -> str:
    """業種横断検証のp値が有意水準未満でない場合、「推奨」を「検討可」に抑える安全装置。

    統計的有意性が確認できていない状態で「推奨」を表示すると、初心者ユーザーが
    誤って信頼してしまうリスクがあるため、判定ロジックの最終段階で必ず適用する。
    """
    if rating != RATING_RECOMMENDED:
        return rating
    if peer_p_value is None or peer_p_value >= PEER_PVALUE_SIGNIFICANCE_THRESHOLD:
        return RATING_CONSIDERABLE
    return rating


def rate_action_row(
    action: str, avg_return: float, win_rate: float, max_drawdown: float, peer_p_value: float | None
) -> dict:
    """1つの(Action, Horizon)行に対する判定結果（RiskLevel, Score, Rating）を返す。

    action=="skip"（見送り）は採点対象外のため、固定の判定を返す
    （安全装置のキャップも適用しない＝常に非推奨のまま）。
    """
    if action == SKIP_ACTION:
        return {"RiskLevel": SKIP_FIXED_RISK_LEVEL, "Score": None, "Rating": SKIP_FIXED_RATING}

    score = compute_score(avg_return, win_rate, max_drawdown)
    rating = apply_peer_significance_cap(score_to_rating(score), peer_p_value)
    return {"RiskLevel": risk_level(max_drawdown), "Score": score, "Rating": rating}


def add_action_ratings(result_df: pd.DataFrame, peer_p_value: float | None) -> pd.DataFrame:
    """デモトレード結果df（calc_demo_tradeの出力）にRiskLevel, Score, Rating列を追加して返す。

    既存のresult_dfの行・列構成は変更せず、末尾に判定結果の列を追加するのみ。
    不正な入力の場合は空のdf（RATING_COLUMNSのみ）を返す（例外は投げない）。
    """
    required = {"Action", "AvgReturn", "WinRate", "MaxDrawdown"}
    if result_df is None or result_df.empty or not required.issubset(result_df.columns):
        return pd.DataFrame(columns=RATING_COLUMNS)

    df = result_df.reset_index(drop=True).copy()
    ratings = [
        rate_action_row(row["Action"], row["AvgReturn"], row["WinRate"], row["MaxDrawdown"], peer_p_value)
        for _, row in df.iterrows()
    ]
    df["RiskLevel"] = [r["RiskLevel"] for r in ratings]
    df["Score"] = [r["Score"] for r in ratings]
    df["Rating"] = [r["Rating"] for r in ratings]
    return df


def rank_rated_actions(rated_df: pd.DataFrame) -> pd.DataFrame:
    """比較表示用に順位付けしたdfを返す。

    「見送り」以外は 評価（推奨→検討可→非推奨）→スコア→平均リターン の順で並べ、
    「見送り」は採点対象外のため常に最後の1行にまとめて固定表示する
    （Horizon違いで複製された行は同一結果になるため代表1行のみ残す）。
    Rank列（1始まり）を付加して返す。
    """
    if rated_df is None or rated_df.empty:
        return rated_df

    non_skip = rated_df[rated_df["Action"] != SKIP_ACTION].copy()
    skip_rows = rated_df[rated_df["Action"] == SKIP_ACTION]

    non_skip["_rating_rank"] = non_skip["Rating"].map(RATING_RANK)
    non_skip = non_skip.sort_values(
        by=["_rating_rank", "Score", "AvgReturn"], ascending=[False, False, False]
    ).drop(columns="_rating_rank")

    parts = [non_skip]
    if not skip_rows.empty:
        parts.append(skip_rows.iloc[[0]])

    ordered = pd.concat(parts, ignore_index=True)
    ordered.insert(0, "Rank", range(1, len(ordered) + 1))
    return ordered


def select_recommended_action(ranked_df: pd.DataFrame) -> pd.Series | None:
    """比較表の先頭に出す「おすすめ行動」を1行選ぶ（見送りは対象外）。該当なしはNone。"""
    if ranked_df is None or ranked_df.empty:
        return None
    candidates = ranked_df[ranked_df["Action"] != SKIP_ACTION]
    if candidates.empty:
        return None
    return candidates.iloc[0]