"""Season prediction: where does each team finish?

Team strength (``team_strength``), a Poisson + Monte Carlo season
(``predictor``) and a walk-forward evaluation against baselines
(``evaluation``).
"""

from football_data_analysis.analyses.season_prediction.predictor import simulate_season
from football_data_analysis.analyses.season_prediction.team_strength import compute_team_strength

__all__ = ["compute_team_strength", "simulate_season"]
