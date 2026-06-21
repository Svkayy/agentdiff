"""Unit tests for the significance tests in agentdiff/stats.py."""
from agentdiff.stats import (
    is_significant, mann_whitney_pvalue, two_proportion_pvalue,
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
