from unittest import TestCase

import numpy as np

from flowback.poll.tasks import quadratic_programming_solver


class TestQuadraticProgrammingSolver(TestCase):
    def assert_solver_result(
        self,
        covariance_matrix: np.ndarray,
        expected_solution: np.ndarray,
        expected_optimal_value: float,
    ) -> None:
        solution, optimal_value, _ = quadratic_programming_solver(covariance_matrix)

        np.testing.assert_allclose(solution, expected_solution, rtol=1e-7, atol=1e-8)
        np.testing.assert_allclose(
            optimal_value,
            expected_optimal_value,
            rtol=1e-7,
            atol=1e-8,
        )

    def test_equally_weights_two_predictors_with_zero_covariance(self):
        self.assert_solver_result(
            covariance_matrix=np.zeros((2, 2)),
            expected_solution=np.array([0.5, 0.5]),
            expected_optimal_value=0.0,
        )

    def test_equally_weights_three_predictors_with_zero_covariance(self):
        self.assert_solver_result(
            covariance_matrix=np.zeros((3, 3)),
            expected_solution=np.array([0.33333333, 0.33333333, 0.33333333]),
            expected_optimal_value=0.0,
        )

    def test_excludes_predictor_with_nonzero_variance(self):
        self.assert_solver_result(
            covariance_matrix=np.diag([0.0, 0.0, 1.0]),
            expected_solution=np.array(
                [0.5, 0.5, 1.87483202e-25],
            ),
            expected_optimal_value=3.514995119900657e-50,
        )

    def test_indefinite_covariance_matrix_still_returns_a_solution(self):
        # eigenvalues [-1, 1]: genuinely concave, not float noise around PSD.
        # Entries stay within the valid [0, 1] range. Solver silently
        # swallows this (prints "Concave minimization") and returns None
        # instead of solving or raising. RED until the concave branch
        # (tasks.py:840-843) actually does something.
        solution, optimal_value, _ = quadratic_programming_solver(
            np.array([[0.0, 1.0], [1.0, 0.0]])
        )
        self.assertIsNotNone(solution)
        self.assertIsNotNone(optimal_value)

    def test_covariance_matrix_entry_above_one_is_rejected(self):
        with self.assertRaises(ValueError):
            quadratic_programming_solver(np.array([[1.0, 2.0], [2.0, 1.0]]))

    def test_nan_covariance_matrix_does_not_raise(self):
        # NaN entries (e.g. from a predictor's missing bets leaking into
        # np.cov) blow up before the try/except even starts, since
        # cp.quad_form's symmetry check fails on nan != nan. RED: raises
        # ValueError uncaught instead of being handled.
        quadratic_programming_solver(
            np.array([[1.0, np.nan], [np.nan, 1.0]])
        )
