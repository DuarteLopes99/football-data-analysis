# Analysis: season prediction

`src/football_data_analysis/analyses/season_prediction` answers "standing at
matchweek *k*, where does each team finish, with how many points?". It reads
played and remaining fixtures from [core](core.md) and adds
**team strength → Poisson + Monte Carlo season → walk-forward backtest**.
Notebooks:
[`02_season_exploration`](../notebooks/season_prediction/02_season_exploration.ipynb)
checks the model's assumptions on the data,
[`03_model_evaluation`](../notebooks/season_prediction/03_model_evaluation.ipynb)
scores it against baselines and applies it to the current season.

```python
from football_data_analysis.core.pipeline import load_season, validate_season
from football_data_analysis.analyses.season_prediction.team_strength import compute_team_strength
from football_data_analysis.analyses.season_prediction.predictor import simulate_season

played, remaining = load_season("mansores_2025_26")
validate_season("mansores_2025_26")       # read this before trusting a prediction
```

## 1. Team strength (`team_strength.compute_team_strength`)

```python
strength = compute_team_strength(played)  # .attack, .defense, .league_avg_goals_per_game, .table
```

* **Attack** = team goals scored per game ÷ league average goals per team per game.
* **Defence** = league average ÷ (team goals conceded per game + 0.1). Higher is
  better. The `+0.1` stops a team that has conceded nothing from getting an
  unbounded rating.

## 2. Monte Carlo prediction (`predictor.simulate_season`)

```python
pred = simulate_season(played, remaining, n_simulations=5000, seed=42,
                       home_advantage=1.15, away_factor=1.0)
pred.predicted_table          # expected final stat line per team
pred.position_probabilities   # Title %, Top 3 %, Bottom 3 %
pred.position_matrix          # team x final position, % (rows sum to 100)
```

Each remaining fixture's goals are independent Poisson draws:

```
lambda_home = attack_home / defence_away * league_avg * home_advantage
lambda_away = attack_away / defence_home * league_avg * away_factor
```

For each simulation the simulated results are added to the played ones and
teams are ranked by points, then goal difference (then name, for full ties).
Stat lines are summed once over simulations and divided once by
`n_simulations` (see the bug below). The draw is vectorised over simulations,
so 5 000 simulations of a half season take well under a second.

`home_advantage=1.15, away_factor=1.0` is the original model. Because the league
average already includes home goals, multiplying only the home side adds goals
instead of moving them between venues. `evaluation.fit_venue_factors(played)`
returns factors that reproduce the observed home and away means and keep the
total unchanged.

## 3. Evaluation (`evaluation.backtest`)

Walk-forward on a **finished** season: for each cut-off matchweek *k*, fit
strength and venue factors on matchweeks ≤ *k*, predict the rest, score against
what happened. Nothing is refitted on test data.

| level | scores | baselines |
|---|---|---|
| match | RPS, multi-class Brier, log loss, hit rate | `uniform`, `base_rates` (training H/D/A shares) |
| final table | points MAE/RMSE, Spearman ρ, champion called, P(real champion) | `ppg` (points per game × season length) |

RPS is the headline score: it is the standard for ordered football outcomes,
because it treats a draw as closer to a home win than an away win is.

`BacktestResult.predictions` keeps every test match's probabilities for
`calibration_table()`. Notebook 03 adds a paired bootstrap so differences
between model variants are judged against resampling noise.

**Results on `fermedo_2024_25`** (13 cut-offs, 2 000 simulations, seed 42;
notebook 03 prints the current numbers in its findings cell):

* All Poisson variants beat both match baselines by a wide margin: RPS ≈ 0.14 vs
  0.245 (uniform), roughly 43 % better.
* The simulated final table beats carrying points-per-game forward (points MAE
  ≈ 4.6 vs 5.7) at most cut-offs.
* Fitted vs fixed home advantage: indistinguishable (bootstrap CI includes 0).
  No home advantage at all: measurably worse.
* Goals are overdispersed (var/mean ≈ 2 home and away) and the model predicts
  more draws than happen (≈ 25 % vs 19.6 %). Negative binomial goals or a
  Dixon–Coles correction are the next candidates to test against the same
  baselines.

## Known bug fixed: double averaging in the predictor

`dev_model.ipynb` divided already averaged simulation stats by
`N_SIMULATIONS` a second time, producing values like `Draws_Predicted: 965.36`.
Regression test: `tests/season_prediction/test_predictor.py`.
