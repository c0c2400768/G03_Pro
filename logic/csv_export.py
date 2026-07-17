"""相川担当：CSV保存処理（logic/csv_export.py）"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from logic.decision_rating import SELL_FIXED_RATING, SELL_FIXED_RISK_LEVEL, SKIP_ACTION, rating_to_mark
from logic.demo_trade import ACTION_LABELS, SELL_ACTION
from logic.ticker_lookup import get_company_name


def save_csv(df: pd.DataFrame, filename: str) -> bool:
    """DataFrameをCSVファイルとして保存し、成功時True・失敗時Falseを返す（UI処理は行わない）。"""
    try:
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        return True
    except Exception:
        return False


# 補助判断のCSVエクスポート専用の列ラベル・並び順。
# 画面表示（pages/_decision_support_view.pyの比較表）と同じ日本語ラベル・整形方式に揃える。
_EXPORT_COLUMN_LABELS = {
    "Rank": "順位",
    "ActionLabel": "投資行動",
    "HorizonLabel": "経過日数",
    "AvgReturnLabel": "平均リターン",
    "WinRateLabel": "勝率",
    "MaxLossLabel": "最大損失",
    "MaxDrawdownLabel": "最大含み損率",
    "AvgHoldDaysLabel": "平均保有日数",
    "SampleSizeLabel": "検証件数",
    "RiskLevel": "リスク",
    "Rating": "評価",
}

_EXPORT_COLUMN_ORDER = [
    "Rank", "ActionLabel", "HorizonLabel", "AvgReturnLabel", "WinRateLabel",
    "MaxLossLabel", "MaxDrawdownLabel", "AvgHoldDaysLabel", "SampleSizeLabel",
    "RiskLevel", "Rating",
]


def _format_horizon(row: pd.Series) -> str:
    """見送り（skip）・売却（sell）は経過日数の概念が無いため「―」、それ以外は「N営業日」を返す。"""
    if row["Action"] in (SKIP_ACTION, SELL_ACTION):
        return "―"
    return f"{int(row['Horizon'])}営業日"


def _format_action_label(row: pd.Series) -> str:
    """「追加購入」はholdと計算式が同一のため独立行動を持たず、hold行の最終判定（Rating）を
    ◯/△/×の記号で流用表示する（画面表示のpages/_decision_support_view.pyと同じ方式）。"""
    label = ACTION_LABELS.get(row["Action"], row["Action"])
    if row["Action"] == "hold":
        return f"{label}[追加購入{rating_to_mark(row['Rating'])}]"
    return label


def build_decision_support_export(
    ranked_df: pd.DataFrame,
    ticker: str,
    stance: str,
    generated_at: datetime | None = None,
) -> str:
    """補助判断の比較結果（decision_rating.rank_rated_actionsの出力）を、日本語ラベル・
    整形済み数値のCSV文字列として組み立てて返す。

    - Action列の内部コード（buy_today等）は画面表示と同じ日本語ラベルに変換する
    - AvgReturn/WinRate/MaxLoss/MaxDrawdownはパーセント表記（小数第1〜2位）に整形する
    - 先頭に銘柄名・立場・出力日時のヘッダー行を付け、単体では意味が分かるファイルにする
    - ranked_dfが空・Noneの場合は空文字列を返す（例外は投げない）
    """
    if ranked_df is None or ranked_df.empty:
        return ""

    if generated_at is None:
        generated_at = datetime.now()

    df = ranked_df.copy()
    df["ActionLabel"] = df.apply(_format_action_label, axis=1)
    df["HorizonLabel"] = df.apply(_format_horizon, axis=1)
    df["AvgReturnLabel"] = df["AvgReturn"].map(lambda x: f"{x:+.2%}")
    # sell（売却）は確定値1つのみでWinRate/MaxLoss/MaxDrawdownという概念が無くNoneのため、
    # SampleSizeLabelと同様にpd.notna()でガードして「―」を返す
    df["WinRateLabel"] = df["WinRate"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "―")
    df["MaxLossLabel"] = df["MaxLoss"].map(lambda x: f"{x:+.2%}" if pd.notna(x) else "―")
    df["MaxDrawdownLabel"] = df["MaxDrawdown"].map(lambda x: f"{x:+.2%}" if pd.notna(x) else "―")
    df["AvgHoldDaysLabel"] = df["AvgHoldDays"].map(lambda x: f"{x:.1f}日")
    df["SampleSizeLabel"] = df["SampleSize"].map(lambda x: f"{int(x)}件" if pd.notna(x) else "―")
    # sellのRiskLevel/Ratingは画面表示（pages/_decision_support_view.py）と同じ固定値
    # （SELL_FIXED_RISK_LEVEL="－"、SELL_FIXED_RATING=""）のため、Ratingの空文字列は
    # CSV上も同じダッシュで出力されるようにする（RiskLevelは元々ダッシュなのでそのままでよい）
    df["Rating"] = df["Rating"].map(lambda x: SELL_FIXED_RISK_LEVEL if x == SELL_FIXED_RATING else x)

    export_df = df[_EXPORT_COLUMN_ORDER].rename(columns=_EXPORT_COLUMN_LABELS)

    header_lines = [
        f"銘柄,{get_company_name(ticker)}（{ticker}）",
        f"立場,{stance}",
        f"出力日時,{generated_at.strftime('%Y-%m-%d %H:%M')}",
        "注意,このおすすめ行動は、複数の投資行動パターンを比較し、その中で最も成績が良かったものを"
        "選んでいます。比較する候補が多いほど、実際の実力より良い結果に見えやすくなる統計的な性質が"
        "あるため、参考情報の一つとしてご覧ください。",
        "",
    ]
    return "\n".join(header_lines) + export_df.to_csv(index=False)