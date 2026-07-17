import streamlit as st

from logic.indicators import calc_rsi, calc_bollinger, calc_bb_position, calc_hv, calc_volume_ratio
from logic.similar_periods import extract_similar_periods, DEFAULT_TOLERANCE
from logic.error_utils import show_error, show_warning

st.title("⑤似た相場を探す")
st.caption("現在の複数の指標と似た状態だった、過去の相場を探します。")

# 類似局面0件時に「許容幅の問題」か「そもそも過去データ不足」かを見分ける行数閾値。
# interface.mdに規定はなく暫定値（要調整の場合は差し替え可）。
MIN_HISTORY_ROWS_FOR_TOLERANCE_ADVICE = 100

# 太刀岡担当ページから受け渡される想定のsession_state（キー名は要すり合わせ）
ticker = st.session_state.get("selected_ticker")
price_df = st.session_state.get("stock_price_df")

if not ticker or price_df is None or price_df.empty:
    show_warning("銘柄が選択されていません。①銘柄・分析条件の設定画面で銘柄を選択してください。")
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

# 現在日（当日）自身の指標値は必ず自分自身と完全一致するため、除外しないと
# 常に1件は類似局面として拾われてしまう。比較対象のhistoryから当日の行を除外する。
today_date = str(latest["Date"])
history_for_search = history.loc[history["Date"].astype(str) != today_date]

st.subheader("許容幅の調整")

# st.navigation構成のマルチページでは、ウィジェットにkeyを指定するだけではページ離脱後に
# 値が保持されない（そのページのスクリプトが実行されない間にウィジェットの状態がクリアされる
# ため）。そのためウィジェットのkeyとは別に、通常のsession_stateの値として許容幅を保持し、
# 毎回そこから初期値を読み書きすることでページ間の値保持を実現する。
_TOLERANCE_STATE_KEYS = {
    "RSI": "iwama_rsi_tolerance",
    "HV": "iwama_hv_tolerance",
    "VolumeRatio": "iwama_volume_tolerance",
}
for _indicator, _state_key in _TOLERANCE_STATE_KEYS.items():
    st.session_state.setdefault(_state_key, float(DEFAULT_TOLERANCE[_indicator]))

col1, col2, col3 = st.columns(3)
with col1:
    rsi_tol = st.slider(
        "RSI許容幅", 0.0, 20.0, st.session_state[_TOLERANCE_STATE_KEYS["RSI"]], step=0.5
    )
with col2:
    hv_tol = st.slider(
        "HV許容幅(%)", 0.0, 10.0, st.session_state[_TOLERANCE_STATE_KEYS["HV"]], step=0.5
    )
with col3:
    vol_tol = st.slider(
        "出来高倍率許容幅", 0.0, 2.0, st.session_state[_TOLERANCE_STATE_KEYS["VolumeRatio"]], step=0.1
    )

st.session_state[_TOLERANCE_STATE_KEYS["RSI"]] = rsi_tol
st.session_state[_TOLERANCE_STATE_KEYS["HV"]] = hv_tol
st.session_state[_TOLERANCE_STATE_KEYS["VolumeRatio"]] = vol_tol

tolerance = {"RSI": rsi_tol, "HV": hv_tol, "VolumeRatio": vol_tol}

similar_df = extract_similar_periods(current, history_for_search, tolerance)
# デモトレード画面へ受け渡し用。分析条件タグと一緒に保存し、⑥側で「別条件（別銘柄・
# 別期間等）の結果を使い回していないか」を照合できるようにする（stale結果表示の防止）。
st.session_state["iwama_similar_periods_df"] = {
    "tag": st.session_state.get("analysis_condition_tag"),
    "data": similar_df,
}

st.subheader("類似局面一覧")
if similar_df.empty:
    if len(history) < MIN_HISTORY_ROWS_FOR_TOLERANCE_ADVICE:
        show_warning(
            "過去データが少ないため類似局面を十分に探索できません"
            "（上場間もない銘柄や分析期間が短い場合に起こります）。"
            "分析期間を延ばすか、別の銘柄でお試しください。"
        )
    else:
        show_warning("条件に一致する過去局面が見つかりませんでした。許容幅を広げてください。")
else:
    st.dataframe(similar_df, use_container_width=True)
    st.caption(f"{len(similar_df)}件の類似局面が見つかりました。")