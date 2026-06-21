"""Lightweight classical significance tests (no scipy dependency).

Used by the comparison engine to decide whether a baseline-vs-candidate behavioral
difference is statistically real given the sample sizes, rather than relying on the
effect size alone. All p-values are two-sided.
"""
import math
from collections.abc import Sequence

_ALPHA = 0.05


def _normal_sf(z: float) -> float:
    """Survival function (1 - CDF) of the standard normal via erf."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _two_sided_p_from_z(z: float) -> float:
    return max(0.0, min(1.0, 2.0 * _normal_sf(abs(z))))


def two_proportion_pvalue(
    b_success: int, b_n: int, c_success: int, c_n: int
) -> float:
    """Two-proportion z-test p-value for baseline vs candidate success rates.

    Returns 1.0 (not significant) when either side is empty or there is no
    pooled variance (both sides all-success or all-failure).
    """
    if b_n <= 0 or c_n <= 0:
        return 1.0
    p_pool = (b_success + c_success) / (b_n + c_n)
    if p_pool <= 0.0 or p_pool >= 1.0:
        return 1.0
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / b_n + 1.0 / c_n))
    if se == 0.0:
        return 1.0
    z = ((c_success / c_n) - (b_success / b_n)) / se
    return _two_sided_p_from_z(z)


def mann_whitney_pvalue(baseline: Sequence[float], candidate: Sequence[float]) -> float:
    """Mann-Whitney U test p-value (normal approximation, tie-corrected).

    Compares two distributions of per-trajectory counts. Returns 1.0 when either
    sample is empty or the data carry no information (all values identical).
    """
    n1, n2 = len(baseline), len(candidate)
    if n1 == 0 or n2 == 0:
        return 1.0

    combined = [(v, 0) for v in baseline] + [(v, 1) for v in candidate]
    combined.sort(key=lambda t: t[0])

    # Average ranks for ties.
    ranks = [0.0] * len(combined)
    i = 0
    tie_term = 0.0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # ranks are 1-based
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        t = j - i + 1
        if t > 1:
            tie_term += t ** 3 - t
        i = j + 1

    r1 = sum(rank for rank, (_, g) in zip(ranks, combined) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0

    n = n1 + n2
    # Variance with tie correction.
    var = (n1 * n2 / 12.0) * ((n + 1) - tie_term / (n * (n - 1))) if n > 1 else 0.0
    if var <= 0.0:
        return 1.0
    sigma = math.sqrt(var)
    # Continuity correction.
    z = (u1 - mu)
    z = (z + 0.5 if z < 0 else z - 0.5) / sigma
    return _two_sided_p_from_z(z)


def is_significant(p_value: float, alpha: float = _ALPHA) -> bool:
    return p_value < alpha
