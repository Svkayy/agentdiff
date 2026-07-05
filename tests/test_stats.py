"""Unit tests for the significance tests in agentdiff/stats.py."""
from agentdiff.stats import (
    benjamini_hochberg,
    cliffs_delta,
    cohens_h,
    is_significant,
    mann_whitney_pvalue,
    proportion_delta_ci,
    two_proportion_pvalue,
)


def test_two_proportion_identical_not_significant():
    assert two_proportion_pvalue(10, 20, 10, 20) == 1.0  # same rate
    assert two_proportion_pvalue(20, 20, 20, 20) == 1.0  # both all-success
    assert two_proportion_pvalue(0, 20, 0, 20) == 1.0    # both all-failure


def test_two_proportion_large_swing_significant():
    p = two_proportion_pvalue(20, 20, 0, 20)  # 100% → 0%
    assert p < 0.001
    assert is_significant(p)


def test_two_proportion_small_n_not_significant():
    # 2/2 vs 1/2 is a big effect but too few samples to be significant.
    p = two_proportion_pvalue(2, 2, 1, 2)
    assert not is_significant(p)


def test_two_proportion_empty():
    assert two_proportion_pvalue(0, 0, 1, 5) == 1.0


def test_proportion_effect_and_interval_are_signed_candidate_minus_baseline():
    ci = proportion_delta_ci(20, 20, 0, 20)
    assert ci is not None
    assert ci[0] <= -1.0
    assert ci[1] < 0.0
    h = cohens_h(20, 20, 0, 20)
    assert h is not None
    assert h < 0.0


def test_mann_whitney_identical_not_significant():
    assert mann_whitney_pvalue([1, 1, 1, 1], [1, 1, 1, 1]) == 1.0


def test_mann_whitney_separated_significant():
    p = mann_whitney_pvalue([2] * 20, [1] * 20)
    assert p < 0.05
    assert is_significant(p)


def test_mann_whitney_small_n_not_significant():
    p = mann_whitney_pvalue([2, 2], [1, 1])
    assert not is_significant(p)


def test_mann_whitney_empty():
    assert mann_whitney_pvalue([], [1, 2, 3]) == 1.0


def test_cliffs_delta_signed_candidate_minus_baseline():
    assert cliffs_delta([2, 2], [1, 1]) == -1.0
    assert cliffs_delta([1, 1], [2, 2]) == 1.0
    assert cliffs_delta([], [1]) is None


# ---------------------------------------------------------------------------
# Task 7: Benjamini-Hochberg correction.
# ---------------------------------------------------------------------------

def test_benjamini_hochberg_reference_case():
    assert benjamini_hochberg([0.01, 0.02, 0.03, 0.04]) == [0.04, 0.04, 0.04, 0.04]


def test_benjamini_hochberg_empty():
    assert benjamini_hochberg([]) == []


def test_benjamini_hochberg_monotone_and_clipped():
    # Unsorted input with a value that would exceed 1.0 before clipping.
    adjusted = benjamini_hochberg([0.5, 0.9, 0.2, 0.01])
    assert all(0.0 <= p <= 1.0 for p in adjusted)
    # BH-adjusted p-values are monotone non-decreasing when read in raw-p rank order.
    order = sorted(range(len(adjusted)), key=lambda i: [0.5, 0.9, 0.2, 0.01][i])
    ranked = [adjusted[i] for i in order]
    assert ranked == sorted(ranked)


def test_benjamini_hochberg_single_value_unchanged():
    assert benjamini_hochberg([0.03]) == [0.03]
