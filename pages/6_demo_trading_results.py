"""岩間担当：デモトレード結果詳細画面（pages/6_demo_trading_results.py）"""

import streamlit as st

from logic.demo_trade import calc_demo_trade, HOLDING_ACTIONS, NEW_ACTIONS, ACTION_LABELS
from logic.error_utils import show_error, show_warning

COLUMN_LABELS = {
    "ActionLabel": "投資行動", "Horizon": "経過日数(営業日)", "AvgReturn": "平均リターン",
    "WinRate": "勝率", "MaxLoss": "最大損失", "MaxDrawdown": "最大ドローダウン", "AvgHoldDays": "平均保有日数",
}

st.title("デモトレード結果")

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
st.caption(f"立場：{stance}")

actions = HOLDING_ACTIONS if stance == "すでに保有している" else NEW_ACTIONS

buy_date = st.session_state.get("purchase_date")
result_df = calc_demo_trade(similar_df, price_df, actions, [5, 10, 20], buy_date=buy_date)
st.session_state["demo_trade_result_df"] = result_df  # 補助判断画面へ受け渡し用（空でも上書きする）

st.subheader("結果一覧")
if result_df.empty:
    show_error("有効な取引結果がありませんでした。類似局面や条件を見直してください。")
    st.stop()

display_df = result_df.copy()
display_df["ActionLabel"] = display_df["Action"].map(ACTION_LABELS)
display_df = display_df[["ActionLabel", "Horizon", "AvgReturn", "WinRate", "MaxLoss", "MaxDrawdown", "AvgHoldDays"]]
display_df = display_df.rename(columns=COLUMN_LABELS)
display_df["平均リターン"] = display_df["平均リターン"].map(lambda x: f"{x:+.2%}")
display_df["勝率"] = display_df["勝率"].map(lambda x: f"{x:.1%}")
display_df["最大損失"] = display_df["最大損失"].map(lambda x: f"{x:+.2%}")
display_df["最大ドローダウン"] = display_df["最大ドローダウン"].map(lambda x: f"{x:+.2%}")
display_df["平均保有日数"] = display_df["平均保有日数"].map(lambda x: f"{x:.1f}日")

st.dataframe(display_df, use_container_width=True, hide_index=True)
st.caption(f"{len(result_df)}パターンの結果を表示しています。")

st.divider()
st.subheader("グラフで比較")
horizon_choice = st.selectbox("比較する経過日数", [5, 10, 20], index=1)

chart_source = result_df[result_df["Horizon"] == horizon_choice].copy()
chart_source["投資行動"] = chart_source["Action"].map(ACTION_LABELS)
chart_source = chart_source.set_index("投資行動")

for col, label in [("AvgReturn", "平均リターン"), ("WinRate", "勝率"),
                    ("MaxLoss", "最大損失"), ("MaxDrawdown", "最大ドローダウン"),
                    ("AvgHoldDays", "平均保有日数")]:
    st.caption(label)
    st.bar_chart(chart_source[[col]].rename(columns={col: label}))