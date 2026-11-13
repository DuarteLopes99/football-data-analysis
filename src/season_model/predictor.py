"""Monte Carlo season predictor: simulate remaining fixtures with a Poisson model.

Each remaining fixture's goals are Poisson draws whose means come from the two
teams' attack/defence strengths (``team_strength.py``), the league's average
goals per team per game, and a home-advantage multiplier on the home side:

    lambda_home = (attack_home / defence_away) * league_avg * home_advantage
    lambda_away = (attack_away / defence_home) * league_avg

Every simulation adds its simulated results to the played ones, ranks the full
table (points, then goal difference) and records each team's stat line and
finishing position. Averaging those once gives ``predicted_table``; counting
positions gives ``position_probabilities``.

Ported from ``dev_model.ipynb``, fixing a bug present there: the original final
merge divided the already-averaged ``Points_Predicted``/``GD_Predicted``/etc.
columns by ``N_SIMULATIONS`` a second time, producing values like
``Draws_Predicted: 965.36``. Here every per-team stat across simulations is
summed exactly once and divided by ``n_simulations`` exactly once.

The simulation is vectorised over simulations (one ``(n_simulations, n_fixtures)``
array of goals per side), so a backtest over many cut-offs runs in seconds
rather than re-running ``compute_league_table`` row by row for every simulation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import poisson

from season_model.league_table import STANDINGS_COLUMNS, compute_league_table
from season_model.team_strength import TeamStrength, compute_team_strength

HOME_ADVANTAGE = 1.15
"""Default multiplier on the home side's expected goals. A fixed guess carried
over from the source notebook; ``evaluation.fit_home_advantage`` estimates it
from data, and the evaluation notebook compares the two."""

STAT_COLUMNS = ["Points", "Wins", "Draws", "Losses", "Goals Scored", "Goals Conceded", "GD", "Played"]


@dataclass
class SeasonPrediction:
    actual_table: pd.DataFrame
    """Standings from played matches only."""

    predicted_table: pd.DataFrame
    """Expected final standings: actual + remaining fixtures, averaged over all simulations."""

    position_probabilities: pd.DataFrame
    """Per team: probability (%) of finishing 1st, in the top 3, or in the bottom 3."""

    position_matrix: pd.DataFrame
    """Team x final position, probability (%) of each finish. Rows sum to 100."""

    n_simulations: int
    home_advantage: float = HOME_ADVANTAGE
    away_factor: float = 1.0


def expected_goals(
    home_team: str,
    away_team: str,
    strength: TeamStrength,
    home_advantage: float = HOME_ADVANTAGE,
    away_factor: float = 1.0,
) -> tuple[float, float]:
    """Poisson means (home, away) for one fixture. Unknown teams count as average (1.0).

    ``away_factor`` scales the away side the way ``home_advantage`` scales the
    home side. The original model leaves it at 1.0, which inflates total goals:
    the league average already *includes* home goals, so multiplying only the
    home side by 1.15 adds goals rather than moving them between venues.
    ``evaluation.fit_venue_factors`` estimates both from data.
    """
    league_avg_goals = strength.league_avg_goals_per_game / 2
    home_attack = strength.attack.get(home_team, 1.0)
    away_defense = strength.defense.get(away_team, 1.0)
    away_attack = strength.attack.get(away_team, 1.0)
    home_defense = strength.defense.get(home_team, 1.0)
    lam_home = (home_attack / away_defense) * league_avg_goals * home_advantage
    lam_away = (away_attack / home_defense) * league_avg_goals * away_factor
    return lam_home, lam_away


def simulate_match(
    home_team: str,
    away_team: str,
    strength: TeamStrength,
    rng: np.random.Generator,
    home_advantage: float = HOME_ADVANTAGE,
) -> tuple[int, int]:
    """One simulated scoreline. Kept for single-match use; ``simulate_season`` draws in bulk."""
    lam_home, lam_away = expected_goals(home_team, away_team, strength, home_advantage)
    return int(poisson.rvs(lam_home, random_state=rng)), int(poisson.rvs(lam_away, random_state=rng))


def _rank_teams(table: pd.DataFrame) -> list[str]:
    return table.sort_values(["Points", "GD"], ascending=[False, False])["Team"].tolist()


def _position_probabilities(position_counts: np.ndarray, teams: list[str], n_simulations: int) -> pd.DataFrame:
    n_teams = len(teams)
    span = min(3, n_teams)
    rows = [
        {
            "Team": team,
            "Title %": round(100 * position_counts[i, 0] / n_simulations, 1),
            "Top 3 %": round(100 * position_counts[i, :span].sum() / n_simulations, 1),
            "Bottom 3 %": round(100 * position_counts[i, -span:].sum() / n_simulations, 1),
        }
        for i, team in enumerate(teams)
    ]
    return pd.DataFrame(rows).sort_values("Title %", ascending=False).reset_index(drop=True)


def _position_matrix(position_counts: np.ndarray, teams: list[str], n_simulations: int) -> pd.DataFrame:
    matrix = pd.DataFrame(
        100 * position_counts / n_simulations,
        index=pd.Index(teams, name="Team"),
        columns=range(1, len(teams) + 1),
    )
    expected_pos = (matrix * np.arange(1, len(teams) + 1)).sum(axis=1) / 100
    return matrix.loc[expected_pos.sort_values().index]


def _base_stats(actual_table: pd.DataFrame, teams: list[str]) -> np.ndarray:
    """Played-match stat lines as a (n_teams, n_stats) array in ``teams`` order."""
    base = actual_table.set_index("Team").reindex(teams)[STAT_COLUMNS].fillna(0)
    return base.to_numpy(dtype=float)


def simulate_season(
    played_matches: pd.DataFrame,
    remaining_fixtures: pd.DataFrame,
    n_simulations: int = 1000,
    seed: int | None = None,
    home_advantage: float = HOME_ADVANTAGE,
    strength: TeamStrength | None = None,
    away_factor: float = 1.0,
) -> SeasonPrediction:
    """Simulate the rest of a season ``n_simulations`` times and average the outcomes.

    ``strength`` defaults to ``compute_team_strength(played_matches)``; pass one
    in to evaluate a different strength model on the same simulation.
    """
    actual_table = compute_league_table(played_matches)
    remaining_teams = (
        pd.concat([remaining_fixtures["Home Team"], remaining_fixtures["Away Team"]]).tolist()
        if not remaining_fixtures.empty
        else []
    )
    teams = sorted(set(actual_table["Team"]) | set(remaining_teams))
    n_teams = len(teams)
    index = {team: i for i, team in enumerate(teams)}

    if remaining_fixtures.empty:
        counts = np.zeros((n_teams, n_teams))
        for pos, team in enumerate(_rank_teams(actual_table)):
            counts[index[team], pos] = n_simulations
        return SeasonPrediction(
            actual_table=actual_table,
            predicted_table=actual_table.copy(),
            position_probabilities=_position_probabilities(counts, teams, n_simulations),
            position_matrix=_position_matrix(counts, teams, n_simulations),
            n_simulations=n_simulations,
            home_advantage=home_advantage,
            away_factor=away_factor,
        )

    if strength is None:
        strength = compute_team_strength(played_matches)
    rng = np.random.default_rng(seed)

    home_idx = remaining_fixtures["Home Team"].map(index).to_numpy()
    away_idx = remaining_fixtures["Away Team"].map(index).to_numpy()
    lambdas = np.array(
        [
            expected_goals(h, a, strength, home_advantage, away_factor)
            for h, a in zip(remaining_fixtures["Home Team"], remaining_fixtures["Away Team"])
        ]
    )
    n_fixtures = len(remaining_fixtures)
    home_goals = rng.poisson(lambdas[:, 0], size=(n_simulations, n_fixtures))
    away_goals = rng.poisson(lambdas[:, 1], size=(n_simulations, n_fixtures))

    # Incidence matrices: fixture j -> its home / away team column.
    home_m = np.zeros((n_fixtures, n_teams))
    home_m[np.arange(n_fixtures), home_idx] = 1
    away_m = np.zeros((n_fixtures, n_teams))
    away_m[np.arange(n_fixtures), away_idx] = 1

    home_win = (home_goals > away_goals).astype(float)
    draw = (home_goals == away_goals).astype(float)
    away_win = (home_goals < away_goals).astype(float)

    # Each stat as (n_simulations, n_teams), simulated part only.
    sim = {
        "Wins": home_win @ home_m + away_win @ away_m,
        "Draws": draw @ home_m + draw @ away_m,
        "Losses": away_win @ home_m + home_win @ away_m,
        "Goals Scored": home_goals @ home_m + away_goals @ away_m,
        "Goals Conceded": away_goals @ home_m + home_goals @ away_m,
        "Played": np.ones_like(home_goals, dtype=float) @ (home_m + away_m),
    }
    sim["Points"] = 3 * sim["Wins"] + sim["Draws"]
    sim["GD"] = sim["Goals Scored"] - sim["Goals Conceded"]

    base = _base_stats(actual_table, teams)
    totals = {col: sim[col] + base[:, k] for k, col in enumerate(STAT_COLUMNS)}

    # Rank by points, then goal difference. Remaining ties fall back to team
    # name order, as in compute_league_table's stable sort.
    order = np.lexsort((np.broadcast_to(np.arange(n_teams), totals["GD"].shape), -totals["GD"], -totals["Points"]))
    position_counts = np.zeros((n_teams, n_teams))
    for pos in range(n_teams):
        position_counts[:, pos] = np.bincount(order[:, pos], minlength=n_teams)

    predicted_table = pd.DataFrame(
        {"Team": teams, **{col: np.round(totals[col].mean(axis=0), 2) for col in STAT_COLUMNS}}
    )
    predicted_table = predicted_table.sort_values(["Points", "GD"], ascending=[False, False]).reset_index(drop=True)

    return SeasonPrediction(
        actual_table=actual_table,
        predicted_table=predicted_table[["Team", *STAT_COLUMNS]],
        position_probabilities=_position_probabilities(position_counts, teams, n_simulations),
        position_matrix=_position_matrix(position_counts, teams, n_simulations),
        n_simulations=n_simulations,
        home_advantage=home_advantage,
        away_factor=away_factor,
    )


__all__ = [
    "HOME_ADVANTAGE",
    "STANDINGS_COLUMNS",
    "SeasonPrediction",
    "expected_goals",
    "simulate_match",
    "simulate_season",
]
