"""岩間担当：デモトレード結果詳細画面（pages/6_demo_trading_results.py）"""

import html

import streamlit as st

from logic.demo_trade import calc_demo_trade, HOLDING_ACTIONS, NEW_ACTIONS, ACTION_LABELS, latest_close_price
from logic.error_utils import show_error, show_warning
from pages._decision_support_view import inject_styles, render_unrealized_pl_card

COLUMN_LABELS = {
    "ActionLabel": "投資行動", "Horizon": "経過日数(営業日)", "AvgReturn": "平均リターン",
    "WinRate": "勝率", "MaxLoss": "最大損失", "MaxDrawdown": "最大ドローダウン", "AvgHoldDays": "平均保有日数",
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
.dt-summary-tile-label { font-size:12px; color:#4b5563; margin-bottom:6px; }
.dt-summary-tile-value { font-size:22px; font-weight:700; }
.dt-summary-green { background:#eafaf1; }
.dt-summary-green .dt-summary-tile-value { color:#166534; }
.dt-summary-blue { background:#eaf2fb; }
.dt-summary-blue .dt-summary-tile-value { color:#1d4ed8; }
.dt-summary-red { background:#fdeaea; }
.dt-summary-red .dt-summary-tile-value { color:#b91c1c; }
.dt-summary-amber { background:#fff8e1; }
.dt-summary-amber .dt-summary-tile-value { color:#92400e; }
.dt-summary-purple { background:#f5f0fb; }
.dt-summary-purple .dt-summary-tile-value { color:#6d28d9; }
.dt-info { cursor:help; color:#9ca3af; font-size:11px; margin-left:2px; }
</style>
"""

st.title("デモトレード結果")
st.markdown(_STYLE, unsafe_allow_html=True)
inject_styles()  # render_unrealized_pl_card（pages/_decision_support_view.py）が使うds-*クラス用

price_df = st.session_state.get("stock_price_df")
similar_df = st.session_state.get("iwama_similar_periods_df")

if price_df is None or price_df.empty:
    show_warning("株価データがありません。トップ画面で銘柄を選択してください。")
    st.stop()
if similar_df is None or similar_df.empty:
    show_warning("類似局面が未計算です。先に「過去類似局面」画面を開いてください。")
    st.stop()

stance = st.session_state.get("investment_stance")
if not stance:
    show_warning("立場が選択されていません。トップ画面で選択してください。")
    st.stop()
st.badge(f"立場：{stance}", icon="🕒", color="blue")

if stance == "すでに保有している":
    purchase_price = st.session_state.get("purchase_price")
    if purchase_price is not None:
        render_unrealized_pl_card(purchase_price, latest_close_price(price_df))

actions = HOLDING_ACTIONS if stance == "すでに保有している" else NEW_ACTIONS

buy_date = st.session_state.get("purchase_date")
result_df = calc_demo_trade(similar_df, price_df, actions, [5, 10, 20], buy_date=buy_date)
st.session_state["demo_trade_result_df"] = result_df  # 補助判断画面へ受け渡し用（空でも上書きする）

if result_df.empty:
    show_error("有効な取引結果がありませんでした。類似局面や条件を見直してください。")
    st.stop()

horizon_choice = st.selectbox("比較する経過日数", [5, 10, 20], index=1)
# sellは今日時点の確定値1つのみで、他の行動のような予測分布を持たず比較する意味が
# ないため、この画面の結果テーブル・グラフからは除外する（含み損益はrender_unrealized_pl_card
# で別カード表示済み）。sellはHorizon=NoneのためHorizon一致条件だけで自然に除外される。
horizon_result_df = result_df[result_df["Horizon"] == horizon_choice]

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
display_df["最大ドローダウン"] = display_df["最大ドローダウン"].map(lambda x: f"{x:+.2%}")
display_df["平均保有日数"] = display_df["平均保有日数"].map(lambda x: f"{x:.1f}日")

st.dataframe(display_df, use_container_width=True, hide_index=True)
st.caption(f"{len(horizon_result_df)}パターンの結果を表示しています。")

st.divider()
st.subheader("グラフで比較")

chart_source = horizon_result_df.copy()
chart_source["投資行動"] = chart_source["Action"].map(ACTION_LABELS)
chart_source = chart_source.set_index("投資行動")

for col, label in [("AvgReturn", "平均リターン"), ("WinRate", "勝率"),
                    ("MaxLoss", "最大損失"), ("MaxDrawdown", "最大ドローダウン"),
                    ("AvgHoldDays", "平均保有日数")]:
    st.caption(label)
    st.bar_chart(chart_source[[col]].rename(columns={col: label}))