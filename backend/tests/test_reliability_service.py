import pytest

from app.core.config import Settings
from app.services.reliability_service import (
    ScoreWeights,
    calculate_reliability_score,
    default_weights,
)

W = ScoreWeights(ocr=0.3, ai=0.5, validation=0.2)


def test_all_three_inputs():  # US-05 AC1
    assert calculate_reliability_score(0.8, 0.9, True, W) == pytest.approx(0.89)


def test_missing_ocr_rescales_remaining_weights():  # US-05 AC2
    # (0.9 * 0.5 + 1.0 * 0.2) / 0.7
    assert calculate_reliability_score(None, 0.9, True, W) == pytest.approx(0.9286, abs=1e-4)


def test_failed_validation_lowers_the_score():
    assert calculate_reliability_score(0.8, 0.9, False, W) == pytest.approx(0.69)


def test_best_and_worst_cases():
    assert calculate_reliability_score(1.0, 1.0, True, W) == 1.0
    assert calculate_reliability_score(0.0, 0.0, False, W) == 0.0


@pytest.mark.parametrize("ocr, ai", [(1.2, 0.9), (-0.1, 0.9), (0.8, 1.5)])
def test_out_of_range_inputs_are_rejected(ocr, ai):
    with pytest.raises(ValueError):
        calculate_reliability_score(ocr, ai, True, W)


def test_weights_that_do_not_sum_to_one_are_rejected():
    with pytest.raises(ValueError):
        Settings(weight_ocr=0.9)


def test_default_weights_match_the_agreed_values():
    assert default_weights() == W