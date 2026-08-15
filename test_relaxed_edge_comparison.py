import math

import pytest

from evaluate_relaxed_edge_smoke import (
    edge_joint_negative_log_likelihood,
)


def test_edge_jnll_for_absent_edge_uses_existence_probability():
    score = edge_joint_negative_log_likelihood(
        exist_prob=0.2,
        distance_mean=3.0,
        distance_var=4.0,
        oracle_edge_exists=False,
        oracle_edge_distance=None,
    )

    assert score == pytest.approx(-math.log(0.8))


def test_edge_jnll_for_existing_edge_scores_joint_probability_and_distance():
    score = edge_joint_negative_log_likelihood(
        exist_prob=0.8,
        distance_mean=3.0,
        distance_var=4.0,
        oracle_edge_exists=True,
        oracle_edge_distance=5.0,
    )

    expected = (
        -math.log(0.8)
        + 0.5 * math.log(2.0 * math.pi * 4.0)
        + ((5.0 - 3.0) ** 2) / (2.0 * 4.0)
    )
    assert score == pytest.approx(expected)
