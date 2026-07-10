"""pages/_decision_support_view.py の render_conclusion_card に関する簡易テスト。

全行動が非推奨（RATING_NOT_RECOMMENDED）の場合に「おすすめ行動」タイルが
出ないこと・警告文言が出ることと、推奨/検討可のケースは従来通りの表示に
なることの回帰確認を行う。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from logic.decision_rating import (
    RATING_CONSIDERABLE,
    RATING_NOT_RECOMMENDED,
    RATING_RECOMMENDED,
    SELL_FIXED_RATING,
    SELL_FIXED_RISK_LEVEL,
)
from pages._decision_support_view import render_comparison_table, render_conclusion_card


def _make_row(action: str, rating: str, avg_return: float = 0.01, win_rate: float = 0.5) -> pd.Series:
    return pd.Series({
        "Action": action, "Horizon": 5, "AvgReturn": avg_return, "WinRate": win_rate,
        "RiskLevel": "中", "Rating": rating,
    })


def _make_ranked_df(rows: list[pd.Series]) -> pd.DataFrame:
    df = pd.DataFrame(rows).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df


def _markdown_html(mock_st) -> str:
    return "".join(call.args[0] for call in mock_st.markdown.call_args_list)


class RenderConclusionCardRatingBranchTest(unittest.TestCase):
    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_all_not_recommended_shows_warning_without_recommendation_tile(self, mock_st, mock_show_warning):
        row = _make_row("hold", RATING_NOT_RECOMMENDED)
        ranked_df = _make_ranked_df([row])

        render_conclusion_card(row, ranked_df, "これから購入する")

        mock_show_warning.assert_called_once()
        warning_text = mock_show_warning.call_args[0][0]
        self.assertIn("推奨できる投資行動がありませんでした", warning_text)

        html = _markdown_html(mock_st)
        self.assertNotIn("おすすめ行動", html)
        self.assertIn("参考（非推奨）", html)

    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_recommended_rating_still_shows_recommendation_tile(self, mock_st, mock_show_warning):
        row = _make_row("buy_today", RATING_RECOMMENDED)
        ranked_df = _make_ranked_df([row])

        render_conclusion_card(row, ranked_df, "これから購入する")

        mock_show_warning.assert_not_called()
        html = _markdown_html(mock_st)
        self.assertIn("おすすめ行動", html)
        self.assertNotIn("参考（非推奨）", html)

    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_considerable_rating_still_shows_recommendation_tile(self, mock_st, mock_show_warning):
        row = _make_row("wait", RATING_CONSIDERABLE)
        ranked_df = _make_ranked_df([row])

        render_conclusion_card(row, ranked_df, "これから購入する")

        mock_show_warning.assert_not_called()
        html = _markdown_html(mock_st)
        self.assertIn("おすすめ行動", html)
        self.assertNotIn("参考（非推奨）", html)

    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_sector_validity_label_still_shown_when_not_recommended(self, mock_st, mock_show_warning):
        row = _make_row("hold", RATING_NOT_RECOMMENDED)
        ranked_df = _make_ranked_df([row])

        render_conclusion_card(row, ranked_df, "これから購入する", sector_validity_label="整合")

        html = _markdown_html(mock_st)
        self.assertIn("業種内整合性", html)


class RenderComparisonTableSellCellsTest(unittest.TestCase):
    def _sell_row_df(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "Rank": 1, "Action": "sell", "Horizon": None, "AvgReturn": 0.03,
            "WinRate": None, "RiskLevel": SELL_FIXED_RISK_LEVEL, "Rating": SELL_FIXED_RATING,
        }])

    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_sell_row_shows_dash_instead_of_pill(self, mock_st, mock_show_warning):
        render_comparison_table(self._sell_row_df())

        html = _markdown_html(mock_st)
        # RiskLevel・Rating・WinRateがすべてダッシュのプレーンテキストで、色分けピル
        # （CSSクラスが存在しないds-pill-risk-－や、空文字列由来の空ピル）にならないこと
        self.assertIn(f"<td>{SELL_FIXED_RISK_LEVEL}</td><td>{SELL_FIXED_RISK_LEVEL}</td>", html)
        self.assertNotIn(f"ds-pill-risk-{SELL_FIXED_RISK_LEVEL}", html)
        self.assertNotIn('class="ds-pill ds-pill-rating-not_recommended"></span>', html)

    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_sell_row_rank_cell_is_dash_not_rank_number(self, mock_st, mock_show_warning):
        # sellは採点・順位付けの対象外のため、Rank列に振られた通し番号（例："10位"）
        # ではなくダッシュを表示する
        df = self._sell_row_df()
        df.loc[0, "Rank"] = 10

        render_comparison_table(df)

        html = _markdown_html(mock_st)
        self.assertNotIn("10位", html)
        self.assertIn(f"<td>{SELL_FIXED_RISK_LEVEL}</td>", html)

    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_sell_row_shows_ranking_exclusion_note(self, mock_st, mock_show_warning):
        render_comparison_table(self._sell_row_df())

        html = _markdown_html(mock_st)
        self.assertIn("順位・評価（ランキング）の対象外", html)

    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_no_sell_row_omits_ranking_exclusion_note(self, mock_st, mock_show_warning):
        df = pd.DataFrame([{
            "Rank": 1, "Action": "buy_today", "Horizon": 5, "AvgReturn": 0.03,
            "WinRate": 0.6, "RiskLevel": "低", "Rating": RATING_RECOMMENDED,
        }])

        render_comparison_table(df)

        html = _markdown_html(mock_st)
        self.assertNotIn("順位・評価（ランキング）の対象外", html)

    @patch("pages._decision_support_view.show_warning")
    @patch("pages._decision_support_view.st")
    def test_sell_row_does_not_raise(self, mock_st, mock_show_warning):
        try:
            render_comparison_table(self._sell_row_df())
        except Exception as exc:  # noqa: BLE001
            self.fail(f"sell行の比較表描画で例外が発生した: {exc}")


if __name__ == "__main__":
    unittest.main()
