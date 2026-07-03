"""岩間担当：デモトレード結果詳細画面（pages/6_demo_trading_results.py）"""

import streamlit as st

from logic.demo_trade import calc_demo_trade
from logic.error_utils import show_error, show_warning

st.title("デモトレード結果")

price_df = st.session_state.get("data_stock_price_df")
similar_df = st.session_state.get("iwama_similar_periods_df")

if price_df is None or price_df.empty:
    show_warning("株価データがありません。トップ画面で銘柄を選択してください。")
    st.stop()

if similar_df is None or similar_df.empty:
    show_warning("類似局面が未計算です。先に「過去類似局面」画面を開いてください。")
    st.stop()

st.subheader("シミュレーション条件")

col1, col2 = st.columns(2)
with col1:
    do_buy = st.checkbox("買い（ロング）", value=True)
    do_sell = st.checkbox("空売り（ショート）", value=False)
with col2:
    horizons = st.multiselect("保有日数", [5, 10, 20, 40], default=[5, 10, 20])

actions = []
if do_buy:
    actions.append("buy")
if do_sell:
    actions.append("sell")

if not actions:
    show_warning("投資行動を1つ以上選択してください。")
    st.stop()
if not horizons:
    show_warning("保有日数を1つ以上選択してください。")
    st.stop()

result_df = calc_demo_trade(similar_df, price_df, actions, horizons)

st.subheader("結果")
if result_df.empty:
    show_error("有効な取引結果がありませんでした。類似局面や条件を見直してください。")
else:
    st.dataframe(result_df, use_container_width=True)
    st.caption(f"{len(result_df)}パターンの結果を表示しています。")