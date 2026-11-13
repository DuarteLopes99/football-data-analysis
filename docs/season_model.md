# Season model: pipeline, model and evaluation

Pipeline: **scrape → raw → processed → validate → league table → team strength →
Monte Carlo prediction → backtest**. Every stage is a plain function in
`src/season_model`, driven by a `SeasonConfig`, and every stage has a notebook
section that calls it. Nothing is hardcoded to one team or season.

## 1. Declaring a season

Everything about a season lives in one `SeasonConfig` in
[`src/season_model/config.py`](../src/season_model/config.py):

```python
SeasonConfig(
    key="mansores_2025_26",                 # directory-safe id -> data/seasons/<key>/
    label="Mansores — AF Aveiro II Divisão Zona Norte 25/26",
    competition_name="AF Aveiro II Divisão Zona Norte 25/26",  # exact zerozero.pt string
    primary_team="mansores",
    epoca_id=155,                           # zerozero season id, pinned onto every URL
    teams={...},                            # team slug -> zerozero.pt "jogos" page URL
    team_name_mapping={...},                # zerozero display name -> team slug
)
```

To add a season, either append a `SeasonConfig` to `SEASONS`, or build one in a
notebook with `define_season(...)` (registered for that Python session only)
and copy it into `SEASONS` once it works.

**`epoca_id`.** A "jogos" URL without it shows the *current* season.
`SeasonConfig.team_urls` rewrites every URL with the config's id, so the stored
URLs can stay plain. Known ids: 154 = 2024/25, 155 = 2025/26.
`epoca_id_for(start_year)` extrapolates from those two; confirm it against the
"Época" selector on a team page before relying on it further out.

**`competition_name`** must match zerozero's string exactly: a team's page lists
the league, the cup and sometimes play-offs together, and only league rows may
reach the table. For a new season, scrape once, then read
`pipeline.competitions_found(season)` to copy the right string.

## 2. Scraping (`pipeline.scrape_season`)

```bash
python -m season_model.scraping.cli mansores_2025_26               # every team
python -m season_model.scraping.cli mansores_2025_26 --teams crc_vale --overwrite
python -m season_model.scraping.cli mansores_2025_26 --no-scrape   # re-process raw only
```

One headless Chrome session, one fixtures page per team, a pause between teams.
`zerozero_client.fetch_team_fixtures()` reads the page's **second** `#team_games`
table (the first is a season-totals row). Two files per team land in
`data/seasons/<key>/raw/`:

* `<slug>_fixtures.csv`: league rows only. Tracked in git.
* `<slug>_all_competitions.csv`: every row on the page. Gitignored; only used to
  pick `competition_name`.

**Rate limit.** A burst of requests returns zerozero's "Serviço Temporariamente
Suspenso" page. The client detects it, raises `RateLimitedError`, and
`scrape_season` stops and reports `rate_limited=True`. Teams already on disk are
skipped on the next run, so waiting a few minutes and re-running resumes the
scrape. Don't loop on it.

Selenium is imported inside `scrape_season`, so processing, modelling and the
tests run on a machine without Chrome.

## 3. Processing (`pipeline.process_season`)

1. Load each team's raw file and keep `Competition == competition_name` (the
   Mansores export carries two Taça Pecol rows that must not reach the table).
2. Turn `Location` (`(C)` casa / `(F)` fora) into explicit `Home Team` /
   `Away Team`, and `Result` into `Home Goals` / `Away Goals`.
   **`Result` is always "home score-away score"**, whichever side the tracked
   team is on (see known bug 1).
3. Deduplicate: every match appears once in each participating team's export.
   `dedupe_fixtures()` keys on `(Matchweek, sorted(home, away))`.

Output: `processed/fixtures_played.csv` and `processed/fixtures_remaining.csv`.
`fermedo_2024_25` predates the per-team raw layout (its raw folder holds a single
tidy export), so it is read from `processed/` directly.

## 4. Validation (`pipeline.validate_season`)

Returns a table of checks: coverage against a full double round-robin
(`n·(n−1)` matches), teams with an incomplete fixture list, team names that
didn't map to a slug, duplicate home/away pairings, missing or negative scores.
Coverage is the one that matters for modelling: with one team's page only, every
other team's strength is estimated from a single match.

## 5. League table and team strength

```python
table = compute_league_table(played)      # Points, W/D/L, GF/GA, GD, Played; sorted by Points, GD
strength = compute_team_strength(played)  # .attack, .defense, .league_avg_goals_per_game, .table
```

* **Attack** = team goals scored per game ÷ league average goals per team per game.
* **Defence** = league average ÷ (team goals conceded per game + 0.1). Higher is
  better. The `+0.1` stops a team that has conceded nothing from getting an
  unbounded rating.

## 6. Monte Carlo prediction (`predictor.simulate_season`)

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
`n_simulations` (see known bug 2). The draw is vectorised over simulations, so
5 000 simulations of a half season take well under a second.

`home_advantage=1.15, away_factor=1.0` is the original model. Because the league
average already includes home goals, multiplying only the home side adds goals
instead of moving them between venues. `evaluation.fit_venue_factors(played)`
returns factors that reproduce the observed home and away means and keep the
total unchanged.

## 7. Evaluation (`evaluation.backtest`)

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
re-run notebook 03 for current numbers):

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

## 8. Player and match-event stats

Separate from the season model: `scraping.zerozero_client.scrape_season_match_reports(urls)`
returns one row per player per match (starters, subs, goals, assists, cards);
`players.match_events.build_events_table()` and `build_player_season_stats()`
turn that into event and per-player tables. Minutes are estimated, not scraped:
starters play until subbed off (else 90), substitutes from their sub-in minute
(else 0).

## Known bugs fixed

Both were found by testing the port against real season data. Regression tests:
`tests/test_fixtures.py`, `tests/test_predictor.py`.

1. **Home/away score swap.** The source notebooks (`dev_model.ipynb`,
   `Dev_Mansores_Predict.ipynb`) read `Result` as "tracked team - opponent" when
   the tracked team played away; it is always "home - away". Some away wins were
   recorded as home wins for the opponent. Before the fix Mansores' 11 games
   computed as 4W-0D-7L (12 pts); after, the correct 10W-0D-1L (30 pts).
2. **Double averaging in the predictor.** `dev_model.ipynb` divided already
   averaged simulation stats by `N_SIMULATIONS` a second time, producing values
   like `Draws_Predicted: 965.36`.

## Data in the repo

* **`fermedo_2024_25`**: complete. 16 teams, 240 matches, double round-robin, no
  remaining fixtures. The backtest season and `tests/test_data_seed.py`'s check.
* **`mansores_2025_26`**: partial. Mansores' own 22 league fixtures (11 played,
  11 remaining as of the 2026-01-17 scrape). Mansores' row is exact; every other
  row reflects one match. The season has since finished: re-scrape all teams
  (the URLs are pinned to `epoca_id=155`) to get the full, final 2025/26 league,
  which becomes a second backtest season.
