import streamlit as st

from logic.indicators import calc_rsi, calc_bollinger, calc_bb_position, calc_hv, calc_volume_ratio
from logic.similar_periods import extract_similar_periods, DEFAULT_TOLERANCE
from logic.error_utils import show_error, show_warning

st.title("過去類似局面")

# 太刀岡担当ページから受け渡される想定のsession_state（キー名は要すり合わせ）
ticker = st.session_state.get("data_selected_ticker")
price_df = st.session_state.get("data_stock_price_df")

if not ticker or price_df is None or price_df.empty:
    show_warning("銘柄が選択されていません。トップ画面で銘柄を選択してください。")
    st.stop()

# 指標計算（及川ロジックを呼び出し、Date列でmergeしてhistoryを作る）
rsi_df = calc_rsi(price_df)
bb_df = calc_bollinger(price_df)
bb_pos_df = calc_bb_position(price_df, bb_df)
hv_df = calc_hv(price_df)
vol_df = calc_volume_ratio(price_df)

history = (
    rsi_df.merge(hv_df, on="Date")
    .merge(bb_pos_df, on="Date")
    .merge(vol_df, on="Date")
)

if history.empty:
    show_error("指標データの計算に失敗しました。")
    st.stop()

history_valid = history.dropna()
if history_valid.empty:
    show_warning("直近の指標値が計算できませんでした（データ不足の可能性）。")
    st.stop()

latest = history_valid.iloc[-1]
current = {
    "RSI": latest["RSI"],
    "HV": latest["HV"],
    "BBPosition": latest["BBPosition"],
    "VolumeRatio": latest["VolumeRatio"],
}

st.subheader("許容幅の調整")
col1, col2, col3 = st.columns(3)
with col1:
    rsi_tol = st.slider("RSI許容幅", 0.0, 20.0, float(DEFAULT_TOLERANCE["RSI"]), step=0.5)
with col2:
    hv_tol = st.slider("HV許容幅(%)", 0.0, 10.0, float(DEFAULT_TOLERANCE["HV"]), step=0.5)
with col3:
    vol_tol = st.slider("出来高倍率許容幅", 0.0, 2.0, float(DEFAULT_TOLERANCE["VolumeRatio"]), step=0.1)

tolerance = {"RSI": rsi_tol, "HV": hv_tol, "VolumeRatio": vol_tol}

similar_df = extract_similar_periods(current, history, tolerance)
st.session_state["iwama_similar_periods_df"] = similar_df  # デモトレード画面へ受け渡し用

st.subheader("類似局面一覧")
if similar_df.empty:
    show_warning("条件に一致する過去局面が見つかりませんでした。許容幅を広げてください。")
else:
    st.dataframe(similar_df, use_container_width=True)
    st.caption(f"{len(similar_df)}件の類似局面が見つかりました。")