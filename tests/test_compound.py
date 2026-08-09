"""Tests for compound urban-stress scoring helpers."""

import pandas as pd

from dhakagraph.compound import percentile_score


def test_percentile_score_is_bounded_and_ordered() -> None:
    scores = percentile_score(pd.Series([10, 30, 20]))
    assert scores.between(0, 100).all()
    assert scores.iloc[1] > scores.iloc[2] > scores.iloc[0]
