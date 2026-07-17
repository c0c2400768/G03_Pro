"""岩間担当：類似局面デモトレードのwalk-forward検証（logic/validation.py）。

既存の「類似局面抽出→デモトレード→結果表示」ロジック（similar_periods.py, demo_trade.py）は
変更せず、それらを過去の複数時点から機械的に呼び出して「たまたま当たった結果ではないか」を
検証する処理を追加する。interface.md 6-1〜6-7の実装規約に準拠し、logic/配下のため
Streamlitには依存せず、異常系では例外を投げず空の結果を返す。
"""

from __future__ import annotations

import logging
from typing import Callable

import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

from logic.comparison import select_peer_universe_for_validation, sector_company_count
from logic.data_fetch import get_stock_data
from logic.demo_trade import calc_demo_trade
from logic.indicators import calc_bb_position, calc_bollinger, calc_hv, calc_rsi, calc_volume_ratio
from logic.similar_periods import extract_similar_periods

# 最小ルックバック日数：指標計算の最大ローリング窓（BB/HV/出来高倍率=20）の
# ウォームアップに加え、類似局面探索に最低限意味のある過去プールを確保するための前提値。
# （interface.mdに数値の規定はないため、妥当な前提として設定。要調整の場合は差し替え可）
MIN_LOOKBACK_DAYS = 60

# 評価用未来日数：デモトレードの保有期間分。demo_trade.pyのデフォルトhorizons([5, 10, 20])の
# 最大値に合わせる
EVALUATION_HORIZON_DAYS = 20

# 検証地点の目標数の下限・上限。データ量に応じて動的に算出した目標地点数をこの範囲にクランプする
MIN_VALIDATION_POINTS = 8
MAX_VALIDATION_POINTS = 25

# p値を算出するために最低限必要なサンプル数
MIN_SAMPLE_FOR_PVALUE = 5

# walk-forward検証で「想定方向」を判定する際に使う投資行動
# （新規購入を想定した最も基本的な行動を代表として採用）
VALIDATION_ACTION = "buy_today"

# 業種横断検証（新規実装2）の目標サンプル数。対象銘柄の33業種区分の銘柄数が
# LARGE_SECTOR_COMPANY_COUNT_THRESHOLD以上（業種規模が大きい）場合は目標を引き上げ、
# より多くの同業他社でサンプルを拡張できるようにする。それ未満は従来通り20を維持する。
# 20/30という数字自体は、統計学で正規近似が効きやすい目安とされるn≥30
# （中心極限定理が効きやすい目安）に寄せたもの。業種規模が小さい場合の20は、
# 30を確保できない場合の妥協値として設定している。
LARGE_SECTOR_COMPANY_COUNT_THRESHOLD = 50
DEFAULT_TARGET_SAMPLE_SIZE = 20
LARGE_SECTOR_TARGET_SAMPLE_SIZE = 30

POINT_COLUMNS = [
    "RefDate", "PredictedDirection", "ActualDirection", "Hit", "ActualReturn", "SimilarSampleSize",
]

PEER_RESULT_COLUMNS = ["Ticker", "Points", "HitRate", "AvgReturn", "AvgStrategyReturn", "Hits"]


def _build_indicator_history(price_df: pd.DataFrame) -> pd.DataFrame:
    """株価dfから指標df（Date, RSI, HV, BBPosition, VolumeRatio）を作る。

    ローリング系の指標計算は過去方向のみを見るため、全期間分をまとめて計算しても
    各日付の値は「その日までのデータだけで計算した場合」と一致する
    （look-ahead biasにはならない）。5_similar_market_phases.pyと同じ組み立て方。
    """
    rsi_df = calc_rsi(price_df)
    bb_df = calc_bollinger(price_df)
    bb_pos_df = calc_bb_position(price_df, bb_df)
    hv_df = calc_hv(price_df)
    vol_df = calc_volume_ratio(price_df)

    history = (
        rsi_df.merge(hv_df, on="Date")
        .merge(bb_pos_df, on="Date")
        .merge(vol_df, on="Date")
    )
    return history


def _verifiable_range(total_rows: int, min_lookback_days: int, evaluation_horizon_days: int) -> int:
    """検証地点として配置可能な行番号の範囲（開始〜終了の幅）を返す。データ不足時は負値。"""
    last_valid_idx = total_rows - 1 - evaluation_horizon_days
    return last_valid_idx - min_lookback_days


def _determine_target_points(total_rows: int, min_lookback_days: int, evaluation_horizon_days: int) -> int:
    """検証地点の目標数を、データ量（検証可能な行数の範囲）に応じて動的に算出する。

    verifiable_range // evaluation_horizon_days を目安とし、
    [MIN_VALIDATION_POINTS, MAX_VALIDATION_POINTS]にクランプする
    （評価ウィンドウが重複しすぎる密な配置や、過剰に少ない地点数を避けるため）。
    """
    verifiable_range = _verifiable_range(total_rows, min_lookback_days, evaluation_horizon_days)
    if verifiable_range < 0:
        return MIN_VALIDATION_POINTS
    estimated = verifiable_range // evaluation_horizon_days
    return max(MIN_VALIDATION_POINTS, min(MAX_VALIDATION_POINTS, estimated))


def _determine_validation_points(
    total_rows: int, min_lookback_days: int, evaluation_horizon_days: int, target_points: int
) -> list[int]:
    """検証地点（price_dfの行番号）を固定間隔で機械的に配置し、行番号のリストを返す。

    データ不足でtarget_points地点を確保できない場合は、自動的に地点数を減らす。
    地点間隔がevaluation_horizon_days未満になる（評価ウィンドウが重複し、疑似的な複製に
    なる）配置も避けるため、間隔を保てる範囲で配置できる最大地点数にもクランプする。
    """
    verifiable_range = _verifiable_range(total_rows, min_lookback_days, evaluation_horizon_days)
    if verifiable_range < 0:
        return []

    max_points_by_spacing = verifiable_range // evaluation_horizon_days + 1
    max_points = min(target_points, verifiable_range + 1, max_points_by_spacing)
    if max_points <= 1:
        return [min_lookback_days]

    interval = verifiable_range / (max_points - 1)
    points = sorted({min_lookback_days + round(interval * i) for i in range(max_points)})
    return points


def _evaluate_single_point(
    price_df: pd.DataFrame,
    indicator_history: pd.DataFrame,
    ref_idx: int,
    tolerance: dict[str, float] | None,
    evaluation_horizon_days: int,
) -> dict | None:
    """1検証地点を評価する。データ不足・類似局面なし等の場合はNoneを返す。"""
    ref_date = str(price_df.iloc[ref_idx]["Date"])

    current_rows = indicator_history.loc[indicator_history["Date"] == ref_date]
    if current_rows.empty:
        return None
    current_row = current_rows.iloc[0]
    if current_row[["RSI", "HV", "BBPosition", "VolumeRatio"]].isna().any():
        return None

    current = {
        "RSI": current_row["RSI"],
        "HV": current_row["HV"],
        "BBPosition": current_row["BBPosition"],
        "VolumeRatio": current_row["VolumeRatio"],
    }

    # look-ahead bias防止：類似局面側にもevaluation_horizon_days分の評価窓があるため、
    # 単純にref_date未満で絞るとその窓がref_date以降にはみ出し、未来情報が混入する。
    # そのため、類似局面の評価窓がref_idxより前で完結するsafe_cutoff_idx未満のみを対象にする。
    safe_cutoff_idx = ref_idx - evaluation_horizon_days
    if safe_cutoff_idx < 0:
        return None
    safe_cutoff_date = str(price_df.iloc[safe_cutoff_idx]["Date"])

    past_history = indicator_history.loc[indicator_history["Date"] < safe_cutoff_date]
    similar_df = extract_similar_periods(current, past_history, tolerance)
    if similar_df.empty:
        return None

    trade_df = calc_demo_trade(similar_df, price_df, [VALIDATION_ACTION], [evaluation_horizon_days])
    if trade_df.empty:
        return None

    predicted_return = trade_df.iloc[0]["AvgReturn"]
    predicted_direction = "up" if predicted_return > 0 else ("down" if predicted_return < 0 else "flat")

    exit_idx = ref_idx + evaluation_horizon_days
    if exit_idx >= len(price_df):
        return None

    entry_close = price_df.iloc[ref_idx]["Close"]
    if entry_close == 0 or pd.isna(entry_close):
        return None

    exit_close = price_df.iloc[exit_idx]["Close"]
    if pd.isna(exit_close):
        return None
    actual_return = (exit_close - entry_close) / entry_close
    actual_direction = "up" if actual_return > 0 else ("down" if actual_return < 0 else "flat")

    return {
        "RefDate": ref_date,
        "PredictedDirection": predicted_direction,
        "ActualDirection": actual_direction,
        "Hit": predicted_direction == actual_direction,
        "ActualReturn": actual_return,
        "SimilarSampleSize": len(similar_df),
    }


def _ttest_pvalue(values: list[float]) -> float | None:
    """帰無仮説「平均=0」に対するt検定のp値を返す。算出不能な場合はNone。"""
    if len(values) < 2:
        return None
    try:
        result = stats.ttest_1samp(values, popmean=0)
        p_value = float(result.pvalue)
    except Exception:
        logger.exception("t検定のp値算出に失敗しました（values件数=%d）", len(values))
        return None
    return p_value if pd.notna(p_value) else None


def _strategy_return(predicted_direction: str, actual_return: float) -> float:
    """予測方向に従って売買した場合の「戦略リターン」を返す。

    predicted_direction=="down"の地点はactual_returnの符号を反転する（下落予測が
    当たれば戦略リターンはプラスになる）。"up"はそのまま。"flat"は0とする。
    生のActualReturn（単に検証地点後に株価が上下したか）ではなく、予測方向を
    加味した「その予測に従って売買していたら儲かったか」を測るために使う
    （_aggregate_statsのp_value算出に使用）。
    """
    if predicted_direction == "down":
        return -actual_return
    if predicted_direction == "up":
        return actual_return
    return 0.0


def _binom_test_pvalue(hit_count: int, trial_count: int) -> float | None:
    """帰無仮説「的中率=50%（ランダム）」に対する二項検定のp値を返す。算出不能な場合はNone。"""
    if trial_count < 1:
        return None
    try:
        result = stats.binomtest(hit_count, trial_count, p=0.5)
        p_value = float(result.pvalue)
    except Exception:
        logger.exception("二項検定のp値算出に失敗しました（hit_count=%d, trial_count=%d）", hit_count, trial_count)
        return None
    return p_value if pd.notna(p_value) else None


def _aggregate_stats(
    returns: list[float],
    hits: list[float],
    strategy_returns: list[float],
    hit_count: int,
    trial_count: int,
    sample_count_for_threshold: int,
    target_count: int,
) -> dict:
    """的中率・平均リターン・戦略リターンのp値・的中率のp値をまとめる。

    returns/hits: 従来通りhit_rate/avg_returnの算出に使う（意味は変更しない。生の
        ActualReturn・的中フラグ、または業種横断側では社ごとのAvgReturn・HitRate）。
    strategy_returns: 予測方向を加味した「戦略リターン」の系列（_strategy_return参照）。
        0と有意に異なるかをt検定し、p_valueとして返す（生のActualReturnへのt検定では
        「予測が当たったか」ではなく「単に地点後に株価が上がったか」を検定してしまうため、
        こちらに差し替えている）。
    hit_count/trial_count: 方向的中率の二項検定（ランダム50%との比較）に使う的中数・
        試行数。的中率のリスト（hits）は業種横断側では社ごとの小数値（0〜1）になり
        二項検定にそのまま使えないため、呼び出し元で地点単位の整数カウントを別途渡す。
    サンプル数に応じてp値の算出可否・参考値扱いを判定する（従来通り）。
    """
    if not returns:
        return {
            "hit_rate": None, "avg_return": None,
            "p_value": None, "p_value_is_reference": False,
            "hit_rate_p_value": None, "insufficient_sample": True,
        }

    hit_rate = sum(hits) / len(hits)
    avg_return = sum(returns) / len(returns)

    if sample_count_for_threshold < MIN_SAMPLE_FOR_PVALUE:
        return {
            "hit_rate": hit_rate, "avg_return": avg_return,
            "p_value": None, "p_value_is_reference": False,
            "hit_rate_p_value": None, "insufficient_sample": True,
        }

    p_value = _ttest_pvalue(strategy_returns)
    hit_rate_p_value = _binom_test_pvalue(hit_count, trial_count)
    return {
        "hit_rate": hit_rate, "avg_return": avg_return,
        "p_value": p_value, "p_value_is_reference": sample_count_for_threshold < target_count,
        "hit_rate_p_value": hit_rate_p_value, "insufficient_sample": False,
    }


def run_single_stock_validation(
    price_df: pd.DataFrame,
    target_points: int | None = None,
    min_lookback_days: int = MIN_LOOKBACK_DAYS,
    evaluation_horizon_days: int = EVALUATION_HORIZON_DAYS,
    tolerance: dict[str, float] | None = None,
) -> dict:
    """単体銘柄のwalk-forward検証（新規実装1）を実行する。

    対象期間内にtarget_points地点を機械的な間隔で配置し、各地点でその時点より前の
    データのみを使って類似局面抽出→デモトレードを行い、想定方向と実際の値動きの方向を照合する。

    Args:
        price_df: 検証対象銘柄の株価df（Date, Open, High, Low, Close, Volume）。
        target_points: 目標検証地点数。未指定（None）の場合はデータ量に応じて
            _determine_target_pointsで動的に算出する（[MIN_VALIDATION_POINTS,
            MAX_VALIDATION_POINTS]の範囲）。明示的に指定した場合はその値を優先する。
        min_lookback_days: 各検証地点で最低限確保する過去データの日数。
        evaluation_horizon_days: 検証地点から何営業日後の値動きと照合するか。
        tolerance: 類似局面抽出の許容幅（未指定時はextract_similar_periodsの既定値）。

    Returns:
        以下のキーを持つdict（データ不足等の場合はpointsが空dfになり、統計値はNone）。
        - points: 検証地点ごとの明細df（POINT_COLUMNS）
        - requested_points / actual_points: 目標地点数 / 実際に評価できた地点数
        - hit_rate / avg_return / p_value / p_value_is_reference / hit_rate_p_value /
          insufficient_sample（p_valueは戦略リターンのt検定、hit_rate_p_valueは
          方向的中率の二項検定。詳細は_aggregate_stats参照）
        - avg_strategy_return / hit_count: 業種横断検証（run_peer_universe_validation）が
          社単位で集計する際に使う中間値（戦略リターンの平均・的中数）
        - adjustment_message: 地点数を自動調整した場合の説明文（調整なしはNone）
    """
    empty_points = pd.DataFrame(columns=POINT_COLUMNS)
    result = {
        "points": empty_points, "requested_points": target_points, "actual_points": 0,
        "hit_rate": None, "avg_return": None, "p_value": None,
        "p_value_is_reference": False, "hit_rate_p_value": None, "insufficient_sample": True,
        "avg_strategy_return": None, "hit_count": 0, "adjustment_message": None,
    }

    if price_df is None or price_df.empty or not {"Date", "Close"}.issubset(price_df.columns):
        return result

    price = price_df.reset_index(drop=True).copy()
    price["Date"] = price["Date"].astype(str)

    if target_points is None:
        target_points = _determine_target_points(len(price), min_lookback_days, evaluation_horizon_days)
        result["requested_points"] = target_points

    ref_indices = _determine_validation_points(len(price), min_lookback_days, evaluation_horizon_days, target_points)
    if not ref_indices:
        return result

    indicator_history = _build_indicator_history(price)
    if indicator_history.empty:
        return result
    indicator_history = indicator_history.copy()
    indicator_history["Date"] = indicator_history["Date"].astype(str)

    rows = [
        r for r in (
            _evaluate_single_point(price, indicator_history, idx, tolerance, evaluation_horizon_days)
            for idx in ref_indices
        )
        if r is not None
    ]

    points_df = pd.DataFrame(rows, columns=POINT_COLUMNS) if rows else empty_points

    strategy_returns = [_strategy_return(r["PredictedDirection"], r["ActualReturn"]) for r in rows]
    hit_count = sum(1 for r in rows if r["Hit"])
    avg_strategy_return = sum(strategy_returns) / len(strategy_returns) if strategy_returns else None

    stats_result = _aggregate_stats(
        [r["ActualReturn"] for r in rows], [r["Hit"] for r in rows],
        strategy_returns, hit_count, len(rows),
        sample_count_for_threshold=len(rows), target_count=target_points,
    )

    adjustment_message = None
    if len(ref_indices) < target_points:
        adjustment_message = f"データ不足のため検証地点を{len(ref_indices)}地点に調整しました"

    result.update({
        "points": points_df, "actual_points": len(rows),
        "avg_strategy_return": avg_strategy_return, "hit_count": hit_count,
        "adjustment_message": adjustment_message,
        **stats_result,
    })
    return result


def _determine_target_sample_size(ticker: str) -> int:
    """対象銘柄の33業種区分の銘柄数から、業種横断検証の目標サンプル数を決める。

    業種の総銘柄数がLARGE_SECTOR_COMPANY_COUNT_THRESHOLD以上ならより多くの
    同業他社が存在するとみなしLARGE_SECTOR_TARGET_SAMPLE_SIZEに引き上げ、
    それ未満・業種が特定できない場合はDEFAULT_TARGET_SAMPLE_SIZEを維持する。
    """
    if sector_company_count(ticker) >= LARGE_SECTOR_COMPANY_COUNT_THRESHOLD:
        return LARGE_SECTOR_TARGET_SAMPLE_SIZE
    return DEFAULT_TARGET_SAMPLE_SIZE


def run_peer_universe_validation(
    ticker: str,
    price_df: pd.DataFrame,
    period: str,
    target_points: int | None = None,
    target_sample_size: int | None = None,
    min_lookback_days: int = MIN_LOOKBACK_DAYS,
    evaluation_horizon_days: int = EVALUATION_HORIZON_DAYS,
    tolerance: dict[str, float] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """業種横断でサンプル拡張したwalk-forward検証（新規実装2）を実行する。

    対象銘柄＋select_peer_universe_for_validationで抽出した同業他社それぞれに対して
    run_single_stock_validation（新規実装1）を実行し、結果を社単位で合算する。
    「この銘柄で当たるか」ではなく「手法自体に再現性があるか」を検証するための集計。

    Args:
        ticker: 検証対象銘柄コード。
        price_df: 対象銘柄の株価df（呼び出し元で取得済みのものを再利用し、再取得しない）。
        period: peer銘柄の株価取得に使う期間文字列（get_stock_dataにそのまま渡す）。
        target_points: 各社のrun_single_stock_validationに渡す目標検証地点数。
            未指定（None）の場合は社ごとのデータ量に応じて動的に算出される。
        target_sample_size: peer拡張の目標サンプル数。未指定（None）の場合は
            対象銘柄の業種規模（_determine_target_sample_size）に応じて20または30を使う。
        progress_callback: 進捗表示用の任意コールバック（完了社数, 対象社数合計）。
            対象銘柄＋peer銘柄のuniverseループ内で各社の検証が終わるたびに呼ばれる。
            pages側でst.progress等の更新に使うことを想定した単なる関数呼び出しであり、
            この関数自体はStreamlit依存を持ち込まない。未指定（None）の場合は何もしない。

    Returns:
        以下のキーを持つdict。
        - peer_tickers: 抽出されたpeer銘柄コードのリスト
        - target_sample_size: 目標サンプル数
        - company_count: 実際に検証できた社数（対象銘柄を含む）
        - total_points: 全社合計の実際の検証地点数
        - hit_rate / avg_return / p_value / p_value_is_reference / insufficient_sample:
          いずれも「地点単位」ではなく、per_companyの社ごとの値（HitRate/AvgReturn）を
          社単位で単純平均したもの。p_value（戦略リターンのt検定）も社ごとの
          AvgStrategyReturnのリストに対して算出しており、集計単位を社単位に揃えている。
          これは、集計単位（社単位）に揃えることで、同一社内の複数地点をそれぞれ
          独立サンプルとして扱う疑似反復（pseudoreplication。本来は独立でない
          同一銘柄内の複数観測を、あたかも独立な多数のサンプルであるかのように扱ってしまい、
          有意性を過大評価すること）を避けるための設計。
        - hit_rate_p_value: 方向的中率の二項検定のp値。こちらは社ごとの的中率（小数）を
          そのまま二項検定に使えないため、全社の的中数・検証地点数をプールした値で算出する
          （t検定と違い、二項検定は個々の的中/不的中という離散イベントの検定のため、
          社をまたいでプールしても集計単位のずれによる問題は生じにくい）。
        - per_company: 社ごとの明細df（PEER_RESULT_COLUMNS）
    """
    empty_per_company = pd.DataFrame(columns=PEER_RESULT_COLUMNS)
    result = {
        "peer_tickers": [], "target_sample_size": target_sample_size, "company_count": 0,
        "total_points": 0, "hit_rate": None, "avg_return": None, "p_value": None,
        "p_value_is_reference": False, "hit_rate_p_value": None, "insufficient_sample": True,
        "per_company": empty_per_company,
    }

    if not ticker or price_df is None or price_df.empty:
        return result

    if target_sample_size is None:
        target_sample_size = _determine_target_sample_size(ticker)
        result["target_sample_size"] = target_sample_size

    peer_tickers = select_peer_universe_for_validation(ticker, target_sample_size)
    result["peer_tickers"] = peer_tickers

    universe = [(ticker, price_df)]
    for peer_ticker in peer_tickers:
        peer_df = get_stock_data(peer_ticker, period)
        if peer_df is None or peer_df.empty:
            continue
        universe.append((peer_ticker, peer_df))

    per_company_rows = []
    total_companies = len(universe)
    for i, (company_ticker, company_df) in enumerate(universe, start=1):
        single_result = run_single_stock_validation(
            company_df, target_points, min_lookback_days, evaluation_horizon_days, tolerance
        )
        if single_result["actual_points"] != 0:
            per_company_rows.append({
                "Ticker": company_ticker,
                "Points": single_result["actual_points"],
                "HitRate": single_result["hit_rate"],
                "AvgReturn": single_result["avg_return"],
                "AvgStrategyReturn": single_result["avg_strategy_return"],
                "Hits": single_result["hit_count"],
            })
        if progress_callback is not None:
            progress_callback(i, total_companies)

    if not per_company_rows:
        return result

    per_company_df = pd.DataFrame(per_company_rows, columns=PEER_RESULT_COLUMNS)

    # hit_rate_p_value（二項検定）は社ごとの小数の的中率をそのまま使えないため、
    # 全社の的中数・検証地点数をプールしたカウントで算出する（クラス docstring参照）。
    total_hits = int(per_company_df["Hits"].sum())
    total_points = int(per_company_df["Points"].sum())

    stats_result = _aggregate_stats(
        per_company_df["AvgReturn"].tolist(), per_company_df["HitRate"].tolist(),
        per_company_df["AvgStrategyReturn"].tolist(), total_hits, total_points,
        sample_count_for_threshold=len(per_company_df), target_count=target_sample_size,
    )

    result.update({
        "company_count": len(per_company_df),
        "total_points": int(per_company_df["Points"].sum()),
        "per_company": per_company_df,
        **stats_result,
    })
    return result
