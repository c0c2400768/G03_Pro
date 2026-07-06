"""エントリポイント（app.py）。

役割：
- pages/配下の各画面をst.navigationでまとめ、サイドバー表示名を日本語化する
- アプリ全体のページ設定（set_page_config）をここに一本化する
- 個別のロジックは持たない
"""

import streamlit as st

st.set_page_config(
    page_title="株価分析アプリ",
    layout="wide",
    initial_sidebar_state="expanded",
)

pages = [
    st.Page("pages/1_home.py", title="トップ"),
    st.Page("pages/2_summary.py", title="サマリー"),
    st.Page("pages/3_stock_chart.py", title="株価チャート"),
    st.Page("pages/4_multi_indicator_analysis.py", title="複数指標分析"),
    st.Page("pages/5_similar_market_phases.py", title="過去類似局面"),
    st.Page("pages/6_demo_trading_results.py", title="デモトレード結果"),
    st.Page("pages/7_decision_support.py", title="補助判断資料"),
]

nav = st.navigation(pages)
nav.run()
