"""太刀岡担当：トップ画面（pages/1_home.py）。

役割：
- 銘柄コード・期間・投資の立場の入力を受け付け、株価と日経平均を取得する
- 取得結果を st.session_state に格納し、他画面から使えるようにする
- 分析開始後はタブで概要・チャート・データを切り替え表示する

実装規約（仕様書6章）への対応：
- 6-2: エラーメッセージ表示（show_error）は画面側で行う
- 6-5: 追加したsession_stateキー investment_stance / analysis_started は
       PR説明欄で共有すること
"""

from datetime import date, timedelta

import streamlit as st

from logic.data_fetch import get_index_data, get_stock_data, normalize_to_100

try:
    from logic.error_utils import show_error, show_warning
except ImportError:  # pragma: no cover - フェーズ1の並行開発用の暫定措置

    def show_error(msg: str) -> None:
        st.error(msg)

    def show_warning(msg: str) -> None:
        st.warning(msg)


st.set_page_config(page_title="トップ | 株価分析", layout="wide")
st.title("トップ：銘柄選択とデータ取得")

col_ticker, col_period, col_stance = st.columns([1.2, 1, 1])

with col_ticker:
    ticker = st.text_input(
        "銘柄コード（yfinance形式）",
        value=st.session_state.get("selected_ticker", "7203.T"),
        help="東証銘柄は「証券コード.T」の形式（例：7203.T）",
    )

with col_period:
    period_options = ["3年", "5年", "10年", "任意"]
    default_period = st.session_state.get("selected_period", "3年")
    period_choice = st.selectbox(
        "分析期間",
        period_options,
        index=period_options.index(default_period) if default_period in period_options else 0,
    )
    custom_start = custom_end = None
    if period_choice == "任意":
        custom_start = st.date_input("開始日", value=date.today() - timedelta(days=365))
        custom_end = st.date_input("終了日", value=date.today())

with col_stance:
    stance_options = ["すでに保有している", "これから購入する"]
    default_stance = st.session_state.get("investment_stance", stance_options[0])
    stance = st.radio("立場", stance_options, index=stance_options.index(default_stance))

st.divider()

if st.button("分析開始", type="primary"):
    ticker_clean = ticker.strip()
    if not ticker_clean:
        show_error("銘柄コードを入力してください。")
    elif period_choice == "任意" and custom_start >= custom_end:
        show_error("開始日は終了日より前の日付を指定してください。")
    else:
        with st.spinner("株価データを取得中..."):
            if period_choice == "任意":
                # 【暫定対応】get_stock_dataはperiod文字列のみ対応のため、
                # 10年分を取得してから日付でフィルタする。要：太刀岡さんへの仕様確認。
                stock_df_full = get_stock_data(ticker_clean, "10年")
                index_df_full = get_index_data("10年")
                if not stock_df_full.empty:
                    mask = (stock_df_full["Date"] >= str(custom_start)) & (
                        stock_df_full["Date"] <= str(custom_end)
                    )
                    stock_df = stock_df_full.loc[mask].reset_index(drop=True)
                else:
                    stock_df = stock_df_full
                if index_df_full is not None and not index_df_full.empty:
                    idx_mask = (index_df_full["Date"] >= str(custom_start)) & (
                        index_df_full["Date"] <= str(custom_end)
                    )
                    index_df = index_df_full.loc[idx_mask].reset_index(drop=True)
                else:
                    index_df = index_df_full
            else:
                stock_df = get_stock_data(ticker_clean, period_choice)
                index_df = get_index_data(period_choice)

        if stock_df.empty:
            show_error(
                f"銘柄「{ticker_clean}」の株価データを取得できませんでした。"
                "銘柄コードと通信環境を確認してください。"
            )
        else:
            st.session_state["selected_ticker"] = ticker_clean
            st.session_state["selected_period"] = period_choice
            st.session_state["stock_price_df"] = stock_df
            st.session_state["index_price_df"] = index_df
            st.session_state["investment_stance"] = stance
            st.session_state["analysis_started"] = True
            if index_df.empty:
                show_warning(
                    "日経平均（^N225）の取得に失敗しました。"
                    "株価単体の分析は可能ですが、乖離率などの比較機能は使えません。"
                )
            st.success(f"{ticker_clean} のデータを取得しました（{len(stock_df)}営業日分、{stance}）。")

stock_df = st.session_state.get("stock_price_df")
index_df = st.session_state.get("index_price_df")

if not st.session_state.get("analysis_started") or stock_df is None or stock_df.empty:
    st.info("銘柄・期間・立場を指定して「分析開始」を押してください。")
    st.stop()

tab_overview, tab_chart, tab_data = st.tabs(["概要", "基準日100正規化チャート", "取得データ"])

with tab_overview:
    st.subheader(f"取得結果：{st.session_state.get('selected_ticker', '')}")
    col_a, col_b, col_c = st.columns(3)
    latest = stock_df.iloc[-1]
    col_a.metric("最新日付", latest["Date"])
    col_b.metric("最新終値", f"{latest['Close']:,.1f}")
    col_c.metric("データ件数", f"{len(stock_df)} 営業日")
    st.caption(f"立場：{st.session_state.get('investment_stance', '')}")

with tab_chart:
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
    else:
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
            "基準日を100とした相対パフォーマンス。"
            "基準日が休場日の場合は、その直後の営業日を基準にしています。"
        )

with tab_data:
    st.subheader("取得データ（末尾10行）")
    st.dataframe(stock_df.tail(10), use_container_width=True)