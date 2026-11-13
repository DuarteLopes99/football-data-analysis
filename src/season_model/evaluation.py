"""Evaluate the season model honestly: walk-forward backtests on a finished season.

The question a season predictor has to answer is "standing at matchweek *k*,
how well does it call the rest?". ``backtest`` answers it by cutting a complete
season at each cut-off, fitting team strength on matchweeks ``<= k`` only, and
scoring the prediction against what actually happened afterwards, at two levels:

* **Match level**: each remaining fixture gets home/draw/away probabilities
  (analytic Poisson, the same model the simulation draws from), scored with the
  ranked probability score (RPS, the standard for ordered football outcomes),
  multi-class Brier score, log loss and hit rate.
* **Table level**: the Monte Carlo expected final table against the real one:
  points MAE/RMSE, Spearman rank correlation, whether the champion was called,
  and the probability the model gave the real champion.

Every model is compared with baselines that a useful model has to beat:
``uniform`` (1/3 each) and ``base_rates`` (the training-period H/D/A
frequencies) for matches, ``ppg`` (current points-per-game carried forward) for
the table. A model that cannot beat ``ppg`` adds nothing over the table itself.

Nothing here refits on test data: venue factors, strengths and base rates all
come from the training window of each cut-off.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import poisson, spearmanr

from season_model.league_table import compute_league_table
from season_model.predictor import HOME_ADVANTAGE, expected_goals, simulate_season
from season_model.team_strength import TeamStrength, compute_team_strength

OUTCOMES = ("H", "D", "A")
PROB_COLUMNS = ["p_home", "p_draw", "p_away"]
MAX_GOALS = 15


# --------------------------------------------------------------------------- #
# Outcomes and probabilities
# --------------------------------------------------------------------------- #


def outcome_index(home_goals, away_goals) -> np.ndarray:
    """0 = home win, 1 = draw, 2 = away win (the order RPS needs)."""
    h = np.asarray(home_goals)
    a = np.asarray(away_goals)
    return np.where(h > a, 0, np.where(h == a, 1, 2))


def poisson_outcome_probs(lam_home: float, lam_away: float, max_goals: int = MAX_GOALS) -> tuple[float, float, float]:
    """P(home win), P(draw), P(away win) for independent Poisson goals."""
    goals = np.arange(max_goals + 1)
    grid = np.outer(poisson.pmf(goals, lam_home), poisson.pmf(goals, lam_away))
    p_home = np.tril(grid, -1).sum()
    p_draw = np.trace(grid)
    p_away = np.triu(grid, 1).sum()
    total = p_home + p_draw + p_away  # mass beyond max_goals is negligible; renormalise anyway
    return p_home / total, p_draw / total, p_away / total


def match_probabilities(
    fixtures: pd.DataFrame,
    strength: TeamStrength,
    home_advantage: float = HOME_ADVANTAGE,
    away_factor: float = 1.0,
) -> pd.DataFrame:
    """Add expected goals and H/D/A probabilities to each fixture row."""
    out = fixtures.copy()
    lams = [
        expected_goals(h, a, strength, home_advantage, away_factor)
        for h, a in zip(out["Home Team"], out["Away Team"])
    ]
    out["lam_home"] = [l[0] for l in lams]
    out["lam_away"] = [l[1] for l in lams]
    probs = np.array([poisson_outcome_probs(lh, la) for lh, la in lams]) if lams else np.empty((0, 3))
    for k, col in enumerate(PROB_COLUMNS):
        out[col] = probs[:, k] if len(probs) else []
    return out


def fit_venue_factors(played: pd.DataFrame) -> tuple[float, float]:
    """(home_factor, away_factor) such that the model reproduces the observed
    mean home and away goals: ``mean_home / league_avg`` and ``mean_away / league_avg``,
    where ``league_avg`` is goals per team per game.

    Unlike a bare home multiplier this moves goals between venues without
    changing the total.
    """
    mean_home = played["Home Goals"].mean()
    mean_away = played["Away Goals"].mean()
    league_avg = (mean_home + mean_away) / 2
    if not league_avg:
        return 1.0, 1.0
    return float(mean_home / league_avg), float(mean_away / league_avg)


def base_rates(played: pd.DataFrame) -> np.ndarray:
    """Observed H/D/A frequencies, with one pseudo-count each so no class is ever 0."""
    counts = np.bincount(outcome_index(played["Home Goals"], played["Away Goals"]), minlength=3) + 1
    return counts / counts.sum()


# --------------------------------------------------------------------------- #
# Scoring rules
# --------------------------------------------------------------------------- #


def ranked_probability_score(probs: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """RPS per match (lower is better; 0 = perfect). Respects that a draw is
    "closer" to a home win than an away win is."""
    probs = np.asarray(probs, dtype=float)
    onehot = np.eye(3)[np.asarray(outcomes)]
    cum_diff = np.cumsum(probs, axis=1)[:, :2] - np.cumsum(onehot, axis=1)[:, :2]
    return (cum_diff**2).sum(axis=1) / 2


def brier_score(probs: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """Multi-class Brier score per match (lower is better; range 0–2)."""
    onehot = np.eye(3)[np.asarray(outcomes)]
    return ((np.asarray(probs) - onehot) ** 2).sum(axis=1)


def log_loss(probs: np.ndarray, outcomes: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Negative log-probability of what happened, per match (lower is better)."""
    p = np.asarray(probs)[np.arange(len(outcomes)), np.asarray(outcomes)]
    return -np.log(np.clip(p, eps, 1.0))


def score_matches(probs: np.ndarray, outcomes: np.ndarray) -> dict[str, float]:
    probs = np.asarray(probs)
    outcomes = np.asarray(outcomes)
    if len(outcomes) == 0:
        return {"n_matches": 0, "rps": np.nan, "brier": np.nan, "log_loss": np.nan, "accuracy": np.nan}
    return {
        "n_matches": len(outcomes),
        "rps": float(ranked_probability_score(probs, outcomes).mean()),
        "brier": float(brier_score(probs, outcomes).mean()),
        "log_loss": float(log_loss(probs, outcomes).mean()),
        "accuracy": float((probs.argmax(axis=1) == outcomes).mean()),
    }


def calibration_table(predictions: pd.DataFrame, n_bins: int = 5) -> pd.DataFrame:
    """Predicted vs observed frequency per outcome, in equal-width probability bins.

    ``predictions`` needs ``p_home/p_draw/p_away`` and ``outcome`` (0/1/2). A
    calibrated model has ``observed`` close to ``mean_predicted`` in every bin;
    with one season per bin this is noisy, so ``n`` is reported.
    """
    rows = []
    edges = np.linspace(0, 1, n_bins + 1)
    for k, (name, col) in enumerate(zip(OUTCOMES, PROB_COLUMNS)):
        p = predictions[col].to_numpy()
        hit = (predictions["outcome"].to_numpy() == k).astype(float)
        bins = np.clip(np.digitize(p, edges) - 1, 0, n_bins - 1)
        for b in range(n_bins):
            mask = bins == b
            if not mask.any():
                continue
            rows.append(
                {
                    "outcome": name,
                    "bin": f"{edges[b]:.1f}–{edges[b + 1]:.1f}",
                    "mean_predicted": p[mask].mean(),
                    "observed": hit[mask].mean(),
                    "n": int(mask.sum()),
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Table-level scoring
# --------------------------------------------------------------------------- #


def ppg_projection(train: pd.DataFrame, final_games: pd.Series) -> pd.Series:
    """Baseline: each team's points-per-game so far, carried over its full schedule."""
    table = compute_league_table(train).set_index("Team")
    ppg = table["Points"] / table["Played"].replace(0, np.nan)
    return (ppg * final_games.reindex(ppg.index)).fillna(0)


def score_table(expected_points: pd.Series, final_table: pd.DataFrame, title_probability: float | None = None) -> dict:
    """Compare projected final points with the real final table."""
    final = final_table.set_index("Team")
    exp = expected_points.reindex(final.index)
    err = exp - final["Points"]
    rho = spearmanr(exp, final["Points"]).statistic if len(final) > 2 else np.nan
    predicted_champion = exp.idxmax()
    actual_champion = final_table.iloc[0]["Team"]
    return {
        "points_mae": float(err.abs().mean()),
        "points_rmse": float(np.sqrt((err**2).mean())),
        "spearman": float(rho),
        "champion_called": bool(predicted_champion == actual_champion),
        "p_actual_champion": title_probability,
    }


# --------------------------------------------------------------------------- #
# Walk-forward backtest
# --------------------------------------------------------------------------- #


def split_at_matchweek(played: pd.DataFrame, cutoff: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(train, test): matchweeks ``<= cutoff`` vs the rest. Test keeps its scores
    for scoring; the simulation only ever sees its Home/Away columns."""
    mw = played["Numeric Matchweek"]
    return played[mw <= cutoff].reset_index(drop=True), played[mw > cutoff].reset_index(drop=True)


@dataclass(frozen=True)
class ModelSpec:
    """One variant of the Poisson model. ``fit_venue=True`` estimates home and
    away factors from the training window instead of using the fixed values."""

    name: str
    home_advantage: float = HOME_ADVANTAGE
    away_factor: float = 1.0
    fit_venue: bool = False

    def venue(self, train: pd.DataFrame) -> tuple[float, float]:
        return fit_venue_factors(train) if self.fit_venue else (self.home_advantage, self.away_factor)


DEFAULT_MODELS = (
    ModelSpec("poisson_fixed_ha", home_advantage=HOME_ADVANTAGE),
    ModelSpec("poisson_venue_fit", fit_venue=True),
    ModelSpec("poisson_no_ha", home_advantage=1.0),
)


@dataclass
class BacktestResult:
    match_scores: pd.DataFrame
    """One row per (cutoff, model): RPS, Brier, log loss, accuracy over the remaining matches."""

    table_scores: pd.DataFrame
    """One row per (cutoff, model): final-table errors."""

    predictions: pd.DataFrame
    """Every test match with its probabilities and outcome, per (cutoff, model). Feeds calibration."""

    def summary(self) -> pd.DataFrame:
        """Mean over cut-offs, best first by RPS."""
        m = self.match_scores.groupby("model")[["rps", "brier", "log_loss", "accuracy"]].mean()
        t = self.table_scores.groupby("model")[["points_mae", "spearman"]].mean()
        return m.join(t, how="outer").sort_values("rps", na_position="last")


def backtest(
    played_full: pd.DataFrame,
    cutoffs: list[int],
    models: tuple[ModelSpec, ...] = DEFAULT_MODELS,
    n_simulations: int = 2000,
    seed: int = 42,
) -> BacktestResult:
    """Walk-forward evaluation over a *complete* season's played matches."""
    final_table = compute_league_table(played_full)
    final_games = final_table.set_index("Team")["Played"]
    actual_champion = final_table.iloc[0]["Team"]

    match_rows, table_rows, pred_frames = [], [], []
    for cutoff in cutoffs:
        train, test = split_at_matchweek(played_full, cutoff)
        if train.empty or test.empty:
            continue
        outcomes = outcome_index(test["Home Goals"], test["Away Goals"])
        strength = compute_team_strength(train)
        remaining = test[["Numeric Matchweek", "Matchweek", "Home Team", "Away Team"]]

        # Baselines
        uniform = np.full((len(test), 3), 1 / 3)
        rates = np.tile(base_rates(train), (len(test), 1))
        for name, probs in (("uniform", uniform), ("base_rates", rates)):
            match_rows.append({"cutoff": cutoff, "model": name, **score_matches(probs, outcomes)})
        table_rows.append(
            {"cutoff": cutoff, "model": "ppg", **score_table(ppg_projection(train, final_games), final_table)}
        )

        # Poisson variants
        for spec in models:
            home_f, away_f = spec.venue(train)
            preds = match_probabilities(test, strength, home_f, away_f)
            preds["outcome"] = outcomes
            preds["cutoff"] = cutoff
            preds["model"] = spec.name
            pred_frames.append(preds)
            match_rows.append(
                {
                    "cutoff": cutoff,
                    "model": spec.name,
                    "home_factor": home_f,
                    "away_factor": away_f,
                    **score_matches(preds[PROB_COLUMNS].to_numpy(), outcomes),
                }
            )
            sim = simulate_season(
                train, remaining, n_simulations=n_simulations, seed=seed,
                home_advantage=home_f, away_factor=away_f, strength=strength,
            )
            title = sim.position_probabilities.set_index("Team")["Title %"].get(actual_champion, 0.0) / 100
            table_rows.append(
                {
                    "cutoff": cutoff,
                    "model": spec.name,
                    **score_table(sim.predicted_table.set_index("Team")["Points"], final_table, title),
                }
            )

    return BacktestResult(
        match_scores=pd.DataFrame(match_rows),
        table_scores=pd.DataFrame(table_rows),
        predictions=pd.concat(pred_frames, ignore_index=True) if pred_frames else pd.DataFrame(),
    )


def goals_dispersion(played: pd.DataFrame) -> pd.DataFrame:
    """Variance-to-mean ratio of home and away goals. Poisson implies ~1;
    well above 1 means the model understates blow-outs and upsets."""
    rows = []
    for col in ("Home Goals", "Away Goals"):
        g = played[col]
        rows.append({"side": col, "mean": g.mean(), "variance": g.var(ddof=1), "var/mean": g.var(ddof=1) / g.mean()})
    return pd.DataFrame(rows)


def draw_rate_check(played: pd.DataFrame, strength: TeamStrength, home_advantage: float, away_factor: float = 1.0) -> dict:
    """Observed draw share vs the share the model implies for the same fixtures.

    Independent Poisson goals get draws wrong in a league-specific direction:
    top-flight leagues usually draw *more* than the model says, while a
    high-scoring, overdispersed amateur league (Fermedo 24/25: var/mean ~ 2)
    can draw *less*. Check it per league rather than assuming.
    """
    preds = match_probabilities(played, strength, home_advantage, away_factor)
    return {
        "observed_draw_rate": float((played["Home Goals"] == played["Away Goals"]).mean()),
        "model_draw_rate": float(preds["p_draw"].mean()),
    }
