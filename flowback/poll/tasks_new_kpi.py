from typing import cast

from django.db.models import (
    Count,
    OuterRef,
    F,
    QuerySet,
    Subquery,
    Window
)
from django.db.models.functions import Random, RowNumber
from numpy.typing import NDArray

from flowback.group.models import (
    Group,
    GroupKPI,
)
from flowback.poll.phases import (
    PollProposalKPI,
    PollProposalKPIBet,
    PollProposalKPIVote,
)

from flowback.poll.services.prediction import longest_poll_prediction_kpi_group_users
import numpy as np
import cvxpy as cp
import logging

logger = logging.getLogger(__name__)

def newer_kpi_betting(group: Group, kpi: GroupKPI) -> dict[int, float] | None:
    """
    This code was primarily written by Loke Hagberg 2026-06-12
    This work was made possible by my wonderful best friend: Emil Svenberg

    Track record handling 1 (might be a second track record handling or more later)

    When calculating the combined probability, pick the largest set of participating predictors with longest (within some max number)
    and fully overlapping track records are there multiple, pick one uniformly randomly.

    Example: If 1 predictor has participated 3 times on winning polls, and 5 predictors has participated 2 times, then this calculation
    takes just 1 predictor as input (with history of 3).

    It is valuable to know what the value of the determinant is, one can use numpy.linalg.det(matrix) for that purpose
    Save all determinants as how near one is to a singular matrix the more sensitive the method chosen is to input data

    Methods for calculating the combined probability

    The DCP rules in cvxpy require that the problem objective have one of two forms: Minimize(convex) or Maximize(concave)

    Long term TODO: Formal verification in an functional language (Haskell? F#? Scala?).
    Also a compiled program/binary with this can avoid numpy and cvxpy bloat in the rest of flowback without a microservice.
    """
    # Outcome value 1 for winning KPI values (based on plurality voting)
    # Outcome value 0 for other KPI values
    # Choose randomly when tied
    # History is added after evaluation. (HOW DO YOU FIND THE LONGEST HISTORY THEN?)
    # Only include KPIs from the winning proposal

    # Bet - Outcome
    # 1 predictor 1 poll
    # Example: values 1 and 2 get 5%; value 3 gets 90%
    # Winner in previous history: 3
    #
    # Outcome - Betts
    # [0.05, 0.05, -0.1]
    # Bet - Outcome
    # [-0.05, -0.05, 0.1]

    # 2 polls and 2 predictors
    # Poll and evaluation order should not matter
    # 0% 0% 100%
    # 33% 33% 34%
    # Evaluated as 3
    # After one poll
    # [0,    0,     0   ]
    # [0.33, 0.33, -0.66]
    # After two polls
    # 0% 0% 100%
    # 33% 33% 34%
    # Evaluated as 3
    # [0,    0,     0,    0,    0,     0   ]
    # [0.33, 0.33, -0.66, 0.33, 0.33, -0.66]
    # Something about NumPy arrays, unclear
    # Number of columns (3 in this case) should not matter
    # Number of rows should not matter

    logger.info("starting new kpi calculations")
    longest_users = longest_poll_prediction_kpi_group_users(group, users_filter=None)
    logger.info("longest_users: %s", longest_users)

    bets_qs = PollProposalKPIBet.objects.filter(
        created_by__in=longest_users,
    ).distinct()

    logger.info("bets_qs: %s", bets_qs)

    predictor_ids = sorted(set(bets_qs.values_list("created_by_id", flat=True)))
    logger.info("predictor_ids: %s", predictor_ids)

    winning_kpis_qs = get_winning_kpi_values(group, kpi)
    logger.info("winning_kpis_qs: %s", winning_kpis_qs)

    input_matrix = bet_outcome_matrix(bets_qs, winning_kpis_qs)
    logger.info("input_matrix: %s", input_matrix)

    if not predictor_ids or not input_matrix.size:
        return None
    if len(predictor_ids) == 1:
        return {predictor_ids[0]: 1.0}

    weights = method(input_matrix)
    logger.info("weights: %s", weights)
    if weights is None:
        logger.warning("KPI calculation got None")
        return None

    return dict(zip(predictor_ids, map(float, weights), strict=True))


def get_winning_kpi_values(group: Group, kpi: GroupKPI) -> QuerySet[PollProposalKPI]:
    winning_kpis = (
        PollProposalKPI.objects
        .filter(proposal__poll__created_by__group=group, kpi_value__kpi=kpi)
        .annotate(votes=Count("pollproposalkpivote"))
        .filter(votes__gt=0)
        .annotate(
            winner_rank=Window(
                expression=RowNumber(),
                partition_by=[F("proposal_id")],
                order_by=[
                    F("votes").desc(),
                    Random(),
                ],
            )
        )
        .filter(winner_rank=1)
    )

    return winning_kpis


def bet_outcome_matrix(
    bets: QuerySet[PollProposalKPIBet],
    winning_kpis: QuerySet[PollProposalKPI],
) -> NDArray[np.float64]:
    bets = list(bets)
    winning_kpis = list(winning_kpis.order_by("proposal_id", "kpi_value__kpi_id"))
    columns = [
        proposal_kpi
        for winner in winning_kpis
        for proposal_kpi in PollProposalKPI.objects.filter(
            proposal=winner.proposal,
            kpi_value__kpi=winner.kpi_value.kpi,
        ).order_by("id")
    ]
    bet_values = {
        (bet.created_by_id, bet.proposal_kpi_id): bet.weight / 100
        for bet in bets
    }
    predictor_ids = sorted({bet.created_by_id for bet in bets})
    matrix = np.array(
        [
            [
                bet_values.get((predictor_id, column.id), 0)
                - (column in winning_kpis)
                for column in columns
            ]
            for predictor_id in predictor_ids
        ],
        dtype=float,
    )

    return matrix


def method(input_matrix: NDArray[np.float64]) -> NDArray[np.float64] | None:
    # Might be always convex
    covariance_matrix = np.cov(input_matrix)
    result = quadratic_programming_solver(covariance_matrix)[0]
    return cast(NDArray[np.float64] | None, result)


def quadratic_programming_solver(
    covariance_matrix: NDArray[np.float64], test: bool = False
) -> list[NDArray[np.float64] | float | None]:
    if np.any((covariance_matrix < 0) | (covariance_matrix > 1)):
        raise ValueError(
            "covariance_matrix entries must be between 0 and 1 (inclusive)"
        )

    predictor_count = covariance_matrix.shape[0]
    # No negative probabilities
    nonnegativity_coefficients = -np.identity(predictor_count)
    nonnegativity_bounds = np.zeros(predictor_count)
    # All probabilities add to one
    normalization_coefficients = np.ones(predictor_count)

    # Define and solve the CVXPY problem.
    predictor_weights = cp.Variable(predictor_count)
    nonnegativity_constraint = (
        nonnegativity_coefficients @ predictor_weights <= nonnegativity_bounds
    )

    normalization_constraint = normalization_coefficients.T @ predictor_weights == 1
    optimization_problem = cp.Problem(
        # @ is matmul
        # .T is transpose
        # With method 1, the covariance matricies that can be inputed are always convex
        cp.Minimize(cp.quad_form(predictor_weights, covariance_matrix)),
        [nonnegativity_constraint, normalization_constraint],
    )

    # Convex case
    try:
        optimization_problem.solve()

    # Concave case
    except Exception:
        logger.warning("Concave minimization, uncalculated results!")
        # TODO: for Emil: extend the algorithm to include the concave minimization case
        # Might not actually be needed tbh

    weight_solution = predictor_weights.value
    minimum_variance = optimization_problem.value
    nonnegativity_dual_values = nonnegativity_constraint.dual_value

    if test:
        print("\nThe optimal value is", minimum_variance)
        print("A solution x is")
        print(weight_solution)

    # weight_solution is a vector (np.array) that sums up to 1.
    return [weight_solution, minimum_variance, nonnegativity_dual_values]


def update_kpi_combined_bets_from_bets(
    bets: QuerySet[PollProposalKPIBet],
    weights: dict[int, float],
) -> None:
    """
    Computes combined_bet from predictor bets, available as soon as prediction_bet
    phase ends. Votes (update_kpi_combined_bets) can't exist until the poll's own
    result phase, long after delegate_vote already needs a populated combined_bet,
    so this is the value delegates actually see; votes later refine older polls'
    combined_bet once their outcomes are known.
    """
    value_weights: dict[int, float] = {}
    total_weights: dict[tuple[int, int], float] = {}
    for user_id, proposal_kpi_id, proposal_id, kpi_id, bet_weight in bets.filter(
        created_by_id__in=weights
    ).values_list(
        "created_by_id",
        "proposal_kpi_id",
        "proposal_kpi__proposal_id",
        "proposal_kpi__kpi_value__kpi_id",
        "weight",
    ):
        weight = weights[user_id] * (bet_weight / 100)
        value_weights[proposal_kpi_id] = value_weights.get(proposal_kpi_id, 0) + weight
        key = (proposal_id, kpi_id)
        total_weights[key] = total_weights.get(key, 0) + weight

    proposal_kpis = list(
        PollProposalKPI.objects.filter(
            proposal_id__in={proposal_id for proposal_id, _ in total_weights}
        ).select_related("kpi_value")
    )
    changed = []
    for proposal_kpi in proposal_kpis:
        key = (proposal_kpi.proposal_id, proposal_kpi.kpi_value.kpi_id)
        total_weight = total_weights.get(key)
        if total_weight:
            proposal_kpi.combined_bet = value_weights.get(proposal_kpi.id, 0) / total_weight
            changed.append(proposal_kpi)

    PollProposalKPI.objects.bulk_update(changed, ["combined_bet"])
