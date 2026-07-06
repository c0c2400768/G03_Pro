"""相川担当：補助判断ページの上部（結論カード・比較表・判断の切り口）表示ロジック
（pages/_decision_support_view.py）。

ファイル名を`_`始まりにしているため、Streamlitのナビゲーション（app.pyのst.navigation）には
現れない（app.pyがpages/配下を明示的にst.Pageで列挙する構成のため、そもそも対象にもならない）。
7_decision_support.pyの既存の描画部分から分離した関数として実装しており、
将来的に別ページへ移動する場合はこのモジュールをそのまま呼び出し元だけ差し替えればよい。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from logic.decision_rating import (
    RATING_CONSIDERABLE,
    RATING_NOT_RECOMMENDED,
    RATING_RECOMMENDED,
    SKIP_ACTION,
)
from logic.demo_trade import ACTION_LABELS
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

.ds-pill { padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; white-space:nowrap; }
.ds-pill-risk-低 { background:#dcfce7; color:#15803d; }
.ds-pill-risk-中 { background:#fef3c7; color:#92400e; }
.ds-pill-risk-高 { background:#fee2e2; color:#b91c1c; }
.ds-pill-risk-なし { background:#f3f4f6; color:#6b7280; }
.ds-pill-rating-recommended { background:#dcfce7; color:#15803d; }
.ds-pill-rating-considerable { background:#dbeafe; color:#1d4ed8; }
.ds-pill-rating-not_recommended { background:#f3f4f6; color:#6b7280; }

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
</style>
"""

_RATING_PILL_CLASS = {
    RATING_RECOMMENDED: "ds-pill-rating-recommended",
    RATING_CONSIDERABLE: "ds-pill-rating-considerable",
    RATING_NOT_RECOMMENDED: "ds-pill-rating-not_recommended",
}

_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def inject_styles() -> None:
    """このモジュール・_validation_view.pyで共通利用するカードデザインのCSSを注入する。"""
    st.markdown(_STYLE, unsafe_allow_html=True)


def _action_label(row: pd.Series) -> str:
    label = ACTION_LABELS.get(row["Action"], row["Action"])
    if row["Action"] == SKIP_ACTION:
        return label
    return f"{label}（{int(row['Horizon'])}営業日）"


def _return_html(avg_return: float) -> str:
    css_class = "ds-return-pos" if avg_return > 0 else "ds-return-neg"
    return f'<span class="{css_class}">{avg_return:+.2%}</span>'


def _winrate_html(win_rate: float) -> str:
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


def render_conclusion_card(recommended_row: pd.Series | None, ranked_df: pd.DataFrame, stance: str) -> None:
    """結論カード（おすすめ行動・平均リターン・勝率・参考:最良結果）を表示する。"""
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
        for _, row in ranked_df.iterrows():
            rank = int(row["Rank"])
            rank_label = f'{_MEDALS.get(rank, "")} {rank}位'.strip()
            rows_html.append(
                "<tr>"
                f"<td>{rank_label}</td>"
                f"<td>{_action_label(row)}</td>"
                f"<td>{_return_html(row['AvgReturn'])}</td>"
                f"<td>{_winrate_html(row['WinRate'])}</td>"
                f"<td>{_risk_pill_html(row['RiskLevel'])}</td>"
                f"<td>{_rating_pill_html(row['Rating'])}</td>"
                "</tr>"
            )

        table_html = (
            '<table class="ds-table"><thead><tr>'
            "<th>順位</th><th>投資行動</th><th>平均リターン</th><th>勝率</th><th>リスク</th><th>評価</th>"
            "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)


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

    single_stock_hit_rate = single_stock_result.get("hit_rate") if single_stock_result else None
    single_stock_avg_return = single_stock_result.get("avg_return") if single_stock_result else None
    single_stock_insufficient_sample = (
        single_stock_result.get("insufficient_sample", True) if single_stock_result else True
    )
    peer_avg_return = peer_result.get("avg_return") if peer_result else None

    hit_rate_ok = (
        not single_stock_insufficient_sample
        and single_stock_hit_rate is not None
        and single_stock_hit_rate > 0.5
    )
    direction_ok = (
        single_stock_avg_return is not None
        and peer_avg_return is not None
        and ((single_stock_avg_return > 0 and peer_avg_return > 0) or (single_stock_avg_return < 0 and peer_avg_return < 0))
    )

    if hit_rate_ok and direction_ok:
        note = "統計検証でも的中率・値動きの方向に一定の再現性が確認されていますが、将来の値動きを保証するものではありません。"
    else:
        note = "統計検証はまだ強い優位性を示す段階ではありません。実運用では他の指標と併用してください。"

    st.markdown(
        f'<div class="ds-footer">⭐ 今回のおすすめは「{label}」です。{note}</div>',
        unsafe_allow_html=True,
    )