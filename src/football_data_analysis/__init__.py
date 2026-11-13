"""Football data analysis on zerozero.pt league data.

Two layers:

* ``core``: everything about getting a season into tidy tables, independent of
  any question asked of it. ``SeasonConfig`` and the season registry, the
  zerozero.pt scraper, the scrape -> process -> validate pipeline, fixture
  handling and the league table. Nothing in ``core`` imports from ``analyses``.
* ``analyses``: one subpackage per question, built on ``core``.
  ``season_prediction`` (team strength, Poisson + Monte Carlo season,
  walk-forward evaluation) and ``players`` (per-player stats from match reports).
"""
