"""岩間担当：デモトレード結果詳細画面（pages/6_demo_trading_results.py）"""

import streamlit as st

from logic.demo_trade import calc_demo_trade, HOLDING_ACTIONS, NEW_ACTIONS, ACTION_LABELS, SELL_ACTION
from logic.error_utils import show_error, show_warning

COLUMN_LABELS = {
    "ActionLabel": "投資行動", "Horizon": "経過日数(営業日)", "AvgReturn": "平均リターン",
    "WinRate": "勝率", "MaxLoss": "最大損失", "MaxDrawdown": "最大ドローダウン", "AvgHoldDays": "平均保有日数",
}

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
</style>
"""

st.title("デモトレード結果")
st.markdown(_STYLE, unsafe_allow_html=True)

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

actions = HOLDING_ACTIONS if stance == "すでに保有している" else NEW_ACTIONS

buy_date = st.session_state.get("purchase_date")
result_df = calc_demo_trade(similar_df, price_df, actions, [5, 10, 20], buy_date=buy_date)
st.session_state["demo_trade_result_df"] = result_df  # 補助判断画面へ受け渡し用（空でも上書きする）

if result_df.empty:
    show_error("有効な取引結果がありませんでした。類似局面や条件を見直してください。")
    st.stop()

horizon_choice = st.selectbox("比較する経過日数", [5, 10, 20], index=1)
# sellはhorizon概念が無く常に1行のみ存在するため、選択中のhorizonに関わらず表示対象に含める
horizon_result_df = result_df[(result_df["Horizon"] == horizon_choice) | (result_df["Action"] == SELL_ACTION)]

st.subheader("結果サマリー")
st.markdown(
    '<div class="dt-summary-row">'
    '<div class="dt-summary-tile dt-summary-green">'
    '<div class="dt-summary-tile-label">📈 平均リターン（全行動平均）</div>'
    f'<div class="dt-summary-tile-value">{horizon_result_df["AvgReturn"].mean():+.2%}</div></div>'
    '<div class="dt-summary-tile dt-summary-blue">'
    '<div class="dt-summary-tile-label">🎯 平均勝率（全行動平均）</div>'
    f'<div class="dt-summary-tile-value">{horizon_result_df["WinRate"].mean():.1%}</div></div>'
    '<div class="dt-summary-tile dt-summary-red">'
    '<div class="dt-summary-tile-label">📉 平均最大損失（全行動平均）</div>'
    f'<div class="dt-summary-tile-value">{horizon_result_df["MaxLoss"].mean():+.1%}</div></div>'
    '<div class="dt-summary-tile dt-summary-amber">'
    '<div class="dt-summary-tile-label">📅 平均保有日数（全行動平均）</div>'
    f'<div class="dt-summary-tile-value">{horizon_result_df["AvgHoldDays"].mean():.1f}日</div></div>'
    '<div class="dt-summary-tile dt-summary-purple">'
    '<div class="dt-summary-tile-label">📄 検証件数（全行動平均）</div>'
    f'<div class="dt-summary-tile-value">{horizon_result_df["SampleSize"].mean():.0f}件</div></div>'
    "</div>",
    unsafe_allow_html=True,
)

st.subheader("詳細データ")
display_df = horizon_result_df.copy()
display_df["ActionLabel"] = display_df["Action"].map(ACTION_LABELS)
# sellはhorizon概念が無くHorizonがNaNになるため、「―」で表示する。
# 数値と文字列が混在する列だとpyarrowのArrow変換で型推定に失敗するため、他の行も
# 文字列に揃える（他は従来通りの数値表記のまま、単位等は付けない）
display_df["Horizon"] = display_df.apply(
    lambda r: "―" if r["Action"] == SELL_ACTION else str(int(r["Horizon"])), axis=1
)
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