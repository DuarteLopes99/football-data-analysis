"""Generic season data layer: config, scraping, pipeline, fixtures, league table.

Every analysis reads its data through here. Nothing in this package depends on
``football_data_analysis.analyses``.
"""

from football_data_analysis.core.fixtures import dedupe_fixtures, split_played_remaining
from football_data_analysis.core.league_table import compute_league_table

__all__ = ["compute_league_table", "dedupe_fixtures", "split_played_remaining"]
