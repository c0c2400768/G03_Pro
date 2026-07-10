"""岩間担当：投資行動の推奨/検討可/非推奨判定ロジック（logic/decision_rating.py）。

既存の集計処理（logic/demo_trade.pyのcalc_demo_trade）は変更せず、その出力
（Action, Horizon, AvgReturn, WinRate, MaxDrawdown等）を元に判定を行う処理を
この関数群に分離する。interface.md 6-2の方針に従い、logic/配下のため
Streamlitには依存せず、例外は投げず不正な入力には空のdfを返す。
"""

from __future__ import annotations

import pandas as pd

# リスク（最大ドローダウンの絶対値）の閾値。3%未満=低、3%以上6%以下=中、6%超=高。
# スイングトレード想定での一般的な下振れ許容目安として設定した固定値であり、
# 本来は_hv_relative_thresholdsによる銘柄自身のHV基準の相対閾値を優先する。
# HVが算出不可（None/NaN）の場合のみ使うフォールバック専用の閾値。
RISK_LOW_THRESHOLD = 0.03
RISK_HIGH_THRESHOLD = 0.06

RATING_RECOMMENDED = "推奨"
RATING_CONSIDERABLE = "検討可"
RATING_NOT_RECOMMENDED = "非推奨"

# 採点対象外（「見送り」）に固定で表示する判定・リスク表記
SKIP_ACTION = "skip"
SKIP_FIXED_RATING = RATING_NOT_RECOMMENDED
SKIP_FIXED_RISK_LEVEL = "なし"

# 「売却」はhorizon（経過日数）概念が無い行動（logic/demo_trade.py参照）。
# rank_rated_actionsでのdedup判定にのみ使う（skipと違い採点対象からは除外しない）
SELL_ACTION = "sell"

# 比較表の並び替えで使う評価の優先順位（数値が大きいほど上位）
RATING_RANK = {RATING_RECOMMENDED: 2, RATING_CONSIDERABLE: 1, RATING_NOT_RECOMMENDED: 0}

RATING_COLUMNS = ["RiskLevel", "Score", "Rating"]


def _return_score(avg_return: float) -> int:
    """平均リターン：プラスなら+1点、マイナス（0を含む）なら-1点。"""
    return 1 if avg_return > 0 else -1


def _win_rate_score(win_rate: float) -> int:
    """勝率：50%以上なら+1点、50%未満なら-1点。"""
    return 1 if win_rate >= 0.5 else -1


# HV（年率ボラティリティ%）基準の相対リスク閾値の係数。
# 想定変動幅 = (HV/100) × √(horizon/252) に対し、この倍率を掛けて低/高の閾値にする。
# RISK_LOW/HIGH_THRESHOLDのような絶対的な固定値ではなく、銘柄自身の想定変動幅（HVベース）
# との相対比較であり、値動きが大きい（小さい）銘柄ほど閾値も連動して大きく（小さく）なる。
RISK_HV_LOW_MULTIPLIER = 0.6
RISK_HV_HIGH_MULTIPLIER = 1.2


def _hv_relative_thresholds(hv: float | None, horizon: float | None) -> tuple[float, float]:
    """HVとhorizonから相対リスク閾値(低,高)を算出する。算出不可の場合は固定閾値を返す。"""
    if hv is None or pd.isna(hv) or horizon is None or pd.isna(horizon) or horizon <= 0:
        return RISK_LOW_THRESHOLD, RISK_HIGH_THRESHOLD
    expected_move = (hv / 100) * ((horizon / 252) ** 0.5)
    return expected_move * RISK_HV_LOW_MULTIPLIER, expected_move * RISK_HV_HIGH_MULTIPLIER


def risk_level(max_drawdown: float, hv: float | None = None, horizon: float | None = None) -> str:
    """最大ドローダウンの絶対値からリスク区分（低/中/高）を判定する。

    hv（対象銘柄の年率ヒストリカルボラティリティ%）とhorizon（経過日数）を両方渡すと、
    銘柄自身の値動きの大きさを基準にした相対閾値（想定変動幅×0.6/×1.2）で判定する。
    HVが算出不可（None/NaN）、またはhorizonが無い行動（sell等）の場合は、
    従来通りの固定閾値（RISK_LOW_THRESHOLD/RISK_HIGH_THRESHOLD）にフォールバックする。
    """
    risk = abs(max_drawdown)
    low, high = _hv_relative_thresholds(hv, horizon)
    if risk < low:
        return "低"
    if risk <= high:
        return "中"
    return "高"


def _risk_score(max_drawdown: float, hv: float | None = None, horizon: float | None = None) -> int:
    return {"低": 1, "中": 0, "高": -1}[risk_level(max_drawdown, hv, horizon)]


def compute_score(
    avg_return: float, win_rate: float, max_drawdown: float, hv: float | None = None, horizon: float | None = None
) -> int:
    """平均リターン・勝率・リスクの3項目を採点し、合計スコア（-3〜+3）を返す。

    3項目は均等配点（各±1点）としている。項目間の重み付けを最適化するには検証用データが
    必要だが、それは判定ロジック自体の妥当性検証（walk-forward検証, logic/validation.py）に
    使うデータと同一になってしまい、過学習・リーク（同じデータで重みを決めて同じデータで
    有効性を確認する）のリスクがあるため、現段階ではあえて均等配点を採用している。
    """
    return _return_score(avg_return) + _win_rate_score(win_rate) + _risk_score(max_drawdown, hv, horizon)


def score_to_rating(score: int) -> str:
    """スコアから推奨/検討可/非推奨を判定する（2点以上=推奨、0〜1点=検討可、-1点以下=非推奨）。"""
    if score >= 2:
        return RATING_RECOMMENDED
    if score >= 0:
        return RATING_CONSIDERABLE
    return RATING_NOT_RECOMMENDED


_RATING_MARKS = {RATING_RECOMMENDED: "◯", RATING_CONSIDERABLE: "△", RATING_NOT_RECOMMENDED: "×"}


def rating_to_mark(rating: str) -> str:
    """推奨/検討可/非推奨を◯/△/×の記号に変換する（未知の値は非推奨相当の×を返す）。

    「追加購入」はholdと計算式が同一のため独立した行動として持たず、holdの最終判定
    （apply_significance_cap適用後のRating）を流用表示する際に使う
    （pages/_decision_support_view.py, logic/csv_export.py参照）。
    """
    return _RATING_MARKS.get(rating, "×")


def _same_sign(a: float, b: float) -> bool:
    """2つの値が両方プラス、または両方マイナスの場合にTrue（0はどちらとも一致しない）。"""
    return (a > 0 and b > 0) or (a < 0 and b < 0)


# 単体銘柄p値（通常時）の有意水準。この値以上なら「推奨」を「検討可」に抑える
SIGNIFICANCE_PVALUE_THRESHOLD = 0.05
# 単体銘柄p値が参考値（目標サンプル数未達）の場合の有意水準（通常時より緩める）
SIGNIFICANCE_PVALUE_REFERENCE_THRESHOLD = 0.10


def apply_significance_cap(
    rating: str,
    single_stock_avg_return: float | None,
    single_stock_p_value: float | None,
    single_stock_p_value_is_reference: bool,
    single_stock_insufficient_sample: bool,
    peer_avg_return: float | None,
) -> str:
    """単体銘柄の統計的有意性・方向一致が確認できない場合、「推奨」を「検討可」に抑える安全装置。

    単体銘柄とpeer平均の値動きの方向（符号）が一致しない場合や、単体銘柄のp値が
    有意水準を下回らない場合に「推奨」を表示すると、初心者ユーザーが誤って信頼してしまう
    リスクがあるため、判定ロジックの最終段階で必ず適用する。

    single_stock_insufficient_sample（サンプル不足）の場合はp値自体が算出できていないため、
    この安全装置には組み込まない（rating不変で返す）。統計的有意性が未確認である旨は、
    判定ロジックを変えずに呼び出し元（pages/7_decision_support.py等）で注意書きとして
    別途表示すること。
    """
    if rating != RATING_RECOMMENDED:
        return rating
    if single_stock_insufficient_sample:
        return rating

    direction_ok = (
        single_stock_avg_return is not None
        and peer_avg_return is not None
        and _same_sign(single_stock_avg_return, peer_avg_return)
    )
    if not direction_ok:
        return RATING_CONSIDERABLE

    threshold = SIGNIFICANCE_PVALUE_REFERENCE_THRESHOLD if single_stock_p_value_is_reference else SIGNIFICANCE_PVALUE_THRESHOLD
    p_value_ok = single_stock_p_value is not None and single_stock_p_value < threshold
    if not p_value_ok:
        return RATING_CONSIDERABLE

    return rating


# 「検討可」を「非推奨」にさらに格下げする的中率の閾値（40%未満）。
# 40%〜50%（apply_significance_capの推奨キャップ閾値との間）はグレーゾーンとして
# 「検討可」を維持し、格下げしない
HIT_RATE_DOWNGRADE_THRESHOLD = 0.4


def apply_hit_rate_floor(
    rating: str,
    single_stock_hit_rate: float | None,
    single_stock_insufficient_sample: bool,
) -> str:
    """単体銘柄検証の的中率が低すぎる場合、「検討可」を「非推奨」にさらに抑える安全装置。

    apply_significance_capの「推奨→検討可」キャップとは逆方向（下方向）のキャップ。
    サンプル不足、または的中率が40%未満（50%を大きく下回り、外れる可能性の方が高い）の
    場合に格下げする。「推奨」「非推奨」はこの関数の対象外（rating!=検討可ならそのまま返す）。
    """
    if rating != RATING_CONSIDERABLE:
        return rating
    if single_stock_insufficient_sample:
        return RATING_NOT_RECOMMENDED
    if single_stock_hit_rate is not None and single_stock_hit_rate < HIT_RATE_DOWNGRADE_THRESHOLD:
        return RATING_NOT_RECOMMENDED
    return rating


def rate_action_row(
    action: str,
    avg_return: float,
    win_rate: float,
    max_drawdown: float,
    horizon: float | None,
    hv: float | None,
    single_stock_hit_rate: float | None,
    single_stock_avg_return: float | None,
    single_stock_p_value: float | None,
    single_stock_p_value_is_reference: bool,
    single_stock_insufficient_sample: bool,
    peer_avg_return: float | None,
) -> dict:
    """1つの(Action, Horizon)行に対する判定結果（RiskLevel, Score, Rating）を返す。

    action=="skip"（見送り）は採点対象外のため、固定の判定を返す
    （安全装置のキャップも適用しない＝常に非推奨のまま）。
    """
    if action == SKIP_ACTION:
        return {"RiskLevel": SKIP_FIXED_RISK_LEVEL, "Score": None, "Rating": SKIP_FIXED_RATING}

    score = compute_score(avg_return, win_rate, max_drawdown, hv, horizon)
    rating = apply_significance_cap(
        score_to_rating(score),
        single_stock_avg_return,
        single_stock_p_value,
        single_stock_p_value_is_reference,
        single_stock_insufficient_sample,
        peer_avg_return,
    )
    rating = apply_hit_rate_floor(rating, single_stock_hit_rate, single_stock_insufficient_sample)
    return {"RiskLevel": risk_level(max_drawdown, hv, horizon), "Score": score, "Rating": rating}


def add_action_ratings(
    result_df: pd.DataFrame,
    hv: float | None,
    single_stock_hit_rate: float | None,
    single_stock_avg_return: float | None,
    single_stock_p_value: float | None,
    single_stock_p_value_is_reference: bool,
    single_stock_insufficient_sample: bool,
    peer_avg_return: float | None,
) -> pd.DataFrame:
    """デモトレード結果df（calc_demo_tradeの出力）にRiskLevel, Score, Rating列を追加して返す。

    hv: 対象銘柄の年率ヒストリカルボラティリティ（%）の直近値。リスク判定（risk_level）を
        銘柄自身の値動きの大きさ基準にするために使う。算出不可の場合はNoneでよい
        （固定閾値にフォールバックする）。
    single_stock_p_value / single_stock_p_value_is_reference: run_single_stock_validationの
        p_value / p_value_is_reference をそのまま渡す（apply_significance_capの安全装置に使う）。
    既存のresult_dfの行・列構成は変更せず、末尾に判定結果の列を追加するのみ。
    不正な入力の場合は空のdf（RATING_COLUMNSのみ）を返す（例外は投げない）。
    """
    required = {"Action", "AvgReturn", "WinRate", "MaxDrawdown"}
    if result_df is None or result_df.empty or not required.issubset(result_df.columns):
        return pd.DataFrame(columns=RATING_COLUMNS)

    df = result_df.reset_index(drop=True).copy()
    ratings = [
        rate_action_row(
            row["Action"], row["AvgReturn"], row["WinRate"], row["MaxDrawdown"], row.get("Horizon"), hv,
            single_stock_hit_rate, single_stock_avg_return, single_stock_p_value, single_stock_p_value_is_reference,
            single_stock_insufficient_sample, peer_avg_return,
        )
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
    「売却」はhorizon概念が無く本来複製されないが、念のため同様に代表1行のみ残す
    （見送りと異なり採点対象なので、固定位置ではなく通常の評価順ソートに含める）。
    Rank列（1始まり）を付加して返す。
    """
    if rated_df is None or rated_df.empty:
        return rated_df

    non_skip = rated_df[rated_df["Action"] != SKIP_ACTION].copy()
    skip_rows = rated_df[rated_df["Action"] == SKIP_ACTION]

    sell_mask = non_skip["Action"] == SELL_ACTION
    if sell_mask.sum() > 1:
        non_skip = pd.concat([non_skip[~sell_mask], non_skip[sell_mask].iloc[[0]]], ignore_index=True)

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


# --- 業種内整合性（業種横断検証専用の独立ラベル） -------------------------------
# 重要：以下はadd_action_ratings/apply_significance_cap等、既存の推奨/検討可/非推奨の
# 判定ロジックには一切組み込まない。完全に独立した補足情報用の判定・ラベル。

SECTOR_VALIDITY_PVALUE_THRESHOLD = 0.05
SECTOR_VALIDITY_MIN_SAMPLE = 5

SECTOR_VALIDITY_UNJUDGEABLE = "判定不可"
SECTOR_VALIDITY_CAUTION = "要注意"
SECTOR_VALIDITY_CONSISTENT = "整合"
SECTOR_VALIDITY_REFERENCE = "参考程度"


def judge_sector_validity(
    peer_p_value: float | None,
    single_stock_avg_return: float | None,
    peer_avg_return: float | None,
    peer_sample_size: int,
) -> str:
    """業種横断検証（peer検証）の結果から「業種内整合性」を判定する。

    既存の推奨/検討可/非推奨の判定（add_action_ratings, apply_significance_cap）とは
    完全に独立した別枠のラベルで、action別ではなく銘柄全体に対して1つ算出する。

    判定基準：
    - peer_sample_size < 5（既存のp値算出可否ルールと同じ閾値）→ 判定不可
    - 単体銘柄とpeer平均の値動きの方向（符号）が不一致 → 要注意
    - p値 < 0.05 かつ方向一致 → 整合
    - p値 >= 0.05（またはp値算出不可）かつ方向一致 → 参考程度
    """
    if peer_sample_size < SECTOR_VALIDITY_MIN_SAMPLE:
        return SECTOR_VALIDITY_UNJUDGEABLE

    direction_matches = (
        single_stock_avg_return is not None
        and peer_avg_return is not None
        and _same_sign(single_stock_avg_return, peer_avg_return)
    )
    if not direction_matches:
        return SECTOR_VALIDITY_CAUTION

    if peer_p_value is not None and peer_p_value < SECTOR_VALIDITY_PVALUE_THRESHOLD:
        return SECTOR_VALIDITY_CONSISTENT
    return SECTOR_VALIDITY_REFERENCE