"""相川担当：補助判断表示画面（pages/7_decision_support.py）"""

from __future__ import annotations

import streamlit as st

from logic.csv_export import save_csv
from logic.error_utils import show_error, show_warning
from logic.demo_trade import ACTION_LABELS

st.title("補助判断")

# --- 注意事項（最優先で目立つ位置に表示） -----------------------------------
st.error(
    "⚠️ 本結果は過去データに基づくシミュレーションであり、"
    "将来の利益を保証するものではありません。売買手数料・税金は考慮していません。"
)

result_df = st.session_state.get("demo_trade_result_df")

if result_df is None or result_df.empty:
    show_warning("分析結果がありません。先に「デモトレード結果」画面を開いて計算を実行してください。")
    st.stop()

stance = st.session_state.get("investment_stance", "")
if stance:
    st.caption(f"立場：{stance}")

# --- ハイライト表示 --------------------------------------------------------
st.subheader("比較的良い結果だった投資行動")

best_row = result_df.loc[result_df["AvgReturn"].idxmax()]
best_label = ACTION_LABELS.get(best_row["Action"], best_row["Action"])

st.success(
    f"「{best_label}」（経過{int(best_row['Horizon'])}営業日）が"
    f"平均リターンで最も良い結果でした（{best_row['AvgReturn']:+.2%}、勝率{best_row['WinRate']:.0%}）。"
)
st.caption("※平均リターン基準の参考情報です。勝率や最大ドローダウンも下記で必ず確認してください。")

# --- 各投資行動の根拠テキスト -----------------------------------------------
st.subheader("各投資行動の結果（根拠）")
for _, row in result_df.iterrows():
    label = ACTION_LABELS.get(row["Action"], row["Action"])
    st.info(
        f"{label}（経過{int(row['Horizon'])}営業日）："
        f"平均リターン {row['AvgReturn']:+.2%} / 勝率 {row['WinRate']:.0%} / "
        f"最大損失 {row['MaxLoss']:+.2%} / 最大ドローダウン {row['MaxDrawdown']:+.2%} / "
        f"平均保有日数 {row['AvgHoldDays']:.1f}日"
    )

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