# Football Season Model

Notebook-first modelling of amateur football league seasons from
[zerozero.pt](https://www.zerozero.pt) data: a **data pipeline** that recovers
the fixtures of a specific season, a **Poisson + Monte Carlo model** of the
final table, and an **honest evaluation** of that model against baselines.
No dashboard, no frontend: three notebooks on top of a small, tested package.

Split out of [Football-Stats-Data](https://github.com/DuarteLopes99/Football-Stats-Data),
which keeps the personal GPS dashboard.

## Notebooks

| notebook | question it answers |
|---|---|
| [`01_zerozero_pipeline`](notebooks/01_zerozero_pipeline.ipynb) | Get a season's fixtures from zerozero.pt into tidy, validated tables. Scraping is behind a `RUN_SCRAPE` flag, so it runs offline on the stored data. |
| [`02_season_exploration`](notebooks/02_season_exploration.ipynb) | What does the data look like, and does it support the model's assumptions (Poisson goals, home advantage, strength)? |
| [`03_model_evaluation`](notebooks/03_model_evaluation.ipynb) | Standing at matchweek *k*, how well does the model call the rest of the season, and does it beat the baselines? Then: apply it to the current season. |

Headline from notebook 03 on the complete 2024/25 season: the model's match
probabilities score **~43 % better RPS than a uniform guess**, and its
simulated final table beats carrying points-per-game forward at most cut-offs.
Fitted vs fixed home advantage makes no measurable difference. Goals are
overdispersed (variance ≈ 2× the mean), which is the obvious next thing to model.

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

Python 3.9+. Notebooks also run without `pip install -e .` (they add `src/` to
the path). Scraping additionally needs Google Chrome; everything else works
without it.

## Getting data for a season

```bash
python -m season_model.scraping.cli mansores_2025_26           # scrape + process + validate
python -m season_model.scraping.cli mansores_2025_26 --no-scrape   # re-process raw only
```

or section 2 of notebook 01. A new season is a `SeasonConfig` (league name,
team URLs, zerozero `epoca_id`), added to `SEASONS` in
`src/season_model/config.py` or built in the notebook with `define_season()`.
Full walkthrough in [`docs/season_model.md`](docs/season_model.md).

## Repository layout

```
Football-Season-Model/
├── notebooks/                  # 01 pipeline · 02 exploration · 03 evaluation
├── src/season_model/
│   ├── config.py               # SeasonConfig, SEASONS registry, epoca_id handling
│   ├── pipeline.py             # scrape_season → process_season → validate_season
│   ├── scraping/               # zerozero.pt Selenium client + CLI
│   ├── fixtures.py             # raw per-team exports → deduplicated played/remaining
│   ├── league_table.py
│   ├── team_strength.py        # attack / defence relative to league average
│   ├── predictor.py            # Poisson goals, vectorised Monte Carlo season
│   ├── evaluation.py           # scoring rules, baselines, walk-forward backtest
│   └── players/                # lineups / events → per-player stats (not used by the model)
├── data/seasons/<key>/{raw,processed}/
├── docs/season_model.md        # the detailed reference
└── tests/
```

## Important instructions

- **Pin every season to its `epoca_id`.** A zerozero "jogos" URL without it
  shows the *current* season. `SeasonConfig.team_urls` enforces it; scrape
  through `pipeline.scrape_season` (or the CLI), never by passing `teams` URLs
  to the client directly.
- **Adding a season is a config change, not a code change.** Don't hardcode a
  team or competition name in `pipeline.py`, `fixtures.py` or the model.
- **`competition_name` is the league only, copied exactly.** Cup ties and
  play-offs would corrupt the table and the predictor. Read it from
  `competitions_found()` after a first scrape rather than typing it.
- **`Result` is always home-away**, whichever side the tracked team is on. Assign
  goals through `Location`, never left-to-right. This was a real bug (see docs).
- **Respect the rate limit.** On a `RateLimitedError`, wait a few minutes and
  re-run; finished teams are skipped. Don't add retry loops.
- **After scraping, re-process.** The scraper writes `raw/`; models read
  `processed/`. `run_pipeline()` and the CLI do both.
- **Read `validate_season()` before trusting a prediction.** With partial
  coverage (e.g. `mansores_2025_26`, one team's fixtures only) every other team's
  strength comes from a single match.
- **Evaluate on finished seasons only, and never fit on test matchweeks.**
  `backtest()` fits strength and venue factors on matchweeks ≤ cut-off. Any new
  model goes through the same `backtest()` against the same baselines
  (`uniform`, `base_rates`, `ppg`), and differences between model variants are
  judged with the paired bootstrap in notebook 03, not by eye.
- **Keep notebook conclusions computed, not typed.** The findings cell in
  notebook 03 prints its numbers from the run; don't hard-code results in
  markdown cells.
- **Logic lives in `src/season_model`, notebooks call it.** If a notebook cell
  grows into something reusable, move it into the package with a test.
- **`data/seasons/**` is the dataset and is tracked**, except the
  `*_all_competitions.csv` scrape by-products, which are gitignored.
