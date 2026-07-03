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

from logic.comparison import select_comparison_targets
from logic.data_fetch import get_index_data, get_stock_data, normalize_to_100
from logic.demo_trade import resolve_entry_price
from logic.error_utils import show_error, show_warning
from logic.ticker_lookup import get_company_name, list_tickers


st.set_page_config(page_title="トップ | 株価分析", layout="wide")
st.title("トップ：銘柄選択とデータ取得")

col_ticker, col_period, col_stance = st.columns([1.2, 1, 1])

with col_ticker:
    tickers = list_tickers()
    if not tickers:
        show_error("銘柄マスタ（data/data_j.xls）を読み込めませんでした。")
        st.stop()

    ticker_options = [t["ticker"] for t in tickers]
    ticker_labels = {t["ticker"]: f"{t['name']}（{t['code']}）" for t in tickers}
    default_ticker = st.session_state.get("selected_ticker", "7203.T")
    default_index = ticker_options.index(default_ticker) if default_ticker in ticker_options else 0

    ticker = st.selectbox(
        "銘柄選択（銘柄名またはコードで検索）",
        options=ticker_options,
        index=default_index,
        format_func=lambda t: ticker_labels.get(t, t),
        help="銘柄名の一部またはコードを入力すると絞り込めます",
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

    purchase_date = None
    if stance == "すでに保有している":
        # 取得価格はユーザーごとに異なるため、購入日から都度取得する（固定値は持たない）
        purchase_date = st.date_input(
            "購入日",
            value=None,
            max_value=date.today(),
            help="保有株を購入した日付。この日の終値を取得価格として使用します。",
        )

st.divider()

if st.button("分析開始", type="primary"):
    ticker_clean = ticker
    if period_choice == "任意" and custom_start >= custom_end:
        show_error("開始日は終了日より前の日付を指定してください。")
    elif stance == "すでに保有している" and purchase_date is None:
        show_error("「すでに保有している」を選択した場合は、購入日を入力してください。")
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
                f"銘柄「{get_company_name(ticker_clean)}」の株価データを取得できませんでした。"
                "通信環境を確認してください。"
            )
        else:
            st.session_state["selected_ticker"] = ticker_clean
            st.session_state["selected_period"] = period_choice
            st.session_state["stock_price_df"] = stock_df
            st.session_state["index_price_df"] = index_df
            st.session_state["investment_stance"] = stance
            st.session_state["analysis_started"] = True

            if stance == "すでに保有している":
                purchase_price = resolve_entry_price(stock_df, str(purchase_date))
                st.session_state["purchase_date"] = str(purchase_date)
                st.session_state["purchase_price"] = purchase_price
                if purchase_price is None:
                    show_warning(
                        f"購入日（{purchase_date}）時点の株価データが見つかりませんでした。"
                        "デモトレード結果画面で「売却」の結果は算出されません。"
                    )
                elif str(purchase_date) < stock_df["Date"].min():
                    show_warning(
                        f"購入日（{purchase_date}）が分析期間より前のため、"
                        f"取得価格は分析期間内で最も古い日（{stock_df['Date'].min()}）の"
                        "終値で代用しています。より正確にするには分析期間を広げてください。"
                    )
            else:
                # 「これから購入する」に切り替えた場合は前回の購入情報を持ち越さない
                st.session_state["purchase_date"] = None
                st.session_state["purchase_price"] = None

            if index_df.empty:
                show_warning(
                    "日経平均（^N225）の取得に失敗しました。"
                    "株価単体の分析は可能ですが、乖離率などの比較機能は使えません。"
                )
            st.success(
                f"{get_company_name(ticker_clean)} のデータを取得しました"
                f"（{len(stock_df)}営業日分、{stance}）。"
            )

stock_df = st.session_state.get("stock_price_df")
index_df = st.session_state.get("index_price_df")

if not st.session_state.get("analysis_started") or stock_df is None or stock_df.empty:
    st.info("銘柄・期間・立場を指定して「分析開始」を押してください。")
    st.stop()

tab_overview, tab_chart, tab_data = st.tabs(["概要", "基準日100正規化チャート", "取得データ"])

with tab_overview:
    st.subheader(f"取得結果：{get_company_name(st.session_state.get('selected_ticker', ''))}")
    col_a, col_b, col_c = st.columns(3)
    latest = stock_df.iloc[-1]
    col_a.metric("最新日付", latest["Date"])
    col_b.metric("最新終値", f"{latest['Close']:,.1f}")
    col_c.metric("データ件数", f"{len(stock_df)} 営業日")
    st.caption(f"立場：{st.session_state.get('investment_stance', '')}")

    if st.session_state.get("investment_stance") == "すでに保有している":
        purchase_price = st.session_state.get("purchase_price")
        if purchase_price is not None:
            st.metric(
                f"取得価格（購入日：{st.session_state.get('purchase_date', '')}）",
                f"{purchase_price:,.1f}",
            )

with tab_chart:
    st.subheader("基準日100正規化チャート（対 日経平均）")
    date_options = stock_df["Date"].tolist()
    if st.session_state.get("normalize_base_date_slider") not in date_options:
        # 銘柄切り替えで日付範囲が変わり、前回の基準日が選べなくなった場合はリセットする
        st.session_state["normalize_base_date_slider"] = date_options[0]

    base_date = st.select_slider(
        "基準日（この日を100として指数化）",
        options=date_options,
        key="normalize_base_date_slider",
    )
    st.session_state["normalize_base_date"] = base_date

    norm_stock = normalize_to_100(stock_df, base_date)
    if norm_stock.empty:
        show_error("正規化に失敗しました。基準日を変更して再度お試しください。")
    else:
        st.session_state["normalized_stock_df"] = norm_stock  # ← 追加

        chart_df = norm_stock.rename(
            columns={"Normalized": get_company_name(st.session_state.get("selected_ticker", "")) or "銘柄"}
        ).set_index("Date")
        if index_df is not None and not index_df.empty:
            norm_index = normalize_to_100(index_df, base_date)
            if not norm_index.empty:
                st.session_state["normalized_index_df"] = norm_index  # ← 追加
                chart_df = chart_df.join(
                    norm_index.rename(columns={"Normalized": "日経平均"}).set_index("Date"),
                    how="left",
                )

        peers = select_comparison_targets(st.session_state.get("selected_ticker", "")).get("peers", [])
        with st.expander("同業他社と比較"):
            if not peers:
                st.info("同業他社データがありません。")
            else:
                selected_peers = st.multiselect(
                    "比較する同業他社",
                    options=peers,
                    default=peers,
                    format_func=get_company_name,
                    key="comparison_peers_selected",
                )
                peer_period = st.session_state.get("selected_period", "3年")
                peer_fetch_period = "10年" if peer_period == "任意" else peer_period
                for peer_ticker in selected_peers:
                    peer_df = get_stock_data(peer_ticker, peer_fetch_period)
                    if peer_df.empty:
                        continue
                    norm_peer = normalize_to_100(peer_df, base_date)
                    if norm_peer.empty:
                        continue
                    chart_df = chart_df.join(
                        norm_peer.rename(columns={"Normalized": get_company_name(peer_ticker)}).set_index("Date"),
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