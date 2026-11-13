Modelling and prediction for amateur football leagues, built around one question family: teams, points and standings. How many points will a team finish on? What are the chances it ends the season in place X? How many points does it need to get there? What happens to the table if a given match goes the other way?

The repo is stratified in two layers:

A generic core that knows nothing about any specific question: season data, league tables, team ratings, match models, a season simulator and an evaluation harness.
Analyses, each answering one question about teams, points or standings, built only on top of the core.

Every analysis reads the same inputs (a season's matches at a given matchweek) and most read the same simulation output, so a new analysis is usually a few functions and a notebook, not a new pipeline.

Notebook-first, no frontend. Data comes from zerozero.pt. Successor to Football-Season-Model; the personal GPS dashboard stays in Football-Stats-Data.

How the layers fit together
                         ┌────────────────────────────── core ──────────────────────────────┐
 zerozero.pt ──▶ data ──▶ SeasonState ──▶ ratings ──▶ match model ──▶ simulation ──▶ SimulationResult
                 (scrape,  (played +      (attack/     (P(goals),     (Monte Carlo    (per sim: points,
                 process,  remaining at   defence,     P(H/D/A))      over the        GD, final position
                 validate) matchweek k)   Elo, ...)                   remaining       for every team)
                                                                      fixtures)
                         └──────────────────────────────────┬─────────────────────────────────┘
                                                            │
        ┌──────────────────┬──────────────────┬─────────────┼──────────────┬───────────────────┐
        ▼                  ▼                  ▼             ▼              ▼                   ▼
  match_outcomes   points_projection   final_position   points_targets   what_if     historical / form
                                                                                    
                         └──────────────────── evaluation (core) scores every analysis ─────────────┘

Two objects carry everything between the layers:

SeasonState: one season frozen at a matchweek: played matches with scores, remaining fixtures, the team list and the season config. Every analysis starts from one. Cutting a finished season at matchweek k gives the state a backtest needs, with nothing from after k in it.
SimulationResult: the outcome of N simulated season endings, kept as arrays (points[sim, team], gd[sim, team], position[sim, team]), not pre-averaged. Points projections, place probabilities, points targets and scenarios are all different summaries of the same arrays.
Repository layout
football-data-analysis/
├── src/football_analysis/
│   ├── core/                          # generic; never imports from analyses/
│   │   ├── config.py                  # SeasonConfig, SEASONS registry, zerozero epoca_id
│   │   ├── data/
│   │   │   ├── zerozero.py            # Selenium client: one page at a time, rate-limit aware
│   │   │   ├── pipeline.py            # scrape_season → process_season → validate_season
│   │   │   └── schema.py              # canonical match / fixture columns, checked on load
│   │   ├── state.py                   # SeasonState, cut_at_matchweek()
│   │   ├── standings.py               # league table + tie-break rules (points, GD, ...)
│   │   ├── ratings/                   # team strength, one interface
│   │   │   ├── base.py                #   Ratings protocol: fit(played) -> ratings
│   │   │   ├── attack_defence.py      #   current model: goals for/against vs league average
│   │   │   └── elo.py                 #   planned
│   │   ├── models/                    # match models, one interface
│   │   │   ├── base.py                #   MatchModel: score_probs(home, away) -> P(H, D, A), goal grid
│   │   │   ├── poisson.py             #   current model (home/away venue factors)
│   │   │   ├── negative_binomial.py   #   planned: goals are overdispersed (var/mean ≈ 2)
│   │   │   └── dixon_coles.py         #   planned: low-score / draw correction
│   │   ├── simulation.py              # simulate(state, model, n) -> SimulationResult (vectorised)
│   │   └── evaluation/
│   │       ├── scoring.py             # RPS, Brier, log loss, MAE, interval coverage
│   │       ├── baselines.py           # uniform, base_rates, points-per-game
│   │       └── backtest.py            # walk-forward over finished seasons, paired bootstrap
│   │
│   └── analyses/                      # one folder per question; imports core only
│       ├── match_outcomes/            # P(home/draw/away) and expected goals per fixture
│       ├── points_projection/         # expected final points per team, with intervals
│       ├── final_position/            # P(team finishes in place X), title / promotion / relegation
│       ├── points_targets/            # points needed for place X; "safe" and "out of reach" lines
│       ├── what_if/                   # fix chosen results, re-simulate, compare tables
│       ├── form_and_trends/           # rolling form, ratings over the season, home/away splits
│       └── historical/                # across seasons: points of champions / relegated, by league
│
├── notebooks/
│   ├── core/
│   │   ├── 01_data_pipeline.ipynb     # get a season from zerozero.pt, validate it
│   │   ├── 02_data_exploration.ipynb  # goals, home advantage, dispersion, ratings
│   │   └── 03_model_evaluation.ipynb  # match models vs baselines, walk-forward
│   └── analyses/
│       └── <analysis>/                # one or more notebooks per analysis
│
├── data/
│   ├── seasons/<key>/raw/             # per-team zerozero exports (league rows)
│   ├── seasons/<key>/processed/       # fixtures_played.csv, fixtures_remaining.csv
│   └── derived/<analysis>/            # outputs an analysis chooses to persist
│
├── tests/
│   ├── core/
│   └── analyses/<analysis>/
└── docs/
    ├── core.md                        # data contract, ratings, models, simulation, evaluation
    └── analyses/<analysis>.md         # longer write-ups when an analysis README isn't enough
What is built and what is planned

The core comes from Football-Season-Model, so most of it already exists.

Area	Status	Comes from
core/config.py, core/data/*	built	season_model/config.py, pipeline.py, scraping/
core/standings.py	built	season_model/league_table.py
core/ratings/attack_defence.py	built	season_model/team_strength.py
core/models/poisson.py	built	season_model/predictor.py (expected_goals) + evaluation.py (poisson_outcome_probs)
core/simulation.py	built	season_model/predictor.py (simulate_season)
core/evaluation/*	built	season_model/evaluation.py
core/state.py, core/models/base.py, core/ratings/base.py	to extract	interfaces implied by today's function signatures
analyses/match_outcomes	built	notebook 03, sections 1 to 3
analyses/points_projection	built	predicted_table + backtest table scores
analyses/final_position	partly built	position_matrix, position_probabilities
analyses/points_targets	planned	
analyses/what_if	planned	
analyses/form_and_trends	planned	
analyses/historical	planned	needs several complete seasons (pipeline can now fetch past seasons by epoca_id)
core/ratings/elo.py, core/models/negative_binomial.py, core/models/dixon_coles.py	planned	evaluation showed overdispersion and over-predicted draws
The core
Data contract

Every processed season has two tables. Analyses rely on these columns and nothing else from the raw scrape.

table	columns
fixtures_played.csv	Numeric Matchweek, Matchweek, Home Team, Away Team, Home Goals, Away Goals, Winner
fixtures_remaining.csv	Numeric Matchweek, Matchweek, Home Team, Away Team

Team names are slugs from SeasonConfig.team_name_mapping. Result from zerozero is always home-away, and processing assigns goals through Location, never by reading the score left to right.

Seasons

A season is a SeasonConfig: the league's exact zerozero competition name, one fixtures-page URL per team, and the zerozero season id epoca_id (154 = 2024/25, 155 = 2025/26). Every URL is pinned to epoca_id; a URL without it shows whatever season is current. Add seasons to SEASONS in core/config.py, or with define_season() from a notebook.

Ratings and match models

Both sit behind small interfaces, so the simulator and every analysis work with any combination:

python
class Ratings(Protocol):
    def fit(self, played: pd.DataFrame) -> "Ratings": ...

class MatchModel(Protocol):
    def goal_grid(self, home: str, away: str) -> np.ndarray: ...      # P(home goals = i, away goals = j)
    def outcome_probs(self, home: str, away: str) -> tuple[float, float, float]: ...

A new model is one class plus tests, and it is judged by the same backtest as the others.

Simulation

simulate(state, model, n_simulations, seed) draws every remaining fixture for every simulation at once and returns a SimulationResult with the raw per-sim arrays. It ranks with core/standings.py's tie-break rules, so a league with different tie-breaks changes one function, not every analysis.

Evaluation

Every analysis is scored the same way: a walk-forward backtest on finished seasons. For each cut-off matchweek k, fit on matchweeks ≤ k, predict the rest, compare with what happened, and compare against a baseline that any useful model must beat.

scoring rules	rps (ordered H/D/A), brier, log_loss, mae, interval_coverage
baselines	uniform, base_rates (training H/D/A shares), ppg (points per game carried forward)
comparing two variants	paired bootstrap over the same matches; a difference counts only if its CI excludes 0
The analyses

Each analysis answers one question about teams, points or standings. All of them follow the same contract:

analyses/<name>/
├── __init__.py
├── analysis.py      # functions: (SeasonState | SimulationResult, ...) -> DataFrame
├── evaluate.py      # how it is backtested: metric + baseline, via core/evaluation
└── README.md        # question, inputs, outputs, method, evaluation, status

plus notebooks/analyses/<name>/ and tests/analyses/<name>/.

analysis	question	main output	evaluated with
match_outcomes	What are the chances of each result in a fixture?	per fixture: p_home, p_draw, p_away, expected goals	RPS vs uniform / base_rates; calibration
points_projection	How many points will each team finish on?	per team: mean, median, 80 % / 95 % interval of final points	points MAE vs ppg; interval coverage
final_position	What are the chances team T finishes in place X (or top N, bottom N)?	team × position probability matrix; title / promotion / relegation %	RPS over positions; Brier on title and relegation; log score of the actual finish
points_targets	How many points does team T need for place X? When is a place safe or out of reach?	per place: points needed at 50 / 80 / 95 % confidence; "magic numbers"	coverage of the stated confidence on finished seasons
what_if	How does the table change if chosen matches end a given way?	baseline vs scenario: Δ points, Δ position probabilities	not backtested (counterfactual); checked for consistency with final_position
form_and_trends	Who is improving or fading? How do home and away differ?	rolling points / goals, ratings by matchweek, venue splits	descriptive; any predictive claim goes through the backtest
historical	How many points did champions, top-3 and relegated teams need across seasons?	per league and season: points at each place	descriptive; feeds points_targets as a prior

Most of these are summaries of one SimulationResult:

python
from football_analysis.core.config import get_season
from football_analysis.core.state import SeasonState
from football_analysis.core.ratings.attack_defence import AttackDefence
from football_analysis.core.models.poisson import Poisson
from football_analysis.core.simulation import simulate
from football_analysis.analyses import final_position, points_projection, points_targets

state = SeasonState.load(get_season("mansores_2025_26")).cut_at_matchweek(15)
model = Poisson(AttackDefence().fit(state.played), venue="fit")
sims = simulate(state, model, n_simulations=10_000, seed=42)

points_projection.summary(sims)                      # expected points + intervals
final_position.matrix(sims)                          # P(place X) for every team
final_position.probability(sims, "mansores", top=1)  # title chance
points_targets.needed(sims, place=3, confidence=0.8) # points for 3rd at 80 %
Adding a new analysis
Write the question as one sentence. If it is not about teams, points or standings, it doesn't belong in this repo.
Create analyses/<name>/ with the four files above. Inputs are a SeasonState or a SimulationResult; outputs are DataFrames.
Decide how it is evaluated (metric + baseline) in evaluate.py, or say in its README why it is descriptive only.
Add a notebook under notebooks/analyses/<name>/ and tests under tests/analyses/<name>/.
Add a row to the analyses table above.

If the analysis needs something the core doesn't have (a new rating, a new model, a tie-break rule), add it to the core with its own tests, so the next analysis can use it too.

Setup
bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
jupyter lab notebooks/
pytest

Python 3.9+. Scraping needs Google Chrome and selenium; everything else runs without them.

Getting a season's data
bash
python -m football_analysis.core.data.cli mansores_2025_26             # scrape + process + validate
python -m football_analysis.core.data.cli mansores_2025_26 --no-scrape # re-process raw only

or notebooks/core/01_data_pipeline.ipynb. Scraping resumes where it stopped: teams already on disk are skipped, so after zerozero's rate-limit page just wait a few minutes and run it again.

Data in the repo
season	coverage	use
fermedo_2024_25	complete: 16 teams, 240 matches	backtests
mansores_2025_26	partial: Mansores' 22 fixtures, scraped to 2026-01-17	re-scrape all 12 teams to complete it; the season has finished
Important instructions
Dependency direction is one way: analyses → core. The core never imports an analysis, and analyses never import each other. If two analyses need the same thing, it belongs in the core.
Every analysis starts from a SeasonState. Never read raw CSVs or call the scraper from an analysis; the data contract above is the only interface.
No look-ahead. A prediction at matchweek k uses only matches ≤ k: ratings, venue factors, base rates, everything. cut_at_matchweek() is the only way to build a historical state.
Keep simulations raw. SimulationResult holds per-simulation arrays. Averaging happens in the analysis that needs it, once. Averaging twice is the bug the original notebook had (Draws_Predicted: 965).
A prediction isn't done until it is evaluated. Each predictive analysis has a backtest against a baseline in evaluate.py. Differences between model variants need the paired bootstrap, not eyeballing.
Read validate_season() before trusting any output. With partial coverage, every team except the scraped one is rated from a handful of games.
Pin every season to its epoca_id, keep competition_name to the league only (copied from competitions_found(), not typed), and assign goals through Location: Result is always home-away.
Respect zerozero's rate limit. On a rate-limit error, wait and re-run; don't add retry loops.
Logic lives in src/, with tests; notebooks call it. Notebook findings are printed from the run, never typed into markdown, so they can't go stale.
Seasons are config, not code. No team or competition name is hardcoded outside core/config.py.
