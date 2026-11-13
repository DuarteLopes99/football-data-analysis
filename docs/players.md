# Analysis: players

`src/football_data_analysis/analyses/players` turns zerozero.pt match reports
into per-player tables. It is code only for now: no notebook and no tests yet,
and nothing in season prediction depends on it.

* Input: `core.scraping.zerozero_client.scrape_season_match_reports(urls)`
  returns one row per player per match (starters, subs, goals, assists, cards).
* `players.match_events.build_events_table()` and
  `build_player_season_stats()` turn that into event and per-player season
  tables.

Minutes are estimated, not scraped: starters play until subbed off (else 90),
substitutes from their sub-in minute (else 0).

Before building on it, give it the same shape as season prediction: a notebook
in `notebooks/players/`, tests in `tests/players/`, and a scraped dataset under
`data/seasons/<key>/`.
