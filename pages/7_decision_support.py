"""相川担当：補助判断表示画面（pages/7_decision_support.py）"""

from __future__ import annotations

import streamlit as st

from logic.csv_export import save_csv
from logic.decision_rating import add_action_ratings, rank_rated_actions, select_recommended_action
from logic.error_utils import show_error, show_warning
from logic.validation import run_peer_universe_validation, run_single_stock_validation
from pages._decision_support_view import (
    inject_styles,
    render_comparison_table,
    render_conclusion_card,
    render_decision_angles,
    render_disclaimer_footer,
)
from pages._validation_view import render_validation_detail_section

st.title("補助判断")
st.caption("過去の類似ケースと比較して、最適な投資行動を見つけるための分析ページです。")

inject_styles()

# --- 注意事項（最優先で目立つ位置に表示） -----------------------------------
st.warning(
    "⚠️ 本結果は過去データに基づくシミュレーションであり、"
    "将来の利益を保証するものではありません。売買手数料・税金は考慮していません。"
)

result_df = st.session_state.get("demo_trade_result_df")

if result_df is None or result_df.empty:
    show_warning("分析結果がありません。先に「デモトレード結果」画面を開いて計算を実行してください。")
    st.stop()

stance = st.session_state.get("investment_stance", "") or "―"

# --- walk-forward検証（統計検証）の計算 -------------------------------------
# 判定ロジックの安全装置（業種横断検証のp値によるキャップ）と、下部の統計検証カードの両方で使う
price_df = st.session_state.get("stock_price_df")
ticker = st.session_state.get("selected_ticker")
period = st.session_state.get("selected_period", "3年")
peer_fetch_period = "10年" if period == "任意" else period

single_stock_result = None
peer_result = None
if price_df is not None and not price_df.empty and ticker:
    with st.spinner("検証データを計算中..."):
        single_stock_result = run_single_stock_validation(price_df)
        peer_result = run_peer_universe_validation(ticker, price_df, peer_fetch_period)

peer_p_value = peer_result.get("p_value") if peer_result is not None else None

# --- 投資行動の判定（推奨/検討可/非推奨） -----------------------------------
rated_df = add_action_ratings(result_df, peer_p_value)
ranked_df = rank_rated_actions(rated_df)
recommended_row = select_recommended_action(ranked_df)

# --- 結論カード -------------------------------------------------------------
render_conclusion_card(recommended_row, ranked_df, stance)

# --- 投資行動の比較表 --------------------------------------------------------
render_comparison_table(ranked_df)

# --- 判断の切り口 ------------------------------------------------------------
render_decision_angles(ranked_df)

# --- CSVエクスポート --------------------------------------------------------
def _on_export_click() -> None:
    ok = save_csv(result_df, "decision_support_result.csv")
    st.session_state["decision_support_export_success"] = ok


st.download_button(
    label="分析結果をCSVで保存",
    data=result_df.to_csv(index=False).encode("utf-8-sig"),
    file_name="decision_support_result.csv",
    mime="text/csv",
    on_click=_on_export_click,
)

if st.session_state.get("decision_support_export_success") is False:
    show_error("CSVの保存に失敗しました。")

# --- 統計検証セクション -------------------------------------------------------
if single_stock_result is not None and peer_result is not None:
    render_validation_detail_section(single_stock_result, peer_result)
else:
    st.markdown("## 統計検証（walk-forward検証）")
    show_warning("株価データがないため、統計検証データを表示できません。")

# --- 総括の注意書き ----------------------------------------------------------
render_disclaimer_footer(recommended_row, peer_result)
