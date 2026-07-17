"""岩間担当：walk-forward検証結果の表示ロジック（pages/_validation_view.py）。

ファイル名を`_`始まりにしているため、Streamlitのナビゲーション（app.pyのst.navigation）には
現れない（app.pyがpages/配下を明示的にst.Pageで列挙する構成のため、そもそも対象にもならない）。
7_decision_support.pyの既存の補助判断カード描画部分から分離した関数として実装しており、
将来的に別ページへ移動する場合はこのモジュールをそのまま呼び出し元だけ差し替えればよい。
カードデザイン用のCSSはpages/_decision_support_view.pyのinject_styles()で注入したものを
共有して使う（同一ページ内なので再注入は不要）。
"""

from __future__ import annotations

import streamlit as st

from logic.error_utils import show_warning
from logic.ticker_lookup import get_company_name

DIRECTION_LABELS = {"up": "上昇", "down": "下落", "flat": "横ばい"}

POINT_COLUMN_LABELS = {
    "RefDate": "検証地点（基準日）",
    "PredictedDirection": "想定方向",
    "ActualDirection": "実際方向",
    "Hit": "一致",
    "ActualReturn": "実際リターン",
    "SimilarSampleSize": "類似局面件数",
}

PEER_COLUMN_LABELS = {
    "Ticker": "銘柄名",
    "Points": "検証地点数",
    "HitRate": "的中率",
    "AvgReturn": "平均リターン",
}


def hit_rate_display(result: dict | None) -> str:
    """単体銘柄検証結果から「過去の的中率」の表示用文字列を返す（メインカードから呼び出す用）。

    resultがNone、または的中率が算出できなかった場合は「算出不可」を返す
    （例外は投げない）。
    """
    if result is None or result.get("hit_rate") is None:
        return "算出不可"
    return f"{result['hit_rate']:.0%}"


def _stat_metric_row_html(result: dict) -> str:
    """的中率・平均リターン・戦略リターンのp値・的中率のp値の4項目を指標タイルとして表示するHTMLを返す。

    戦略リターンのp値・的中率のp値には、目標サンプル数未達の場合「参考値」の注記を残す。
    """
    if result["insufficient_sample"] and result["hit_rate"] is None:
        return '<div class="ds-stat-note">⚠️ 検証に必要なデータが不足しているため、統計検証できませんでした。</div>'

    hit_rate_html = (
        '<div class="ds-metric-tile ds-metric-green">'
        '<div class="ds-metric-tile-label">的中率</div>'
        f'<div class="ds-metric-tile-value">{result["hit_rate"]:.1%}</div></div>'
    )
    avg_return_html = (
        '<div class="ds-metric-tile ds-metric-blue">'
        '<div class="ds-metric-tile-label">平均リターン</div>'
        f'<div class="ds-metric-tile-value">{result["avg_return"]:+.2%}</div></div>'
    )

    notes = []
    if result["insufficient_sample"]:
        p_value_label, p_value_text = "p値（戦略リターン）", "算出不可"
        hit_p_value_label, hit_p_value_text = "p値（的中率）", "算出不可"
        notes.append("⚠️ サンプル不足のため統計検証不可（帰無仮説の検定にはサンプル数5以上が必要です）")
    else:
        if result["p_value"] is None:
            p_value_label, p_value_text = "p値（戦略リターン）", "算出不可"
        elif result["p_value_is_reference"]:
            p_value_label, p_value_text = "p値（戦略リターン・参考値）", f'{result["p_value"]:.3f}'
        else:
            p_value_label, p_value_text = "p値（戦略リターン）", f'{result["p_value"]:.3f}'

        if result.get("hit_rate_p_value") is None:
            hit_p_value_label, hit_p_value_text = "p値（的中率）", "算出不可"
        elif result["p_value_is_reference"]:
            hit_p_value_label, hit_p_value_text = "p値（的中率・参考値）", f'{result["hit_rate_p_value"]:.3f}'
        else:
            hit_p_value_label, hit_p_value_text = "p値（的中率）", f'{result["hit_rate_p_value"]:.3f}'

        if result["p_value_is_reference"]:
            notes.append("ℹ️ 目標サンプル数に未達のため、p値は参考値です")

    p_value_html = (
        '<div class="ds-metric-tile ds-metric-amber">'
        f'<div class="ds-metric-tile-label">{p_value_label}</div>'
        f'<div class="ds-metric-tile-value">{p_value_text}</div></div>'
    )
    hit_p_value_html = (
        '<div class="ds-metric-tile ds-metric-purple">'
        f'<div class="ds-metric-tile-label">{hit_p_value_label}</div>'
        f'<div class="ds-metric-tile-value">{hit_p_value_text}</div></div>'
    )

    # それぞれのp値が何を検定した値なのかを明記する注記（ユーザーが誤解しないように）。
    notes.append(
        "ℹ️ 「p値（戦略リターン）」は、予測方向に従って売買した場合の戦略リターンが0と異なるかを"
        "検定したものです。「p値（的中率）」は、方向の的中率が偶然（50%）と異なるかを"
        "検定したものです。"
    )

    row_html = f'<div class="ds-metric-row">{hit_rate_html}{avg_return_html}{p_value_html}{hit_p_value_html}</div>'
    notes_html = "".join(f'<div class="ds-stat-note">{note}</div>' for note in notes)
    return row_html + notes_html


def render_single_stock_validation_card(result: dict) -> None:
    """単体銘柄でのwalk-forward検証結果（新規実装1）をカード形式で表示する。

    「この銘柄で当たるか」を示すセクション。業種横断検証（新規実装2）とは
    意味が異なる指標のため、呼び出し元で別カードとして分離すること。
    """
    with st.container(border=True):
        st.markdown(
            '<div class="ds-stat-header">'
            '<div class="ds-stat-icon ds-stat-icon-green">📈</div>'
            '<div><div class="ds-stat-title">単体銘柄での検証（この銘柄で当たるか）</div>'
            '<div class="ds-stat-desc">対象期間内の複数時点に遡り、各時点より前のデータだけで'
            "類似局面抽出とデモトレードを行い、実際のその後の値動きと照合した結果です。</div></div></div>",
            unsafe_allow_html=True,
        )

        if result["actual_points"] == 0:
            show_warning("検証に必要なデータが不足しているため、検証できませんでした。")
            return

        if result["adjustment_message"]:
            st.caption(result["adjustment_message"])
        st.caption(f"検証地点数：{result['actual_points']}地点（目標{result['requested_points']}地点中）")
        st.markdown(_stat_metric_row_html(result), unsafe_allow_html=True)

        with st.expander("検証地点ごとの明細"):
            points_df = result["points"]
            if points_df.empty:
                st.caption("表示できる明細がありません。")
            else:
                display_df = points_df.copy()
                display_df["PredictedDirection"] = display_df["PredictedDirection"].map(DIRECTION_LABELS)
                display_df["ActualDirection"] = display_df["ActualDirection"].map(DIRECTION_LABELS)
                display_df["Hit"] = display_df["Hit"].map({True: "○", False: "×"})
                display_df["ActualReturn"] = display_df["ActualReturn"].map(lambda x: f"{x:+.2%}")
                display_df = display_df.rename(columns=POINT_COLUMN_LABELS)
                st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_peer_validation_card(result: dict) -> None:
    """業種横断でのwalk-forward検証結果（新規実装2）をカード形式で表示する。

    「手法自体に再現性があるか」を示すセクション。単体銘柄検証（新規実装1）と
    混同されないよう、呼び出し元で別カードとして分離すること。
    明細テーブルの銘柄コードは、表示直前にget_company_nameで銘柄名に変換する
    （内部の取得・フィルタ処理は銘柄コードのまま）。
    """
    with st.container(border=True):
        st.markdown(
            '<div class="ds-stat-header">'
            '<div class="ds-stat-icon ds-stat-icon-blue">🏢</div>'
            '<div><div class="ds-stat-title">業種横断での検証（手法自体に再現性があるか）</div>'
            '<div class="ds-stat-desc">対象銘柄に加え、同業種・近接規模の銘柄にも同じwalk-forward検証を行い、'
            "社をまたいで結果を合算しています。</div></div></div>",
            unsafe_allow_html=True,
        )

        if result["company_count"] == 0:
            show_warning("検証に必要なデータが不足しているため、検証できませんでした。")
            return

        st.caption(
            f"サンプル数{result['company_count']}社（目標{result['target_sample_size']}社中）、"
            f"合計検証地点数：{result['total_points']}地点"
        )
        st.markdown(_stat_metric_row_html(result), unsafe_allow_html=True)
        st.markdown(
            '<div class="ds-stat-note">ℹ️ このp値は「投資行動の判定（推奨/検討可/非推奨）」には'
            "使用していません。上部の結論カードにある「業種内整合性」の判定材料として、"
            "参考情報としてのみ表示しています。</div>",
            unsafe_allow_html=True,
        )

        with st.expander("銘柄ごとの明細"):
            per_company_df = result["per_company"]
            if per_company_df.empty:
                st.caption("表示できる明細がありません。")
            else:
                display_df = per_company_df.copy()
                display_df["Ticker"] = display_df["Ticker"].map(get_company_name)
                display_df["HitRate"] = display_df["HitRate"].map(lambda x: f"{x:.1%}")
                display_df["AvgReturn"] = display_df["AvgReturn"].map(lambda x: f"{x:+.2%}")
                display_df = display_df.rename(columns=PEER_COLUMN_LABELS)
                st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_validation_detail_section(single_stock_result: dict, peer_result: dict) -> None:
    """統計検証セクション全体（単体銘柄・業種横断の2カード）を表示する。

    単体銘柄の検証結果（新規実装1）と業種横断の検証結果（新規実装2）は
    意味が異なる指標のため、カードを分けて表示する。
    """
    st.markdown("## 統計検証（walk-forward検証）")
    st.caption("偶然の結果ではなく、再現性があるかを検証するために、過去の複数時点に遡って検証しています。")
    # 本検証が⑤画面の許容幅設定を使わない理由、および全行動の判定にbuy_todayの検証結果を
    # 代表値として使っている旨を、ユーザーの誤解を防ぐためあらかじめ明記する
    # （判定ロジック・検証ロジック自体は変更しない、表示専用の注記）。
    st.caption(
        "本検証は、ユーザーが⑤画面で設定した許容幅ではなく、固定の標準的な許容幅を用いて"
        "実施しています。これは、条件によって「たまたま」検証をパスするのではなく、"
        "手法自体の頑健性・再現性を確認するためです。"
    )
    st.caption(
        "本検証は、新規購入（buy_today）を対象に行った方向予測の検証です。保有継続・"
        "一部売却・損切りなど他の投資行動についても、この検証結果を代表値として判定の"
        "裏付けに使用しています。"
    )

    render_single_stock_validation_card(single_stock_result)
    render_peer_validation_card(peer_result)