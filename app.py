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
    st.Page("pages/1_home.py", title="①銘柄・分析条件の設定", icon="🔧"),
    st.Page("pages/2_summary.py", title="②株価・指標サマリー", icon="📋"),
    st.Page("pages/3_stock_chart.py", title="③株価チャート", icon="🕯️"),
    st.Page("pages/4_multi_indicator_analysis.py", title="④指標分析", icon="🧮"),
    st.Page("pages/5_similar_market_phases.py", title="⑤似た相場を探す", icon="🔍"),
    st.Page("pages/6_demo_trading_results.py", title="⑥シミュレーション結果", icon="🎯"),
    st.Page("pages/7_decision_support.py", title="⑦投資判断サポート", icon="🧭"),
]

nav = st.navigation(pages)
nav.run()
