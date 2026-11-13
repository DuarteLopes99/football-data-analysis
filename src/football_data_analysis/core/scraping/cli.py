"""CLI: scrape and process fixtures for a configured season.

Usage:
    python -m football_data_analysis.core.scraping.cli mansores_2025_26
    python -m football_data_analysis.core.scraping.cli mansores_2025_26 --overwrite --teams mansores crc_vale
    python -m football_data_analysis.core.scraping.cli mansores_2025_26 --no-scrape     # re-process raw only

Resumable: teams already on disk are skipped unless --overwrite. If zerozero's
rate limit is hit, wait a few minutes and run the same command again.
"""

from __future__ import annotations

import argparse
import sys

from football_data_analysis.core.config import get_season, list_seasons
from football_data_analysis.core.pipeline import process_season, scrape_season, validate_season


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("season", help=f"One of: {', '.join(s.key for s in list_seasons())}")
    parser.add_argument("--teams", nargs="*", help="Only these team slugs")
    parser.add_argument("--overwrite", action="store_true", help="Re-scrape teams already on disk")
    parser.add_argument("--no-scrape", action="store_true", help="Skip scraping, only re-process raw files")
    parser.add_argument("--no-headless", action="store_true", help="Show the browser window")
    args = parser.parse_args(argv)

    season = get_season(args.season)
    if not args.no_scrape:
        print(f"Scraping {season.label} (epoca_id={season.epoca_id}, {season.n_teams} teams)...")
        report = scrape_season(season, teams=args.teams, overwrite=args.overwrite, headless=not args.no_headless)
        print(report.to_frame().to_string(index=False))
        if report.rate_limited:
            print("\nRate limited by zerozero.pt. Wait a few minutes and run the same command again.")
            return 2

    played, remaining = process_season(season)
    print(f"\nProcessed: {len(played)} played, {len(remaining)} remaining -> {season.processed_dir}")
    print(validate_season(season, played, remaining).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
