import pytest

from forge.calibration import agreement_metrics, weighted_kappa


def test_kappa_is_one_for_perfect_agreement():
    assert weighted_kappa([1, 3, 5, 4], [1, 3, 5, 4]) == pytest.approx(1.0)


def test_kappa_punishes_big_disagreements_more():
    close = weighted_kappa([1, 2, 3, 4, 5], [2, 3, 4, 5, 4])
    far = weighted_kappa([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert far < 0 < close < 1


def test_kappa_matches_a_hand_computed_case():
    # Items scored (1, 2) and (2, 1). Weighted disagreement observed: 2 x (1/4)^2 = 1/8.
    # Expected by chance: each of the 4 cells has 0.5, two of them weigh 1/16, so 1/16.
    # kappa = 1 - (1/8) / (1/16) = -1: worse than chance.
    assert weighted_kappa([1, 2], [2, 1]) == pytest.approx(-1.0)


def test_agreement_metrics():
    m = agreement_metrics(human=[4, 3, 5, 2], judge=[4, 4, 5, 4])
    assert m["exact"] == 0.5
    assert m["within_1"] == 0.75
    assert m["mean_difference"] == 0.75  # the judge scores higher on average
