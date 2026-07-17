"""山﨑担当：サマリー画面（pages/2_summary.py）。

役割：他担当のlogic関数（太刀岡：データ取得、及川：指標計算）を呼び出し、
要約情報を表示する。山﨑担当は固有ロジックを持たないため。
"""

import streamlit as st
import plotly.graph_objects as go

from logic.indicators import calc_rsi, calc_bollinger, calc_bb_position, calc_hv, calc_volume_ratio
from logic.error_utils import show_warning
from logic.ticker_lookup import get_company_name


st.title("②株価・指標サマリー")
st.caption("取得した銘柄の直近の値動きと主要指標を、ひと目で確認できます。")

stock_df = st.session_state.get("stock_price_df")
ticker = st.session_state.get("selected_ticker")

if stock_df is None or stock_df.empty:
    show_warning("データが取得されていません。①銘柄・分析条件の設定画面で銘柄を選択してください。")
    st.stop()

latest = stock_df.iloc[-1]
prev = stock_df.iloc[-2] if len(stock_df) >= 2 else None

st.subheader(f"{get_company_name(ticker)} の概況")

col1, col2, col3 = st.columns(3)
col1.metric("最新終値", f"{latest['Close']:,.1f}")
if prev is not None:
    change = latest["Close"] - prev["Close"]
    change_pct = change / prev["Close"] * 100
    col2.metric("前日比", f"{change:+.1f}", f"{change_pct:+.2f}%")
else:
    col2.metric("前日比", "データ不足")
col3.metric("データ件数", f"{len(stock_df)} 営業日")

st.divider()
st.subheader("主要指標（直近値）")

rsi_df = calc_rsi(stock_df)
bb_df = calc_bollinger(stock_df)
bb_pos_df = calc_bb_position(stock_df, bb_df)
hv_df = calc_hv(stock_df)
vol_df = calc_volume_ratio(stock_df)

latest_rsi = rsi_df["RSI"].dropna().iloc[-1] if not rsi_df["RSI"].dropna().empty else None
latest_bb_pos = bb_pos_df["BBPosition"].dropna().iloc[-1] if not bb_pos_df["BBPosition"].dropna().empty else None
latest_hv = hv_df["HV"].dropna().iloc[-1] if not hv_df["HV"].dropna().empty else None
latest_vol = vol_df["VolumeRatio"].dropna().iloc[-1] if not vol_df["VolumeRatio"].dropna().empty else None

col4, col5, col6, col7 = st.columns(4)
col4.metric("RSI", f"{latest_rsi:.1f}" if latest_rsi is not None else "算出不可")
col5.metric("BB位置", latest_bb_pos or "算出不可")
col6.metric("HV", f"{latest_hv:.1f}%" if latest_hv is not None else "算出不可")
col7.metric("出来高倍率", f"{latest_vol:.2f}" if latest_vol is not None else "算出不可")

if latest_rsi is None:
    show_warning("直近の指標が算出できていません（データ期間が短い可能性があります）。")

st.divider()
st.subheader("直近の値動き")

fig = go.Figure(data=[
    go.Scatter(x=stock_df["Date"], y=stock_df["Close"], mode="lines", name="終値")
])

stance = st.session_state.get("investment_stance")
purchase_date = st.session_state.get("purchase_date")
if stance == "すでに保有している" and purchase_date:
    if stock_df["Date"].min() <= purchase_date <= stock_df["Date"].max():
        fig.add_vline(
            x=purchase_date,
            line_dash="dash",
            line_color="gray",
            annotation_text="購入日",
            annotation_position="top",
        )

fig.update_layout(xaxis_title="日付", yaxis_title="価格", height=350)
st.plotly_chart(fig, use_container_width=True)