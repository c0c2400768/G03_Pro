"""岩間担当：デモトレード結果詳細画面（pages/6_demo_trading_results.py）"""

import html

import plotly.graph_objects as go
import streamlit as st

from logic.decision_rating import (
    RATING_CONSIDERABLE,
    RATING_NOT_RECOMMENDED,
    RATING_RECOMMENDED,
    add_action_ratings_without_validation,
    rank_rated_actions,
)
from logic.demo_trade import calc_demo_trade, HOLDING_ACTIONS, NEW_ACTIONS, ACTION_LABELS, latest_close_price
from logic.error_utils import show_error, show_warning
from logic.indicators import calc_hv
from pages._decision_support_view import inject_styles, render_unrealized_pl_card

COLUMN_LABELS = {
    "ActionLabel": "投資行動", "Horizon": "経過日数(営業日)", "AvgReturn": "平均リターン",
    "WinRate": "勝率", "MaxLoss": "最大損失", "MaxDrawdown": "最大含み損率", "AvgHoldDays": "平均保有日数",
}

# 結果サマリーの各タイルに添えるiマークのツールチップ文言（title属性で表示）。
# 初心者が意味を誤解しやすい指標の補足説明であり、値そのものの算出ロジックには影響しない。
_SUMMARY_TILE_TOOLTIPS = {
    "📈 平均リターン（全行動平均）": (
        "選択した経過日数で、各投資行動を取った場合のリターン（値上がり・値下がり率）の平均を、"
        "さらに全行動で平均した値です。プラスなら値上がり、マイナスなら値下がりを意味します。"
    ),
    "🎯 平均勝率（全行動平均）": (
        "過去の類似局面のうち、リターンがプラスになった割合（勝率）を全行動で平均した値です。"
        "100%に近いほど、過去は当たりやすかったことを示します。"
    ),
    "📉 平均最大損失（全行動平均）": (
        "各投資行動のうち最も損失が大きかったケースのリターンを、全行動で平均した値です。"
        "実際に起こりうる下振れの目安として参考にしてください。"
    ),
    "📅 平均保有日数（全行動平均）": (
        "類似局面の発生から実際に売買が完了するまでの平均保有日数を、全行動で平均した値です。"
    ),
    "📄 検証件数（全行動平均）": (
        "各投資行動の結果算出に使われた過去の類似局面の件数（サンプル数）を、全行動で平均した値です。"
        "件数が少ないほど結果の信頼度は下がります。"
    ),
}

# 「グラフで比較」のバー色分け（Rating別）。緑=推奨、黄=検討可、グレー=非推奨。
# pages/_decision_support_view.pyのds-pill-rating-*と背景色の透明度の考え方は揃えつつ、
# 「検討可」はds-pill-rating-considerableの青ではなく黄系（同ファイルds-pill-risk-中や
# dt-summary-amberで使っているamber系の色）に合わせている（依頼文の「検討可=黄系」指定を
# 優先し、色そのものはこのファイル内の既存amber色と統一）。カードの背景に使う低い不透明度
# （0.18等）だとバー塗りとしては薄すぎるため、バー用にやや高い不透明度にしている。
_RATING_BAR_COLORS = {
    RATING_RECOMMENDED: "rgba(34,197,94,0.75)",
    RATING_CONSIDERABLE: "rgba(245,158,11,0.80)",
    RATING_NOT_RECOMMENDED: "rgba(128,128,128,0.55)",
}
_DEFAULT_BAR_COLOR = "rgba(128,128,128,0.55)"


def _fixed_return_axis_range(values, base: float = 0.10, padding: float = 1.15) -> list[float]:
    """0を含む固定レンジ（既定±10%）を返す。実データがレンジを超える場合はデータに合わせて拡張する。

    ±10%を基準にしたのは、この画面が扱うAvgReturn/MaxLossが概ね数%〜十数%程度の範囲に
    収まることが多いため（厳密な統計的根拠があるわけではなく、実データを踏まえた妥当な
    目安として設定。要調整の場合はbase引数を差し替え可）。
    """
    data_min = float(values.min())
    data_max = float(values.max())
    lo = min(-base, data_min * padding) if data_min < 0 else -base
    hi = max(base, data_max * padding) if data_max > 0 else base
    return [lo, hi]


def _summary_tile_label_html(label: str) -> str:
    tooltip = _SUMMARY_TILE_TOOLTIPS.get(label)
    if tooltip is None:
        return f'<div class="dt-summary-tile-label">{label}</div>'
    return (
        f'<div class="dt-summary-tile-label">{label} '
        f'<span class="dt-info" title="{html.escape(tooltip)}">ℹ️</span></div>'
    )

_STYLE = """
<style>
/* margin-bottom:16pxは、st.markdownのラッパー要素(stMarkdownContainer)がst側で
   margin-bottom:-16pxを持つため、その分を打ち消すためのもの（打ち消さないとタイル背景の
   下端が次のセクションと重なる）。 */
.dt-summary-row { display:flex; gap:16px; margin-bottom:16px; }
.dt-summary-tile { flex:1; border-radius:12px; padding:16px; text-align:center; }
.dt-summary-tile-label { font-size:12px; color:var(--text-color); margin-bottom:6px; }
.dt-summary-tile-value { font-size:22px; font-weight:700; }
.dt-summary-green { background:rgba(34,197,94,0.18); }
.dt-summary-green .dt-summary-tile-value { color:#16a34a; }
.dt-summary-blue { background:rgba(59,130,246,0.18); }
.dt-summary-blue .dt-summary-tile-value { color:#2563eb; }
.dt-summary-red { background:rgba(239,68,68,0.18); }
.dt-summary-red .dt-summary-tile-value { color:#dc2626; }
.dt-summary-amber { background:rgba(245,158,11,0.20); }
.dt-summary-amber .dt-summary-tile-value { color:#b45309; }
.dt-summary-purple { background:rgba(168,85,247,0.18); }
.dt-summary-purple .dt-summary-tile-value { color:#7c3aed; }
.dt-info { cursor:help; color:#9ca3af; font-size:11px; margin-left:2px; }
</style>
"""

st.title("⑥シミュレーション結果")
st.caption("過去の類似相場をもとに、各投資行動を取った場合の成績を比較します。")
st.markdown(_STYLE, unsafe_allow_html=True)
inject_styles()  # render_unrealized_pl_card（pages/_decision_support_view.py）が使うds-*クラス用

price_df = st.session_state.get("stock_price_df")
similar_entry = st.session_state.get("iwama_similar_periods_df")
similar_df = similar_entry.get("data") if isinstance(similar_entry, dict) else None

if price_df is None or price_df.empty:
    show_warning("株価データがありません。①銘柄・分析条件の設定画面で銘柄を選択してください。")
    st.stop()
if similar_df is None or similar_df.empty:
    show_warning("類似局面が未計算です。先に⑤似た相場を探す画面を開いてください。")
    st.stop()

# 銘柄・期間・立場を変更した後、⑤を経由せず直接この画面を開いた場合、以前の分析条件の
# 類似局面がそのまま表示されてしまう（stale表示）ため、生成時点の分析条件タグと
# 現在の分析条件タグを照合する。
if similar_entry.get("tag") != st.session_state.get("analysis_condition_tag"):
    show_warning("分析条件（銘柄・期間・立場等）が変更されています。⑤似た相場を探す画面を開いて再実行してください。")
    st.stop()

stance = st.session_state.get("investment_stance")
if not stance:
    show_warning("立場が選択されていません。①銘柄・分析条件の設定画面で選択してください。")
    st.stop()
st.badge(f"立場：{stance}", icon="🕒", color="blue")

if stance == "すでに保有している":
    purchase_price = st.session_state.get("purchase_price")
    if purchase_price is not None:
        render_unrealized_pl_card(purchase_price, latest_close_price(price_df))

actions = HOLDING_ACTIONS if stance == "すでに保有している" else NEW_ACTIONS

buy_date = st.session_state.get("purchase_date")
result_df = calc_demo_trade(similar_df, price_df, actions, [5, 10, 20], buy_date=buy_date)
# 補助判断画面へ受け渡し用（空でも上書きする）。⑤と同様、分析条件タグと一緒に保存し、
# ⑦側でstale表示を防止できるようにする。
st.session_state["demo_trade_result_df"] = {
    "tag": st.session_state.get("analysis_condition_tag"),
    "data": result_df,
}

if result_df.empty:
    show_error("有効な取引結果がありませんでした。類似局面や条件を見直してください。")
    st.stop()

horizon_choice = st.selectbox("比較する経過日数", [5, 10, 20], index=1)
# sellは今日時点の確定値1つのみで、他の行動のような予測分布を持たず比較する意味が
# ないため、この画面の結果テーブル・グラフからは除外する（含み損益はrender_unrealized_pl_card
# で別カード表示済み）。sellはHorizon=NoneのためHorizon一致条件だけで自然に除外される。
horizon_result_df = result_df[result_df["Horizon"] == horizon_choice]

if horizon_result_df.empty:
    show_warning(
        f"経過日数{horizon_choice}営業日の結果が計算できませんでした。"
        "類似局面の件数が少ない、または類似局面の日付が分析期間の終盤に集中している"
        "（その先の営業日データが無い）可能性があります。"
        "⑤似た相場を探す画面で許容幅を広げるか、比較する経過日数を変更してください。"
    )
    st.stop()

st.subheader("結果サマリー")
_summary_tiles = [
    ("dt-summary-green", "📈 平均リターン（全行動平均）", f'{horizon_result_df["AvgReturn"].mean():+.2%}'),
    ("dt-summary-blue", "🎯 平均勝率（全行動平均）", f'{horizon_result_df["WinRate"].mean():.1%}'),
    ("dt-summary-red", "📉 平均最大損失（全行動平均）", f'{horizon_result_df["MaxLoss"].mean():+.1%}'),
    ("dt-summary-amber", "📅 平均保有日数（全行動平均）", f'{horizon_result_df["AvgHoldDays"].mean():.1f}日'),
    ("dt-summary-purple", "📄 検証件数（全行動平均）", f'{horizon_result_df["SampleSize"].mean():.0f}件'),
]
_summary_tiles_html = "".join(
    f'<div class="dt-summary-tile {css_class}">'
    + _summary_tile_label_html(label)
    + f'<div class="dt-summary-tile-value">{value}</div></div>'
    for css_class, label, value in _summary_tiles
)
st.markdown(f'<div class="dt-summary-row">{_summary_tiles_html}</div>', unsafe_allow_html=True)

st.subheader("詳細データ")
display_df = horizon_result_df.copy()
display_df["ActionLabel"] = display_df["Action"].map(ACTION_LABELS)
# horizon_result_dfはsell（Horizon=None）を含まないため、常に数値として整形できる。
# 数値と文字列が混在する列だとpyarrowのArrow変換で型推定に失敗するため、文字列に揃える
# （他は従来通りの数値表記のまま、単位等は付けない）
display_df["Horizon"] = display_df["Horizon"].astype(int).astype(str)
display_df = display_df[["ActionLabel", "Horizon", "AvgReturn", "WinRate", "MaxLoss", "MaxDrawdown", "AvgHoldDays"]]
display_df = display_df.rename(columns=COLUMN_LABELS)
display_df["平均リターン"] = display_df["平均リターン"].map(lambda x: f"{x:+.2%}")
display_df["勝率"] = display_df["勝率"].map(lambda x: f"{x:.1%}")
display_df["最大損失"] = display_df["最大損失"].map(lambda x: f"{x:+.2%}")
display_df["最大含み損率"] = display_df["最大含み損率"].map(lambda x: f"{x:+.2%}")
display_df["平均保有日数"] = display_df["平均保有日数"].map(lambda x: f"{x:.1f}日")

st.dataframe(display_df, use_container_width=True, hide_index=True)
st.caption(f"{len(horizon_result_df)}パターンの結果を表示しています。")

st.divider()
st.subheader("グラフで比較")

# バーの並び順・色分けをRating（推奨/検討可/非推奨）に揃える。この画面は⑦投資判断サポートの
# ようなwalk-forward検証（統計的有意性チェック）を行わないため、検証データを使わない簡易判定
# （add_action_ratings_without_validation）で代用する。そのため、ここでのRatingは⑦の
# 最終的な判定（統計的安全装置を全て適用した後の値）と異なる場合がある。
hv_series = calc_hv(price_df)["HV"].dropna()
latest_hv = float(hv_series.iloc[-1]) if not hv_series.empty else None

rated_chart_df = add_action_ratings_without_validation(horizon_result_df, latest_hv)
ranked_chart_df = rank_rated_actions(rated_chart_df)
ranked_chart_df["ActionLabel"] = ranked_chart_df["Action"].map(ACTION_LABELS)
bar_colors = [_RATING_BAR_COLORS.get(r, _DEFAULT_BAR_COLOR) for r in ranked_chart_df["Rating"]]

st.caption(
    "🟢推奨　🟡検討可　⚪非推奨（この画面独自の簡易判定です。⑦投資判断サポートの統計検証を"
    "反映した最終判定とは異なる場合があります）"
)

_CHART_METRICS = [
    ("AvgReturn", "平均リターン", lambda x: f"{x:+.2%}", _fixed_return_axis_range(ranked_chart_df["AvgReturn"])),
    ("WinRate", "勝率", lambda x: f"{x:.1%}", [0.0, 1.0]),
    ("MaxLoss", "最大損失", lambda x: f"{x:+.2%}", _fixed_return_axis_range(ranked_chart_df["MaxLoss"])),
    ("MaxDrawdown", "最大含み損率", lambda x: f"{x:+.2%}", None),
    ("AvgHoldDays", "平均保有日数", lambda x: f"{x:.1f}日", None),
]

for col, label, fmt, axis_range in _CHART_METRICS:
    st.caption(label)
    values = ranked_chart_df[col]
    fig = go.Figure(data=[go.Bar(
        x=ranked_chart_df["ActionLabel"],
        y=values,
        text=[fmt(v) for v in values],
        textposition="outside",
        cliponaxis=False,
        marker_color=bar_colors,
    )])
    # 画面幅いっぱいに広げず固定幅にすることで、行動数が少なくてもバー幅・間隔が
    # 間延びしないようにする（bargapでバー間隔を一定に保つ）。
    fig.update_layout(height=340, width=700, bargap=0.35, margin=dict(t=30, b=10, l=10, r=10))
    if axis_range is not None:
        fig.update_yaxes(range=axis_range)
    st.plotly_chart(fig, use_container_width=False)