# football-data-analysis

Modelling and analysis of amateur football leagues from
[zerozero.pt](https://www.zerozero.pt) data, always about **teams, points and
league tables**. Notebook-first: no dashboard, no frontend, a small tested
package that the notebooks call.

The repository is layered. A generic **core** gets any season into tidy,
validated tables; on top of it, each kind of analysis is its own package with
its own notebooks, tests and doc. Season prediction (Poisson + Monte Carlo
final table, with an honest evaluation against baselines) is the first one.

Split out of [Football-Stats-Data](https://github.com/DuarteLopes99/Football-Stats-Data)
in November 2026 (first as `Football-Season-Model`). That repo keeps the
personal GPS dashboard and reads only `mansores_fixtures.csv` from here.

## How it is organised

```
                 ┌──────────────────────── analyses ─────────────────────────┐
                 │  season_prediction          players          <next one>   │
                 │  strength, Monte Carlo,     per-player       ...          │
                 │  backtest                   season stats                  │
                 └───────────────────────────────┬───────────────────────────┘
                                                 │ reads played / remaining fixtures
┌────────────────────────────────────────── core ──────────────────────────────────────────┐
│  SeasonConfig + SEASONS → scrape (zerozero.pt) → raw → process → processed → validate   │
│  fixtures, league table                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                                 │
                                    data/seasons/<key>/{raw,processed}/
```

| layer | package | notebooks | doc | status |
|---|---|---|---|---|
| core | `football_data_analysis.core` | [`core/01_zerozero_pipeline`](notebooks/core/01_zerozero_pipeline.ipynb) | [`docs/core.md`](docs/core.md) | in use |
| analysis | `football_data_analysis.analyses.season_prediction` | [`season_prediction/02_season_exploration`](notebooks/season_prediction/02_season_exploration.ipynb), [`season_prediction/03_model_evaluation`](notebooks/season_prediction/03_model_evaluation.ipynb) | [`docs/season_prediction.md`](docs/season_prediction.md) | in use |
| analysis | `football_data_analysis.analyses.players` | none yet | [`docs/players.md`](docs/players.md) | code only, untested |

## Notebooks

| notebook | question it answers |
|---|---|
| [`core/01_zerozero_pipeline`](notebooks/core/01_zerozero_pipeline.ipynb) | Get a season's fixtures from zerozero.pt into tidy, validated tables. Scraping is behind a `RUN_SCRAPE` flag, so it runs offline on the stored data. |
| [`season_prediction/02_season_exploration`](notebooks/season_prediction/02_season_exploration.ipynb) | What does the data look like, and does it support the model's assumptions (Poisson goals, home advantage, strength)? |
| [`season_prediction/03_model_evaluation`](notebooks/season_prediction/03_model_evaluation.ipynb) | Standing at matchweek *k*, how well does the model call the rest of the season, and does it beat the baselines? Then: apply it to the current season. |

Season prediction, on the complete 2024/25 season (notebook 03 prints the
current numbers in its findings cell): the model's match probabilities score
**about 43 % better RPS than a uniform guess** (0.140 vs 0.245), and its
simulated final table beats carrying points-per-game forward (points MAE 4.6 vs
5.7) at most cut-offs. Fitted vs fixed home advantage makes no measurable
difference. Goals are overdispersed (variance about 2× the mean), which is the
obvious next thing to model.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
jupyter lab notebooks/
pytest                       # 28 tests, ~2 s
```

Python 3.9+. Notebooks also run without `pip install -e .` (they find the repo
root and add `src/` to the path). Scraping additionally needs Google Chrome;
everything else works without it.

## Getting data for a season

```bash
python -m football_data_analysis.core.scraping.cli mansores_2025_26               # scrape + process + validate
python -m football_data_analysis.core.scraping.cli mansores_2025_26 --no-scrape   # re-process raw only
```

or section 2 of notebook `core/01`. A new season is a `SeasonConfig` (league
name, team URLs, zerozero `epoca_id`), added to `SEASONS` in
`src/football_data_analysis/core/config.py` or built in the notebook with
`define_season()`. Full walkthrough in [`docs/core.md`](docs/core.md).

## Adding a new analysis

An analysis is a new question about teams, points or tables (for example
expected points against actual, form and streaks, head-to-head, or season
comparisons). Each one gets the same four pieces, named the same:

```
src/football_data_analysis/analyses/<name>/   # logic, with an __init__ that says what it answers
notebooks/<name>/                              # numbered after the existing notebooks
tests/<name>/
docs/<name>.md
```

It reads fixtures through `core.pipeline.load_season` and checks
`validate_season` first. If a second analysis needs something an existing one
already has (a helper, a metric, a data transform), that code moves down into
`core` with its test, rather than one analysis importing another.

## Repository layout

```
football-data-analysis/
├── src/football_data_analysis/
│   ├── core/                          # generic: any analysis builds on this
│   │   ├── config.py                  # SeasonConfig, SEASONS registry, epoca_id handling
│   │   ├── pipeline.py                # scrape_season → process_season → validate_season, load_season
│   │   ├── scraping/                  # zerozero.pt Selenium client + CLI
│   │   ├── fixtures.py                # raw per-team exports → deduplicated played/remaining
│   │   └── league_table.py
│   └── analyses/
│       ├── season_prediction/
│       │   ├── team_strength.py       # attack / defence relative to league average
│       │   ├── predictor.py           # Poisson goals, vectorised Monte Carlo season
│       │   └── evaluation.py          # scoring rules, baselines, walk-forward backtest
│       └── players/                   # match reports → per-player stats (no notebook yet)
├── notebooks/
│   ├── core/                          # 01 pipeline
│   └── season_prediction/             # 02 exploration · 03 evaluation
├── tests/
│   ├── core/
│   └── season_prediction/
├── data/seasons/<key>/{raw,processed}/
└── docs/                              # core.md · season_prediction.md · players.md
```

## Important instructions

**Layers**

- **`core` never imports from `analyses`.** Analyses depend on core, and on
  nothing else in the repo. Shared logic moves down into `core`.
- **Logic lives in the package, notebooks call it.** If a notebook cell grows
  into something reusable, move it into the right layer with a test.
- **Keep notebook conclusions computed, not typed.** Findings cells print their
  numbers from the run; don't hard-code results in markdown cells.

**Core data**

- **Pin every season to its `epoca_id`.** A zerozero "jogos" URL without it
  shows the *current* season. `SeasonConfig.team_urls` enforces it; scrape
  through `pipeline.scrape_season` (or the CLI), never by passing `teams` URLs
  to the client directly.
- **Adding a season is a config change, not a code change.** Don't hardcode a
  team or competition name in `pipeline.py`, `fixtures.py` or any analysis.
- **`competition_name` is the league only, copied exactly.** Cup ties and
  play-offs would corrupt the table and every analysis. Read it from
  `competitions_found()` after a first scrape rather than typing it.
- **`Result` is always home-away**, whichever side the tracked team is on. Assign
  goals through `Location`, never left-to-right. This was a real bug (see
  `docs/core.md`).
- **Respect the rate limit.** On a `RateLimitedError`, wait a few minutes and
  re-run; finished teams are skipped. Don't add retry loops.
- **After scraping, re-process.** The scraper writes `raw/`; analyses read
  `processed/`. `run_pipeline()` and the CLI do both.
- **Read `validate_season()` before trusting any analysis.** With partial
  coverage (e.g. `mansores_2025_26`, one team's fixtures only) every other team
  is described by a single match.
- **`data/seasons/**` is the dataset and is tracked**, except the
  `*_all_competitions.csv` scrape by-products, which are gitignored.
  `mansores_2025_26/raw/mansores_fixtures.csv` is also read by
  Football-Stats-Data; it is produced here.

**Season prediction (and any model added later)**

- **Evaluate on finished seasons only, and never fit on test matchweeks.**
  `backtest()` fits strength and venue factors on matchweeks ≤ cut-off. Any new
  model goes through the same `backtest()` against the same baselines
  (`uniform`, `base_rates`, `ppg`), with RPS as the headline score.
- **Differences between model variants are judged with the paired bootstrap**
  in notebook 03, not by eye.
