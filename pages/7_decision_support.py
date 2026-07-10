"""相川担当：補助判断表示画面（pages/7_decision_support.py）"""

from __future__ import annotations

import streamlit as st

from logic.csv_export import build_decision_support_export
from logic.decision_rating import (
    add_action_ratings,
    judge_sector_validity,
    rank_rated_actions,
    select_recommended_action,
)
from logic.error_utils import show_warning
from logic.indicators import calc_hv
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

if "demo_trade_result_df" not in st.session_state:
    show_warning("分析結果がありません。先に「デモトレード結果」画面を開いて計算を実行してください。")
    st.stop()

result_df = st.session_state.get("demo_trade_result_df")

if result_df is None or result_df.empty:
    show_warning(
        "デモトレードが実行できなかったため、補助判断の分析もできません。"
        "「過去類似局面」画面で条件を見直し（過去データ不足の場合は分析期間を延ばす、"
        "許容幅の問題の場合は許容幅を広げる）、再度お試しください。"
    )
    st.stop()

stance = st.session_state.get("investment_stance", "") or "―"

# --- walk-forward検証（統計検証）の計算 -------------------------------------
# 判定ロジックの安全装置（単体銘柄の的中率・方向一致によるキャップ）と、下部の統計検証カードの両方で使う。
#
# 【再計算の抑制】このページ内での他の操作（CSVダウンロードボタン押下等）でも
# Streamlitはスクリプト全体を再実行するため、何も対策しないと業種横断検証（最大20社分の
# 類似局面探索＋デモトレード）まで毎回フルで再計算されてしまう。
# 「分析開始」に相当する条件（銘柄・期間・立場）が前回と変わっていない間はsession_stateの
# キャッシュを使い回し、条件が変わったときだけ再計算する。
price_df = st.session_state.get("stock_price_df")
ticker = st.session_state.get("selected_ticker")
period = st.session_state.get("selected_period", "3年")
peer_fetch_period = "10年" if period == "任意" else period

single_stock_result = None
peer_result = None
if price_df is not None and not price_df.empty and ticker:
    validation_key = (ticker, period, stance)
    if (
        st.session_state.get("validation_cache_key") == validation_key
        and "validation_cache_value" in st.session_state
    ):
        single_stock_result, peer_result = st.session_state["validation_cache_value"]
    else:
        with st.spinner("検証データを計算中..."):
            single_stock_result = run_single_stock_validation(price_df)
            peer_result = run_peer_universe_validation(ticker, price_df, peer_fetch_period)
        st.session_state["validation_cache_key"] = validation_key
        st.session_state["validation_cache_value"] = (single_stock_result, peer_result)

single_stock_hit_rate = single_stock_result.get("hit_rate") if single_stock_result is not None else None
single_stock_avg_return = single_stock_result.get("avg_return") if single_stock_result is not None else None
single_stock_p_value = single_stock_result.get("p_value") if single_stock_result is not None else None
single_stock_p_value_is_reference = (
    single_stock_result.get("p_value_is_reference", False) if single_stock_result is not None else False
)
single_stock_insufficient_sample = (
    single_stock_result.get("insufficient_sample", True) if single_stock_result is not None else True
)
peer_avg_return = peer_result.get("avg_return") if peer_result is not None else None
peer_p_value = peer_result.get("p_value") if peer_result is not None else None
peer_sample_size = peer_result.get("company_count", 0) if peer_result is not None else 0

# 対象銘柄の年率ヒストリカルボラティリティ（直近値）。リスク判定（risk_level）を
# 銘柄自身の値動きの大きさ基準にするために使う。算出不可の場合はNone（固定閾値にフォールバック）
latest_hv = None
if price_df is not None and not price_df.empty:
    hv_series = calc_hv(price_df)["HV"].dropna()
    if not hv_series.empty:
        latest_hv = float(hv_series.iloc[-1])

# --- 投資行動の判定（推奨/検討可/非推奨） -----------------------------------
rated_df = add_action_ratings(
    result_df, latest_hv,
    single_stock_hit_rate, single_stock_avg_return, single_stock_p_value, single_stock_p_value_is_reference,
    single_stock_insufficient_sample, peer_avg_return,
)
ranked_df = rank_rated_actions(rated_df)
recommended_row = select_recommended_action(ranked_df)

# 単体銘柄検証がサンプル不足の場合、判定ロジックには組み込まない（apply_significance_cap参照）ため、
# 統計的有意性が未確認である旨をここで注意書きとして表示する
if single_stock_insufficient_sample:
    st.caption("⚠️ サンプル不足のため統計的有意性は未確認です（上記の判定はp値による裏付けができていません）。")

# --- 業種内整合性（既存の推奨/検討可/非推奨とは独立した別枠の補足情報） -------------
sector_validity_label = judge_sector_validity(peer_p_value, single_stock_avg_return, peer_avg_return, peer_sample_size)

# --- 結論カード -------------------------------------------------------------
render_conclusion_card(recommended_row, ranked_df, stance, sector_validity_label)

# --- 投資行動の比較表 --------------------------------------------------------
render_comparison_table(ranked_df)

# --- 判断の切り口 ------------------------------------------------------------
render_decision_angles(ranked_df)

# --- CSVエクスポート --------------------------------------------------------
# 比較表と同じ日本語ラベル・整形済み数値（%表示等）で出力する。
# 生データ（result_df）ではなく、順位・リスク・評価まで含めたranked_dfを使うことで、
# 画面を見なくてもCSV単体で判断材料になる内容にしている。
export_csv_text = build_decision_support_export(ranked_df, st.session_state.get("selected_ticker", ""), stance)

st.download_button(
    label="分析結果をCSVで保存",
    data=export_csv_text.encode("utf-8-sig"),
    file_name="補助判断結果.csv",
    mime="text/csv",
    disabled=not export_csv_text,
)

# --- 統計検証セクション -------------------------------------------------------
if single_stock_result is not None and peer_result is not None:
    render_validation_detail_section(single_stock_result, peer_result)
else:
    st.markdown("## 統計検証（walk-forward検証）")
    show_warning("株価データがないため、統計検証データを表示できません。")

# --- 総括の注意書き ----------------------------------------------------------
render_disclaimer_footer(recommended_row, single_stock_result, peer_result)