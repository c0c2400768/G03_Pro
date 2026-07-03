"""山﨑担当：株価チャート詳細画面（pages/3_stock_chart.py）。

役割：太刀岡担当のstock_price_dfを使い、ローソク足チャートと出来高を表示する。
山﨑担当は固有ロジックを持たないため、logic側の関数は呼び出さない。
"""

import streamlit as st
import plotly.graph_objects as go

try:
    from logic.error_utils import show_warning
except ImportError:  # pragma: no cover - 相川さんの実装が未マージの間の暫定措置

    def show_warning(msg: str) -> None:
        st.warning(msg)


st.title("株価チャート")

stock_df = st.session_state.get("stock_price_df")
ticker = st.session_state.get("selected_ticker")

if stock_df is None or stock_df.empty:
    show_warning("データが取得されていません。トップ画面で銘柄を選択してください。")
    st.stop()

st.subheader(f"{ticker} ローソク足チャート")

fig = go.Figure(data=[
    go.Candlestick(
        x=stock_df["Date"],
        open=stock_df["Open"],
        high=stock_df["High"],
        low=stock_df["Low"],
        close=stock_df["Close"],
        name="株価",
    )
])
fig.update_layout(
    xaxis_title="日付",
    yaxis_title="価格",
    xaxis_rangeslider_visible=False,
    height=450,
)
st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("出来高")
st.bar_chart(stock_df.set_index("Date")["Volume"])