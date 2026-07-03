"""複数指標分析詳細画面（担当：及川）。

設計書（画面④）の内容：
- RSI・BB・HV・出来高倍率・乖離率の現在値を数値で表示
- 各指標の状態（過熱・中立・売られすぎ 等）をテキスト＋色で表示
- 各指標の推移をタブで切り替えてグラフ表示
- タブ上部に全指標の現在値を横並びで表示
- 各指標の意味・読み方をトグル(expander)で開閉して確認できる

前提（session_state）：
    このアプリは複数ファイルに分かれた協働開発のため、他担当の画面・関数の
    実装がまだ手元に無い状態でこのファイルを書いている。そのため、上流
    （太刀岡さんのトップ画面）が保存する session_state のキー名は、
    interface.md 6-5 の命名規則（`担当領域_変数名`）に沿って以下のように
    "仮定" している。実際のキー名と食い違っていたら、後述の
    ## 前提キー一覧 の該当箇所だけ書き換えれば動くようにしてある。

    - st.session_state["stock_price_df"]      : 太刀岡 get_stock_data() の出力
                                                 (Date, Open, High, Low, Close, Volume)
    - st.session_state["index_price_df"]      : 太刀岡 get_index_data() の出力 (Date, Close)
    - st.session_state["normalized_stock_df"] : 太刀岡 normalize_to_100(株価df) の出力
                                                 (Date, Normalized)
    - st.session_state["normalized_index_df"] : 太刀岡 normalize_to_100(日経平均df) の出力
                                                 (Date, Normalized)
    - st.session_state["selected_ticker"]     : 選択された銘柄コード（表示用）

    正規化データ（乖離率の計算に必要）がまだ無い場合でも、他の指標は
    表示できるようにしてある（乖離率タブだけ情報表示にフォールバック）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from logic.indicators import (
    calc_rsi,
    calc_bollinger,
    calc_bb_position,
    calc_hv,
    calc_volume_ratio,
    calc_deviation,
)
from logic.error_utils import show_error, show_warning


st.set_page_config(page_title="複数指標分析", page_icon="🧮", layout="wide")

# =====================================================================
# 状態判定（このファイル固有のUI用ロジック。logic/には置かない＝画面表示の
# 都合であり、他担当が使う共有インターフェースではないため）
# =====================================================================
LEVEL_COLOR = {
    "hot": "🔴", "warm": "🟠", "neutral": "⚪", "cold": "🔵", "na": "⚫",
}


def judge_rsi(value: float) -> tuple[str, str]:
    """RSIの値から (状態ラベル, 色レベル) を返す。"""
    if value is None or pd.isna(value):
        return "判定不可", "na"
    if value >= 70:
        return "買われすぎ（過熱）", "hot"
    if value <= 30:
        return "売られすぎ", "cold"
    return "中立", "neutral"


def judge_bb_position(position: object) -> tuple[str, str]:
    """BBPosition("upper"/"mid"/"lower") から (状態ラベル, 色レベル) を返す。"""
    if position is None or (isinstance(position, float) and pd.isna(position)):
        return "判定不可", "na"
    mapping = {
        "upper": ("上限付近", "hot"),
        "lower": ("下限付近", "cold"),
        "mid": ("中央付近", "neutral"),
    }
    return mapping.get(position, ("判定不可", "na"))


def judge_hv(hv_series: pd.Series, current: float) -> tuple[str, str]:
    """HVの現在値を、自分自身の過去分布と比べて (状態ラベル, 色レベル) を返す。"""
    valid = hv_series.dropna()
    if current is None or pd.isna(current) or valid.empty:
        return "判定不可", "na"
    q75 = valid.quantile(0.75)
    q25 = valid.quantile(0.25)
    if current >= q75:
        return "変動が大きい", "hot"
    if current <= q25:
        return "変動が小さい", "cold"
    return "平常", "neutral"


def judge_volume_ratio(value: float) -> tuple[str, str]:
    """出来高倍率から (状態ラベル, 色レベル) を返す。"""
    if value is None or pd.isna(value):
        return "判定不可", "na"
    if value >= 2.0:
        return "急増", "hot"
    if value >= 1.5:
        return "やや多い", "warm"
    if value <= 0.5:
        return "閑散", "cold"
    return "平常", "neutral"


def judge_deviation(value: float) -> tuple[str, str]:
    """市場乖離率から (状態ラベル, 色レベル) を返す。"""
    if value is None or pd.isna(value):
        return "判定不可", "na"
    if value >= 5:
        return "市場より強い", "hot"
    if value <= -5:
        return "市場より弱い", "cold"
    return "市場並み", "neutral"


def badge(label: str, level: str) -> str:
    """状態ラベルに色つき絵文字を付ける。"""
    return f"{LEVEL_COLOR.get(level, '⚪')} {label}"


def last_valid(series: pd.Series):
    """Seriesの末尾から見て最初に見つかる非NaN値を返す（無ければNone）。"""
    valid = series.dropna()
    return None if valid.empty else valid.iloc[-1]


INDICATOR_GUIDE = {
    "RSI": (
        "**RSI（相対力指数）** は値動きの強さを0〜100で表す指標です。"
        "70以上で買われすぎ、30以下で売られすぎの目安とされます。"
    ),
    "ボリンジャーバンド": (
        "**ボリンジャーバンド** は移動平均線の上下に標準偏差(σ)の幅を取った帯です。"
        "終値が上限に近ければ「上限付近」、下限に近ければ「下限付近」と判定します。"
    ),
    "HV": (
        "**ヒストリカルボラティリティ(HV)** は過去の値動きの激しさ（年率%）です。"
        "この銘柄自身の過去分布と比べ、上位25%なら「変動が大きい」と判定します。"
    ),
    "出来高倍率": (
        "**出来高倍率** は直近の出来高 ÷ 過去20日平均出来高です。"
        "2.0以上で急増、0.5以下で閑散とみなします。"
    ),
    "乖離率": (
        "**市場乖離率** は、基準日を100とした株価と日経平均の正規化値の差（ポイント）です。"
        "プラスなら株価が市場平均より強く推移していることを表します。"
    ),
}


# =====================================================================
# データ取得（他担当の画面が保存した session_state を読む）
# =====================================================================
price_df = st.session_state.get("stock_price_df")
index_df = st.session_state.get("index_price_df")
normalized_stock_df = st.session_state.get("normalized_stock_df")
normalized_index_df = st.session_state.get("normalized_index_df")
ticker = st.session_state.get("selected_ticker", "―")

st.title("🧮 複数指標分析詳細画面")

if price_df is None or price_df.empty:
    show_error("株価データがありません。トップ画面で銘柄を選択し、分析を実行してください。")
    st.stop()

st.caption(f"対象銘柄：{ticker}")

# =====================================================================
# 指標の計算（1つ失敗しても他は続行する）
# =====================================================================
computed: dict[str, pd.DataFrame] = {}
failed: list[str] = []


def safe_calc(name: str, func, *args) -> None:
    """指標計算を試み、失敗したらその指標だけスキップして処理を続ける。"""
    try:
        computed[name] = func(*args)
    except Exception:
        failed.append(name)


safe_calc("RSI", calc_rsi, price_df)
safe_calc("BB", calc_bollinger, price_df)
if "BB" in computed:
    safe_calc("BBPosition", calc_bb_position, price_df, computed["BB"])
safe_calc("HV", calc_hv, price_df)
safe_calc("VolumeRatio", calc_volume_ratio, price_df)

deviation_available = normalized_stock_df is not None and normalized_index_df is not None
if deviation_available:
    safe_calc("Deviation", calc_deviation, normalized_stock_df, normalized_index_df)
else:
    show_warning("正規化データが未取得のため、乖離率は表示できません。トップ画面の分析完了後に再度お試しください。")

for name in failed:
    show_error(f"{name} の計算に失敗しました。この指標のみスキップして表示を続けます。")

# 画面間の受け渡し用に保存（命名規則: 及川担当のため oikawa_ プレフィックス）
st.session_state["oikawa_indicators"] = computed

# =====================================================================
# 現在値の取得と状態判定
# =====================================================================
current_rsi = last_valid(computed["RSI"]["RSI"]) if "RSI" in computed else None
current_bbpos = last_valid(computed["BBPosition"]["BBPosition"]) if "BBPosition" in computed else None
current_hv = last_valid(computed["HV"]["HV"]) if "HV" in computed else None
current_vr = last_valid(computed["VolumeRatio"]["VolumeRatio"]) if "VolumeRatio" in computed else None
current_dev = last_valid(computed["Deviation"]["Deviation"]) if "Deviation" in computed else None

rsi_label, rsi_level = judge_rsi(current_rsi)
bb_label, bb_level = judge_bb_position(current_bbpos)
hv_label, hv_level = judge_hv(computed["HV"]["HV"], current_hv) if "HV" in computed else ("判定不可", "na")
vr_label, vr_level = judge_volume_ratio(current_vr)
dev_label, dev_level = judge_deviation(current_dev)

# =====================================================================
# 現在値の横並び表示
# =====================================================================
cols = st.columns(5)
rows = [
    ("RSI", f"{current_rsi:.1f}" if current_rsi is not None else "—", rsi_label, rsi_level),
    ("BB位置", {"upper": "上限付近", "mid": "中央", "lower": "下限付近"}.get(current_bbpos, "—"),
     bb_label, bb_level),
    ("HV（年率）", f"{current_hv:.1f}%" if current_hv is not None else "—", hv_label, hv_level),
    ("出来高倍率", f"{current_vr:.2f}倍" if current_vr is not None else "—", vr_label, vr_level),
    ("乖離率", f"{current_dev:.2f}pt" if current_dev is not None else "—", dev_label, dev_level),
]
for col, (name, value, label, level) in zip(cols, rows):
    col.metric(name, value)
    col.caption(badge(label, level))

if current_rsi is not None:
    st.progress(min(max(int(round(current_rsi)), 0), 100), text=f"RSI {current_rsi:.1f} / 100")

st.divider()

# =====================================================================
# 指標ごとのタブ（推移グラフ＋読み方）
# =====================================================================
tab_labels = ["RSI", "ボリンジャーバンド", "HV", "出来高倍率", "乖離率"]
tabs = st.tabs(tab_labels)

with tabs[0]:
    if "RSI" in computed:
        df = computed["RSI"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["Date"], y=df["RSI"], name="RSI", line=dict(color="#1f77b4")))
        fig.add_hline(y=70, line=dict(color="red", dash="dash"))
        fig.add_hline(y=30, line=dict(color="green", dash="dash"))
        fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10), yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("RSIを表示できませんでした。")
    with st.expander("RSI の見方"):
        st.markdown(INDICATOR_GUIDE["RSI"])

with tabs[1]:
    if "BB" in computed:
        df = computed["BB"]
        merged = price_df[["Date", "Close"]].merge(df, on="Date", how="left")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=merged["Date"], y=merged["Upper"], name="+2σ",
                                 line=dict(color="#d62728", width=1)))
        fig.add_trace(go.Scatter(x=merged["Date"], y=merged["Middle"], name="中央線",
                                 line=dict(color="#ff7f0e", width=1)))
        fig.add_trace(go.Scatter(x=merged["Date"], y=merged["Lower"], name="-2σ",
                                 line=dict(color="#2ca02c", width=1)))
        fig.add_trace(go.Scatter(x=merged["Date"], y=merged["Close"], name="終値",
                                 line=dict(color="#1f77b4")))
        fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10),
                          legend=dict(orientation="h", y=1.02))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ボリンジャーバンドを表示できませんでした。")
    with st.expander("ボリンジャーバンドの見方"):
        st.markdown(INDICATOR_GUIDE["ボリンジャーバンド"])

with tabs[2]:
    if "HV" in computed:
        df = computed["HV"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["Date"], y=df["HV"], name="HV(%)", line=dict(color="#9467bd")))
        fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10), yaxis_title="年率%")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("HVを表示できませんでした。")
    with st.expander("HV の見方"):
        st.markdown(INDICATOR_GUIDE["HV"])

with tabs[3]:
    if "VolumeRatio" in computed:
        df = computed["VolumeRatio"]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df["Date"], y=df["VolumeRatio"], name="出来高倍率",
                             marker=dict(color="#8c8c8c")))
        fig.add_hline(y=1.0, line=dict(color="black", dash="dash"))
        fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("出来高倍率を表示できませんでした。")
    with st.expander("出来高倍率の見方"):
        st.markdown(INDICATOR_GUIDE["出来高倍率"])

with tabs[4]:
    if "Deviation" in computed:
        df = computed["Deviation"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["Date"], y=df["Deviation"], name="乖離率(pt)",
                                 line=dict(color="#e377c2")))
        fig.add_hline(y=0, line=dict(color="black", dash="dash"))
        fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("乖離率を表示できませんでした（正規化データが未取得の可能性があります）。")
    with st.expander("乖離率の見方"):
        st.markdown(INDICATOR_GUIDE["乖離率"])