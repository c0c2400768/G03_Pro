"""山﨑担当：サマリー画面（pages/2_summary.py）。

役割：他担当のlogic関数（太刀岡：データ取得、及川：指標計算）を呼び出し、
要約情報を表示する。山﨑担当は固有ロジックを持たないため。
"""

import streamlit as st

from logic.indicators import calc_rsi, calc_bollinger, calc_bb_position, calc_hv, calc_volume_ratio

try:
    from logic.error_utils import show_warning
except ImportError:  # pragma: no cover - 相川さんの実装が未マージの間の暫定措置

    def show_warning(msg: str) -> None:
        st.warning(msg)


st.title("サマリー")

stock_df = st.session_state.get("stock_price_df")
ticker = st.session_state.get("selected_ticker")

if stock_df is None or stock_df.empty:
    show_warning("データが取得されていません。トップ画面で銘柄を選択してください。")
    st.stop()

latest = stock_df.iloc[-1]
prev = stock_df.iloc[-2] if len(stock_df) >= 2 else None

st.subheader(f"{ticker} の概況")

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
chart_df = stock_df[["Date", "Close"]].set_index("Date")
st.line_chart(chart_df)