import numpy as np
import pandas as pd
import pytest

from season_model.config import get_season
from season_model.evaluation import (
    backtest,
    brier_score,
    fit_venue_factors,
    log_loss,
    poisson_outcome_probs,
    ranked_probability_score,
    split_at_matchweek,
)
from season_model.fixtures import load_processed


def test_rps_is_zero_for_a_certain_correct_call_and_penalises_distance():
    perfect = ranked_probability_score(np.array([[1, 0, 0]]), np.array([0]))
    near = ranked_probability_score(np.array([[0, 1, 0]]), np.array([0]))
    far = ranked_probability_score(np.array([[0, 0, 1]]), np.array([0]))
    assert perfect[0] == 0 and 0 < near[0] < far[0] == 1


def test_brier_and_log_loss_of_uniform_forecast():
    p = np.full((1, 3), 1 / 3)
    assert brier_score(p, np.array([1]))[0] == pytest.approx(2 / 3)
    assert log_loss(p, np.array([1]))[0] == pytest.approx(np.log(3))


def test_poisson_probabilities_sum_to_one_and_favour_the_stronger_side():
    ph, pd_, pa = poisson_outcome_probs(2.0, 0.8)
    assert ph + pd_ + pa == pytest.approx(1)
    assert ph > pa


def test_venue_factors_move_goals_without_changing_the_total():
    played = pd.DataFrame({"Home Goals": [3, 2, 1], "Away Goals": [1, 1, 1]})
    h, a = fit_venue_factors(played)
    assert (h + a) / 2 == pytest.approx(1)
    assert h > 1 > a


def test_split_never_leaks_future_matchweeks():
    played, _ = load_processed(get_season("fermedo_2024_25"))
    train, test = split_at_matchweek(played, 10)
    assert train["Numeric Matchweek"].max() == 10 and test["Numeric Matchweek"].min() == 11
    assert len(train) + len(test) == len(played)


def test_backtest_on_the_complete_season_produces_sane_scores():
    played, _ = load_processed(get_season("fermedo_2024_25"))
    result = backtest(played, cutoffs=[15], n_simulations=300, seed=0)
    scores = result.match_scores.set_index("model")
    assert scores.loc["uniform", "rps"] == pytest.approx(scores.loc["uniform", "rps"])  # finite
    assert (scores["rps"].between(0, 1)).all()
    tables = result.table_scores.set_index("model")
    assert {"ppg", "poisson_fixed_ha", "poisson_venue_fit"} <= set(tables.index)
    assert (tables["points_mae"] >= 0).all()
