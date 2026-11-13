# Core: season data from zerozero.pt

`src/football_data_analysis/core` is the layer every analysis builds on. It
answers one question, "what happened (and what is still to play) in this
season?", and knows nothing about models. Pipeline:
**SeasonConfig → scrape → raw → process → processed → validate → league table**.
Every stage is a plain function driven by a `SeasonConfig`; nothing is
hardcoded to one team or season. Notebook:
[`notebooks/core/01_zerozero_pipeline`](../notebooks/core/01_zerozero_pipeline.ipynb).

## 1. Declaring a season

Everything about a season lives in one `SeasonConfig` in
[`core/config.py`](../src/football_data_analysis/core/config.py):

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
python -m football_data_analysis.core.scraping.cli mansores_2025_26               # every team
python -m football_data_analysis.core.scraping.cli mansores_2025_26 --teams crc_vale --overwrite
python -m football_data_analysis.core.scraping.cli mansores_2025_26 --no-scrape   # re-process raw only
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

Selenium is imported inside `scrape_season`, so processing, the analyses and the
tests run on a machine without Chrome.

The same client also scrapes match reports
(`scrape_season_match_reports(urls)`), the input of the
[players analysis](players.md).

## 3. Processing (`pipeline.process_season`)

1. Load each team's raw file and keep `Competition == competition_name` (the
   Mansores export carries two Taça Pecol rows that must not reach the table).
2. Turn `Location` (`(C)` casa / `(F)` fora) into explicit `Home Team` /
   `Away Team`, and `Result` into `Home Goals` / `Away Goals`.
   **`Result` is always "home score-away score"**, whichever side the tracked
   team is on (see the bug below).
3. Deduplicate: every match appears once in each participating team's export.
   `dedupe_fixtures()` keys on `(Matchweek, sorted(home, away))`.

Output: `processed/fixtures_played.csv` and `processed/fixtures_remaining.csv`,
which is what every analysis reads (through `pipeline.load_season`).
`fermedo_2024_25` predates the per-team raw layout (its raw folder holds a single
tidy export), so it is read from `processed/` directly.

## 4. Validation (`pipeline.validate_season`)

Returns a table of checks: coverage against a full double round-robin
(`n·(n−1)` matches), teams with an incomplete fixture list, team names that
didn't map to a slug, duplicate home/away pairings, missing or negative scores.
Coverage is the one that matters for any analysis: with one team's page only,
every other team is described by a single match.

## 5. League table (`league_table.compute_league_table`)

```python
table = compute_league_table(played)      # Points, W/D/L, GF/GA, GD, Played; sorted by Points, GD
```

## Known bug fixed: home/away score swap

The source notebooks (`dev_model.ipynb`, `Dev_Mansores_Predict.ipynb`) read
`Result` as "tracked team - opponent" when the tracked team played away; it is
always "home - away". Some away wins were recorded as home wins for the
opponent. Before the fix Mansores' 11 games computed as 4W-0D-7L (12 pts);
after, the correct 10W-0D-1L (30 pts). Regression test:
`tests/core/test_fixtures.py`.

## Data in the repo

* **`fermedo_2024_25`**: complete. 16 teams, 240 matches, double round-robin, no
  remaining fixtures. The backtest season of the season prediction analysis and
  the check in `tests/core/test_data_seed.py`.
* **`mansores_2025_26`**: partial. Mansores' own 22 league fixtures (11 played,
  11 remaining as of the 2026-01-17 scrape). Mansores' row is exact; every other
  row reflects one match. The season has since finished: re-scrape all teams
  (the URLs are pinned to `epoca_id=155`) to get the full, final 2025/26 league,
  which becomes a second complete season for every analysis.
