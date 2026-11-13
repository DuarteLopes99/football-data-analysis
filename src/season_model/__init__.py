"""Season modelling for amateur football leagues from zerozero.pt data.

Pipeline (``pipeline``): scrape -> raw -> processed -> validated.
Model (``team_strength`` + ``predictor``): Poisson goals, Monte Carlo season.
Evaluation (``evaluation``): walk-forward backtests against baselines.
"""

from season_model.fixtures import dedupe_fixtures, split_played_remaining
from season_model.league_table import compute_league_table
from season_model.predictor import simulate_season
from season_model.team_strength import compute_team_strength

__all__ = [
    "compute_league_table",
    "compute_team_strength",
    "dedupe_fixtures",
    "simulate_season",
    "split_played_remaining",
]
