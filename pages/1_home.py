"""太刀岡担当：トップ画面（pages/1_home.py）。

役割：
- 銘柄コード・期間の入力を受け付け、株価と日経平均を取得する
- 取得結果を st.session_state に格納し、他画面（サマリー・チャート等）から使えるようにする
- 基準日100正規化の比較チャートを表示する

実装規約（仕様書6章）への対応：
- 6-2: エラーメッセージ表示（show_error）は画面側＝この画面で行う。logic側はUI処理をしない
- 6-5: session_stateのkeyは selected_ticker / selected_period / stock_price_df /
       index_price_df / normalize_base_date を使用（PR説明欄で共有すること）
"""

import streamlit as st

from logic.data_fetch import get_index_data, get_stock_data, normalize_to_100

# 相川さんの共通モジュール（logic/error_utils.py）が未マージの間も動かせるように、
# import失敗時だけ暫定のst.errorにフォールバックする。マージ後はtry/exceptを外してよい。
try:
    from logic.error_utils import show_error, show_warning
except ImportError:  # pragma: no cover - フェーズ1の並行開発用の暫定措置

    def show_error(msg: str) -> None:
        """暫定：st.errorでエラーメッセージを表示する。"""
        st.error(msg)

    def show_warning(msg: str) -> None:
        """暫定：st.warningで警告メッセージを表示する。"""
        st.warning(msg)


st.set_page_config(page_title="トップ | 株価分析", layout="wide")
st.title("トップ：銘柄選択とデータ取得")

# ---------------------------------------------------------------
# 入力フォーム
# ---------------------------------------------------------------
col_ticker, col_period = st.columns([2, 1])
with col_ticker:
    ticker = st.text_input(
        "銘柄コード（yfinance形式）",
        value=st.session_state.get("selected_ticker", "7203.T"),
        help="東証銘柄は「証券コード.T」の形式で入力（例：トヨタ自動車 → 7203.T）",
    )
with col_period:
    period_options = ["6ヶ月", "1年", "2年", "3年", "5年", "10年"]
    default_period = st.session_state.get("selected_period", "3年")
    period = st.selectbox(
        "取得期間",
        period_options,
        index=period_options.index(default_period)
        if default_period in period_options
        else 3,
    )

if st.button("データ取得", type="primary"):
    ticker_clean = ticker.strip()
    if not ticker_clean:
        show_error("銘柄コードを入力してください。")
    else:
        with st.spinner("株価データを取得中..."):
            stock_df = get_stock_data(ticker_clean, period)
            index_df = get_index_data(period)

        # 6-2: 返ってきたdfが空かどうかを必ずチェックしてから後続処理へ
        if stock_df.empty:
            show_error(
                f"銘柄「{ticker_clean}」の株価データを取得できませんでした。"
                "銘柄コードと通信環境を確認してください。"
            )
        else:
            st.session_state["selected_ticker"] = ticker_clean
            st.session_state["selected_period"] = period
            st.session_state["stock_price_df"] = stock_df
            st.session_state["index_price_df"] = index_df
            if index_df.empty:
                show_warning(
                    "日経平均（^N225）の取得に失敗しました。"
                    "株価単体の分析は可能ですが、乖離率などの比較機能は使えません。"
                )
            st.success(f"{ticker_clean} のデータを取得しました（{len(stock_df)}営業日分）。")

# ---------------------------------------------------------------
# 取得済みデータの表示（session_stateにあれば再実行後も表示される）
# ---------------------------------------------------------------
stock_df = st.session_state.get("stock_price_df")
index_df = st.session_state.get("index_price_df")

if stock_df is None or stock_df.empty:
    st.info("銘柄コードと期間を指定して「データ取得」を押してください。")
    st.stop()

st.divider()
st.subheader(f"取得結果：{st.session_state.get('selected_ticker', '')}")

col_a, col_b, col_c = st.columns(3)
latest = stock_df.iloc[-1]
col_a.metric("最新日付", latest["Date"])
col_b.metric("最新終値", f"{latest['Close']:,.1f}")
col_c.metric("データ件数", f"{len(stock_df)} 営業日")

with st.expander("取得データ（末尾10行）を確認"):
    st.dataframe(stock_df.tail(10), use_container_width=True)

# ---------------------------------------------------------------
# 基準日100正規化：日経平均との比較チャート
# ---------------------------------------------------------------
st.divider()
st.subheader("基準日100正規化チャート（対 日経平均）")

date_options = stock_df["Date"].tolist()
base_date = st.select_slider(
    "基準日（この日を100として指数化）",
    options=date_options,
    value=st.session_state.get("normalize_base_date", date_options[0]),
    key="normalize_base_date_slider",
)
st.session_state["normalize_base_date"] = base_date

norm_stock = normalize_to_100(stock_df, base_date)
if norm_stock.empty:
    show_error("正規化に失敗しました。基準日を変更して再度お試しください。")
    st.stop()

chart_df = norm_stock.rename(
    columns={"Normalized": st.session_state.get("selected_ticker", "銘柄")}
).set_index("Date")

if index_df is not None and not index_df.empty:
    norm_index = normalize_to_100(index_df, base_date)
    if not norm_index.empty:
        chart_df = chart_df.join(
            norm_index.rename(columns={"Normalized": "日経平均"}).set_index("Date"),
            how="left",
        )

st.line_chart(chart_df)
st.caption(
    "基準日を100とした相対パフォーマンス。基準日が休場日の場合は、その直後の営業日を基準にしています。"
)