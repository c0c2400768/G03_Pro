"""相川担当：補助判断ページの上部（結論カード・比較表・判断の切り口）表示ロジック
（pages/_decision_support_view.py）。

ファイル名を`_`始まりにしているため、Streamlitのナビゲーション（app.pyのst.navigation）には
現れない（app.pyがpages/配下を明示的にst.Pageで列挙する構成のため、そもそも対象にもならない）。
7_decision_support.pyの既存の描画部分から分離した関数として実装しており、
将来的に別ページへ移動する場合はこのモジュールをそのまま呼び出し元だけ差し替えればよい。
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from logic.decision_rating import (
    RATING_CONSIDERABLE,
    RATING_NOT_RECOMMENDED,
    RATING_RECOMMENDED,
    SECTOR_VALIDITY_CAUTION,
    SECTOR_VALIDITY_CONSISTENT,
    SECTOR_VALIDITY_REFERENCE,
    SECTOR_VALIDITY_UNJUDGEABLE,
    SELL_FIXED_RATING,
    SELL_FIXED_RISK_LEVEL,
    SIGNIFICANCE_PVALUE_REFERENCE_THRESHOLD,
    SIGNIFICANCE_PVALUE_THRESHOLD,
    SKIP_ACTION,
    rating_to_mark,
)
from logic.demo_trade import ACTION_LABELS, SELL_ACTION, calc_unrealized_return
from logic.error_utils import show_warning

_STYLE = """
<style>
.ds-card-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; }
.ds-card-title { display:flex; align-items:center; gap:10px; font-size:20px; font-weight:700; color:#1f2937; }
.ds-badge-stance { background:#f3f4f6; color:#374151; padding:4px 12px; border-radius:999px; font-size:13px; }

.ds-action-tile { background:#eafaf1; border-radius:12px; padding:16px 20px; margin-bottom:16px; }
.ds-action-tile-label { font-size:13px; color:#4b5563; margin-bottom:4px; }
.ds-action-tile-value { font-size:24px; font-weight:700; color:#166534; }

.ds-metric-row { display:flex; gap:16px; margin-bottom:16px; }
.ds-metric-tile { flex:1; border-radius:12px; padding:16px; text-align:center; }
.ds-metric-tile-label { font-size:12px; color:#4b5563; margin-bottom:6px; }
.ds-metric-tile-value { font-size:22px; font-weight:700; }
.ds-metric-tile-sub { font-size:13px; font-weight:600; margin-top:2px; }
.ds-metric-green { background:#eafaf1; }
.ds-metric-green .ds-metric-tile-value { color:#166534; }
.ds-metric-blue { background:#eaf2fb; }
.ds-metric-blue .ds-metric-tile-value { color:#1d4ed8; }
.ds-metric-amber { background:#fff8e1; }
.ds-metric-amber .ds-metric-tile-value { color:#92400e; font-size:18px; }
.ds-metric-amber .ds-metric-tile-sub { color:#92400e; }

.ds-desc-text { font-size:14px; color:#374151; }

.ds-table { width:100%; border-collapse:collapse; font-size:14px; }
.ds-table th { text-align:left; color:#6b7280; font-weight:600; font-size:13px; padding:8px 10px; border-bottom:1px solid #e5e7eb; }
.ds-table td { padding:10px; border-bottom:1px solid #f3f4f6; vertical-align:middle; color:#1f2937; }
.ds-return-pos { color:#16a34a; font-weight:600; }
.ds-return-neg { color:#dc2626; font-weight:600; }
.ds-winrate-bar-track { background:#e5e7eb; border-radius:999px; height:6px; width:70px; display:inline-block; vertical-align:middle; margin-right:8px; }
.ds-winrate-bar-fill { background:#22c55e; border-radius:999px; height:6px; display:inline-block; }

.ds-pill { padding:3px 10px; border-radius:999px; font-size:13px; font-weight:600; white-space:nowrap; }
.ds-pill-risk-低 { background:#dcfce7; color:#15803d; }
.ds-pill-risk-中 { background:#fef3c7; color:#92400e; }
.ds-pill-risk-高 { background:#fee2e2; color:#b91c1c; }
.ds-pill-risk-なし { background:#f3f4f6; color:#6b7280; }
.ds-pill-rating-recommended { background:#dcfce7; color:#15803d; }
.ds-pill-rating-considerable { background:#dbeafe; color:#1d4ed8; }
.ds-pill-rating-not_recommended { background:#f3f4f6; color:#4b5563; }

/* margin-bottom:16pxは、st.markdownのラッパー要素(stMarkdownContainer)がst側で
   margin-bottom:-16pxを持つため、その分を打ち消してst.container(border=True)の
   下端とカードの下端を揃えるためのもの（打ち消さないとカードが外枠の下端をはみ出す）。 */
.ds-angle-row { display:flex; align-items:stretch; gap:16px; margin-bottom:16px; }
.ds-angle-card { flex:1; border-radius:12px; padding:16px; }
.ds-angle-green { background:#f0fdf4; }
.ds-angle-blue { background:#eff6ff; }
.ds-angle-purple { background:#faf5ff; }
.ds-angle-title { font-size:13px; font-weight:700; margin-bottom:8px; color:#1f2937; }
.ds-angle-action { font-size:15px; font-weight:700; margin-bottom:6px; color:#1f2937; }
.ds-angle-desc { font-size:13px; color:#4b5563; }

.ds-footer { background:#fff8e1; border-radius:12px; padding:16px 20px; font-size:13px; color:#78350f; }

.ds-stat-header { display:flex; align-items:flex-start; gap:14px; margin-bottom:16px; }
.ds-stat-icon { width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:20px; flex-shrink:0; }
.ds-stat-icon-green { background:#dcfce7; }
.ds-stat-icon-blue { background:#dbeafe; }
.ds-stat-title { font-size:16px; font-weight:700; color:#1f2937; margin-bottom:4px; }
.ds-stat-desc { font-size:13px; color:#6b7280; }
.ds-stat-note { font-size:12px; color:#6b7280; margin:4px 0 12px 0; }

.ds-th-info { cursor:help; color:#9ca3af; font-size:11px; margin-left:2px; }
</style>
"""

_RATING_PILL_CLASS = {
    RATING_RECOMMENDED: "ds-pill-rating-recommended",
    RATING_CONSIDERABLE: "ds-pill-rating-considerable",
    RATING_NOT_RECOMMENDED: "ds-pill-rating-not_recommended",
}

_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

# 比較表の列見出しに添えるiマークのツールチップ文言（title属性で表示）。
# 既存の推奨/検討可/非推奨の判定ロジックには影響しない表示専用の説明。
_COMPARISON_COLUMN_TOOLTIPS = {
    "平均リターン": "過去の類似局面を起点に、この投資行動を取った場合のリターンの平均値です。",
    "勝率": "過去の類似局面のうち、リターンがプラスになった割合です。",
    "リスク": (
        "この銘柄の値動きの大きさ（HV）を基準にした、最大ドローダウンの相対的な大きさです"
        "（低/中/高）。HVが算出できない場合は固定の閾値（3%/6%）で判定します。"
    ),
    "評価": (
        "平均リターン・勝率・リスクの3項目を均等に採点したスコアに、単体銘柄の統計的有意性チェック"
        "（p値・方向一致・的中率）による安全装置を適用した最終判定です。"
    ),
}


def _comparison_th_html(label: str) -> str:
    tooltip = _COMPARISON_COLUMN_TOOLTIPS.get(label)
    if tooltip is None:
        return f"<th>{label}</th>"
    return f'<th>{label} <span class="ds-th-info" title="{html.escape(tooltip)}">ℹ️</span></th>'

# judge_sector_validity（業種内整合性）の各ラベルの意味を、目視で確認しやすいよう
# 一言補足として併記する。既存の推奨/検討可/非推奨の判定ロジックには影響しない表示専用の説明
_SECTOR_VALIDITY_DESCRIPTIONS = {
    SECTOR_VALIDITY_CONSISTENT: "同業他社と方向性が一致し、統計的にも有意です。",
    SECTOR_VALIDITY_REFERENCE: "同業他社と方向性は一致していますが、統計的な有意性はまだ弱い（参考程度）です。",
    SECTOR_VALIDITY_CAUTION: "この銘柄と同業他社平均で値動きの方向が一致していません。判定の信頼度にご注意ください。",
    SECTOR_VALIDITY_UNJUDGEABLE: "同業他社のサンプル数が少なく、整合性を判定できませんでした。",
}


def inject_styles() -> None:
    """このモジュール・_validation_view.pyで共通利用するカードデザインのCSSを注入する。"""
    st.markdown(_STYLE, unsafe_allow_html=True)


def _action_label(row: pd.Series) -> str:
    """行動ラベルを組み立てる。skip・sell等horizon概念が無い行動（Horizon=NaN）は
    「（N営業日）」の付与を省く（int(nan)はValueErrorになるため、NaN判定が必須）。"""
    label = ACTION_LABELS.get(row["Action"], row["Action"])
    if row["Action"] == SKIP_ACTION or pd.isna(row["Horizon"]):
        return label
    return f"{label}（{int(row['Horizon'])}営業日）"


def _comparison_action_label(row: pd.Series) -> str:
    """比較表専用のラベル。「追加購入」はholdと計算式が同一のため独立行動を持たず、
    hold行の最終判定（Rating）を◯/△/×の記号で流用表示する
    （この表示変更は補助判断画面の比較表限定。pages/6のデモトレード結果画面は対象外）。"""
    label = _action_label(row)
    if row["Action"] == "hold":
        return f"{label}[追加購入{rating_to_mark(row['Rating'])}]"
    return label


def _return_html(avg_return: float) -> str:
    css_class = "ds-return-pos" if avg_return > 0 else "ds-return-neg"
    return f'<span class="{css_class}">{avg_return:+.2%}</span>'


def _winrate_html(win_rate: float | None) -> str:
    # sell（売却）は確定値1つのみで勝率という概念が無くWinRate=Noneのため、
    # バー付き表示はせずSELL_FIXED_RISK_LEVEL（－）と同じダッシュのみ表示する。
    if win_rate is None or pd.isna(win_rate):
        return SELL_FIXED_RISK_LEVEL
    width = max(0.0, min(1.0, win_rate)) * 100
    return (
        f'<span class="ds-winrate-bar-track">'
        f'<span class="ds-winrate-bar-fill" style="width:{width:.0f}%"></span></span>'
        f"{win_rate:.0%}"
    )


def _risk_pill_html(risk_level: str) -> str:
    return f'<span class="ds-pill ds-pill-risk-{risk_level}">{risk_level}</span>'


def _rating_pill_html(rating: str) -> str:
    css_class = _RATING_PILL_CLASS.get(rating, "ds-pill-rating-not_recommended")
    return f'<span class="ds-pill {css_class}">{rating}</span>'


def _risk_cell_html(risk_level: str) -> str:
    """sell（売却）のRiskLevel固定値（SELL_FIXED_RISK_LEVEL）にはCSSの色分けクラスが
    無いため、ピルで包まずプレーンテキストのまま表示する。"""
    if risk_level == SELL_FIXED_RISK_LEVEL:
        return risk_level
    return _risk_pill_html(risk_level)


def _rating_cell_html(rating: str) -> str:
    """sell（売却）のRating固定値（SELL_FIXED_RATING、空文字列）は、そのままだと
    空のピルが出てしまうため、ダッシュのプレーンテキストで表示する。"""
    if rating == SELL_FIXED_RATING:
        return SELL_FIXED_RISK_LEVEL
    return _rating_pill_html(rating)


def render_conclusion_card(
    recommended_row: pd.Series | None,
    ranked_df: pd.DataFrame,
    stance: str,
    sector_validity_label: str | None = None,
) -> None:
    """結論カード（おすすめ行動・平均リターン・勝率・参考:最良結果）を表示する。

    sector_validity_label: judge_sector_validityの判定結果（業種内整合性）。既存の
        推奨/検討可/非推奨とは無関係の別枠の補足情報として、銘柄全体に対して1行だけ表示する。
        Noneの場合は表示しない（統計検証データが無い等）。
    """
    with st.container(border=True):
        st.markdown(
            f'<div class="ds-card-header">'
            f'<div class="ds-card-title">✅ 結論</div>'
            f'<div class="ds-badge-stance">立場：{stance}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        if recommended_row is None:
            show_warning("有効な投資行動の判定結果がありませんでした。")
            return

        non_skip_df = ranked_df[ranked_df["Action"] != SKIP_ACTION]
        best_return_row = non_skip_df.loc[non_skip_df["AvgReturn"].idxmax()] if not non_skip_df.empty else None

        if recommended_row["Rating"] == RATING_NOT_RECOMMENDED:
            # 全行動が非推奨だった場合、ranked_dfの先頭行（相対的にマシだった非推奨行動）を
            # 「おすすめ」と誤解されないよう、おすすめ行動タイルは出さず警告＋参考情報にとどめる。
            show_warning(
                "今回は推奨できる投資行動がありませんでした。"
                "最も成績が良かった行動でも「非推奨」判定のため、様子見（見送り）も選択肢としてご検討ください。"
            )
            st.markdown(
                f'<div class="ds-desc-text">参考（非推奨）：'
                f'「{_action_label(recommended_row)}」が候補の中では相対的に良い結果でしたが、'
                f"統計的な裏付けは確認できていません。</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="ds-action-tile">'
                f'<div class="ds-action-tile-label">📅 おすすめ行動</div>'
                f'<div class="ds-action-tile-value">{_action_label(recommended_row)}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

            best_return_sub = ""
            if best_return_row is not None:
                best_return_sub = f'<div class="ds-metric-tile-sub">{_action_label(best_return_row)}</div>'

            st.markdown(
                f'<div class="ds-metric-row">'
                f'<div class="ds-metric-tile ds-metric-green">'
                f'<div class="ds-metric-tile-label">📈 平均リターン</div>'
                f'<div class="ds-metric-tile-value">{recommended_row["AvgReturn"]:+.2%}</div></div>'
                f'<div class="ds-metric-tile ds-metric-blue">'
                f'<div class="ds-metric-tile-label">🥧 勝率</div>'
                f'<div class="ds-metric-tile-value">{recommended_row["WinRate"]:.0%}</div></div>'
                f'<div class="ds-metric-tile ds-metric-amber">'
                f'<div class="ds-metric-tile-label">⭐ 参考：最良結果</div>'
                f'<div class="ds-metric-tile-value">{best_return_sub}</div></div>'
                f"</div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                f'<div class="ds-desc-text">過去の類似局面では、'
                f'「{_action_label(recommended_row)}」が平均的に良い結果でした'
                f'（平均リターン{recommended_row["AvgReturn"]:+.2%}、勝率{recommended_row["WinRate"]:.0%}）。'
                f"</div>",
                unsafe_allow_html=True,
            )

        if sector_validity_label is not None:
            description = _SECTOR_VALIDITY_DESCRIPTIONS.get(sector_validity_label, "")
            st.markdown(
                f'<div class="ds-desc-text">🏢 業種内整合性：{sector_validity_label}'
                f'（{description}）</div>',
                unsafe_allow_html=True,
            )


def render_unrealized_pl_card(purchase_price: float | None, current_price: float | None) -> None:
    """「現在の含み損益」カードを表示する。

    「今日売る」の損益は購入価格と現在値だけで一意に決まる確定値であり、他の投資行動
    （hold・buy_today等）のような過去の類似局面に基づく予測分布ではないため、結論カードや
    比較表（推奨/検討可/非推奨の判定・順位付け）とは別の独立カードとして表示する。
    purchase_price/current_priceのいずれかが取得できずcalc_unrealized_returnがNoneを
    返す場合は何も表示しない（stance="これから購入する"の場合はそもそも呼び出さない想定）。
    """
    confirmed_return = calc_unrealized_return(purchase_price, current_price)
    if confirmed_return is None:
        return

    css_class = "ds-return-pos" if confirmed_return > 0 else "ds-return-neg"

    with st.container(border=True):
        st.markdown(
            '<div class="ds-card-header">'
            '<div class="ds-card-title">📌 現在の含み損益</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="ds-action-tile">'
            f'<div class="ds-action-tile-label">今すぐ売却した場合の確定リターン</div>'
            f'<div class="ds-action-tile-value"><span class="{css_class}">{confirmed_return:+.2%}</span></div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="ds-desc-text">購入価格 {purchase_price:,.1f} → 現在値 {current_price:,.1f}'
            f'（差額 {current_price - purchase_price:+,.1f}）</div>',
            unsafe_allow_html=True,
        )


def render_comparison_table(ranked_df: pd.DataFrame) -> None:
    """投資行動の比較表（順位・投資行動・平均リターン・勝率・リスク・評価）を表示する。"""
    with st.container(border=True):
        st.markdown(
            '<div class="ds-card-header">'
            '<div class="ds-card-title">📊 投資行動の比較</div>'
            '<div class="ds-desc-text">平均リターンだけでなく、勝率とリスクもあわせて確認してください。</div>'
            "</div>",
            unsafe_allow_html=True,
        )

        if ranked_df is None or ranked_df.empty:
            show_warning("比較できる投資行動がありません。")
            return

        rows_html = []
        has_sell_row = False
        for _, row in ranked_df.iterrows():
            is_sell = row["Action"] == SELL_ACTION
            has_sell_row = has_sell_row or is_sell
            if is_sell:
                # sellは購入価格・現在値から一意に決まる確定値で採点・順位付けの対象外
                # （rank_rated_actions参照）のため、Rank列に振られた通し番号は表示せず
                # ダッシュにする（下部の注記で理由を説明する）。
                rank_label = SELL_FIXED_RISK_LEVEL
            else:
                rank = int(row["Rank"])
                rank_label = f'{_MEDALS.get(rank, "")} {rank}位'.strip()
            rows_html.append(
                "<tr>"
                f"<td>{rank_label}</td>"
                f"<td>{_comparison_action_label(row)}</td>"
                f"<td>{_return_html(row['AvgReturn'])}</td>"
                f"<td>{_winrate_html(row['WinRate'])}</td>"
                f"<td>{_risk_cell_html(row['RiskLevel'])}</td>"
                f"<td>{_rating_cell_html(row['Rating'])}</td>"
                "</tr>"
            )

        headers_html = "".join(
            _comparison_th_html(label) for label in ["順位", "投資行動", "平均リターン", "勝率", "リスク", "評価"]
        )
        table_html = (
            "<table class=\"ds-table\"><thead><tr>" + headers_html + "</tr></thead><tbody>"
            + "".join(rows_html) + "</tbody></table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)

        if has_sell_row:
            st.markdown(
                '<div class="ds-stat-note">ℹ️ 「売却」は購入価格と現在値から一意に決まる確定値であり、'
                "他の投資行動のような過去の類似局面に基づく予測比較の対象ではないため、"
                "順位・評価（ランキング）の対象外とし「－」で表示しています。現在の含み損益は"
                '上部の「📌 現在の含み損益」カードをご覧ください。</div>',
                unsafe_allow_html=True,
            )


def _pick_best_return(non_skip_df: pd.DataFrame) -> pd.Series | None:
    if non_skip_df.empty:
        return None
    return non_skip_df.loc[non_skip_df["AvgReturn"].idxmax()]


def _pick_fastest_entry(non_skip_df: pd.DataFrame) -> pd.Series | None:
    buy_today_df = non_skip_df[non_skip_df["Action"] == "buy_today"]
    if buy_today_df.empty:
        return None
    return buy_today_df.sort_values(by=["Rank"]).iloc[0]


def _pick_lowest_risk(non_skip_df: pd.DataFrame) -> pd.Series | None:
    low_risk_df = non_skip_df[non_skip_df["RiskLevel"] == "低"]
    if low_risk_df.empty:
        return None
    return low_risk_df.sort_values(by=["Rank"]).iloc[0]


def render_decision_angles(ranked_df: pd.DataFrame) -> None:
    """判断の切り口（利益重視・早く入りたい・リスク回避）の3カードを表示する。"""
    if ranked_df is None or ranked_df.empty:
        return

    non_skip_df = ranked_df[ranked_df["Action"] != SKIP_ACTION]

    with st.container(border=True):
        st.markdown('<div class="ds-card-title">💡 どう判断する？</div><br/>', unsafe_allow_html=True)

        best_return_row = _pick_best_return(non_skip_df)
        fastest_entry_row = _pick_fastest_entry(non_skip_df)
        lowest_risk_row = _pick_lowest_risk(non_skip_df)

        cards = []

        if best_return_row is not None:
            cards.append(
                '<div class="ds-angle-card ds-angle-green">'
                '<div class="ds-angle-title">🏆 利益重視</div>'
                f'<div class="ds-angle-action">{_action_label(best_return_row)} が第一候補</div>'
                '<div class="ds-angle-desc">最も平均リターンが高い選択肢です。</div></div>'
            )

        if fastest_entry_row is not None:
            risk_note = (
                "下振れリスク（最大損失）に注意してください。"
                if fastest_entry_row["RiskLevel"] in ("中", "高")
                else "リスクも比較的抑えられています。"
            )
            cards.append(
                '<div class="ds-angle-card ds-angle-blue">'
                '<div class="ds-angle-title">🕐 早く入りたい</div>'
                f'<div class="ds-angle-action">{_action_label(fastest_entry_row)} も候補</div>'
                f'<div class="ds-angle-desc">{risk_note}</div></div>'
            )

        if lowest_risk_row is not None:
            cards.append(
                '<div class="ds-angle-card ds-angle-purple">'
                '<div class="ds-angle-title">🛡️ リスク回避</div>'
                f'<div class="ds-angle-action">{_action_label(lowest_risk_row)} を優先</div>'
                '<div class="ds-angle-desc">安定重視なら、リスクが低い選択肢や見送りを。</div></div>'
            )

        if cards:
            st.markdown(f'<div class="ds-angle-row">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_disclaimer_footer(
    recommended_row: pd.Series | None,
    single_stock_result: dict | None,
    peer_result: dict | None,
) -> None:
    """統計検証の結果が推奨ラベルの信頼度を保証するものではない旨の総括注意書きを表示する。"""
    if recommended_row is None:
        return

    label = _action_label(recommended_row)

    single_stock_avg_return = single_stock_result.get("avg_return") if single_stock_result else None
    single_stock_p_value = single_stock_result.get("p_value") if single_stock_result else None
    single_stock_p_value_is_reference = (
        single_stock_result.get("p_value_is_reference", False) if single_stock_result else False
    )
    single_stock_insufficient_sample = (
        single_stock_result.get("insufficient_sample", True) if single_stock_result else True
    )
    peer_avg_return = peer_result.get("avg_return") if peer_result else None

    # apply_significance_capと同じ判定基準（p_value_is_referenceなら0.10、通常は0.05）で
    # 注意書きの文言を出し分ける。サンプル不足の場合はp値自体が無いため専用の注意書きにする。
    direction_ok = (
        single_stock_avg_return is not None
        and peer_avg_return is not None
        and ((single_stock_avg_return > 0 and peer_avg_return > 0) or (single_stock_avg_return < 0 and peer_avg_return < 0))
    )
    p_value_threshold = (
        SIGNIFICANCE_PVALUE_REFERENCE_THRESHOLD if single_stock_p_value_is_reference else SIGNIFICANCE_PVALUE_THRESHOLD
    )
    p_value_ok = single_stock_p_value is not None and single_stock_p_value < p_value_threshold

    if single_stock_insufficient_sample:
        note = "サンプル不足のため統計的有意性は未確認です。将来の値動きを保証するものではありません。"
    elif direction_ok and p_value_ok:
        note = "統計検証でも値動きの方向に一定の再現性が確認されていますが、将来の値動きを保証するものではありません。"
    else:
        note = "統計検証はまだ強い優位性を示す段階ではありません。実運用では他の指標と併用してください。"

    st.markdown(
        f'<div class="ds-footer">⭐ 今回のおすすめは「{label}」です。{note}<br/><br/>'
        "📊 このおすすめ行動は、複数の投資行動パターンを比較し、その中で最も成績が良かったものを"
        "選んでいます。比較する候補が多いほど、実際の実力より良い結果に見えやすくなる統計的な性質が"
        "あるため、参考情報の一つとしてご覧ください。</div>",
        unsafe_allow_html=True,
    )