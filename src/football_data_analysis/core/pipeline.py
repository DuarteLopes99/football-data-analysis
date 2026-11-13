"""zerozero.pt -> tidy season tables, for any configured season.

Three stages, each one callable on its own from a notebook:

1. ``scrape_season``: one headless Chrome session, one fixtures page per team,
   pinned to the season's ``epoca_id``. Writes two files per team into
   ``data/seasons/<key>/raw/``:

   * ``<slug>_all_competitions.csv``: the page as scraped, every competition.
     Use it to find the exact ``competition_name`` for a new season.
   * ``<slug>_fixtures.csv``: the same rows filtered to the league.

   It is **resumable**: teams whose file already exists are skipped unless
   ``overwrite=True``, so a run that hits zerozero's rate limit can simply be
   re-run a few minutes later and picks up where it stopped.

2. ``process_season``: raw per-team files -> deduplicated
   ``processed/fixtures_played.csv`` and ``processed/fixtures_remaining.csv``.

3. ``validate_season``: coverage and consistency checks, returned as a table
   rather than printed, so a notebook can assert on them.

``load_season`` reads the processed tables back; nothing downstream reads raw.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd

from football_data_analysis.core.config import SeasonConfig, get_season
from football_data_analysis.core.fixtures import load_processed, load_raw_team_fixtures, save_processed, split_played_remaining

ALL_COMPETITIONS_SUFFIX = "_all_competitions.csv"
LEAGUE_SUFFIX = "_fixtures.csv"


def _as_season(season: SeasonConfig | str) -> SeasonConfig:
    return get_season(season) if isinstance(season, str) else season


# --------------------------------------------------------------------------- #
# 1. Scrape
# --------------------------------------------------------------------------- #


@dataclass
class ScrapeReport:
    scraped: list[str]
    skipped: list[str]
    failed: dict[str, str]
    rate_limited: bool

    def to_frame(self) -> pd.DataFrame:
        rows = [{"team": t, "status": "scraped", "detail": ""} for t in self.scraped]
        rows += [{"team": t, "status": "skipped (already on disk)", "detail": ""} for t in self.skipped]
        rows += [{"team": t, "status": "failed", "detail": d} for t, d in self.failed.items()]
        return pd.DataFrame(rows, columns=["team", "status", "detail"])


def scrape_season(
    season: SeasonConfig | str,
    teams: list[str] | None = None,
    overwrite: bool = False,
    headless: bool = True,
    wait_seconds: float = 5.0,
    pause_between_teams: float = 3.0,
) -> ScrapeReport:
    """Scrape the fixtures page of every team (or of ``teams``) for one season.

    Stops at the first rate-limit page instead of hammering the site: the
    report says ``rate_limited=True`` and the run can be repeated later.
    Selenium is imported here, not at module level, so processing and
    modelling work on a machine without Chrome.
    """
    from football_data_analysis.core.scraping.zerozero_client import RateLimitedError, chrome_driver, fetch_team_fixtures

    season = _as_season(season)
    urls = season.team_urls
    wanted = teams or list(urls)
    unknown = sorted(set(wanted) - set(urls))
    if unknown:
        raise KeyError(f"Not in {season.key}.teams: {unknown}")

    report = ScrapeReport(scraped=[], skipped=[], failed={}, rate_limited=False)
    todo = []
    for slug in wanted:
        if not overwrite and (season.raw_dir / f"{slug}{LEAGUE_SUFFIX}").exists():
            report.skipped.append(slug)
        else:
            todo.append(slug)
    if not todo:
        return report

    with chrome_driver(headless=headless) as driver:
        for i, slug in enumerate(todo):
            if i:
                time.sleep(pause_between_teams)
            try:
                df = fetch_team_fixtures(driver, slug, urls[slug], season.team_name_mapping, wait_seconds)
            except RateLimitedError as exc:
                report.failed[slug] = str(exc)
                report.rate_limited = True
                break
            except Exception as exc:  # layout change, timeout: record it and keep going
                report.failed[slug] = f"{type(exc).__name__}: {exc}"
                continue
            df.to_csv(season.raw_dir / f"{slug}{ALL_COMPETITIONS_SUFFIX}", index=False)
            league = df[df["Competition"] == season.competition_name]
            league.to_csv(season.raw_dir / f"{slug}{LEAGUE_SUFFIX}", index=False)
            report.scraped.append(slug)
    return report


def competitions_found(season: SeasonConfig | str) -> pd.DataFrame:
    """Every competition string in the all-competitions files, with row counts.

    The way to pick ``competition_name`` for a new season: scrape once with a
    placeholder, look here, then set the real string.
    """
    season = _as_season(season)
    frames = [pd.read_csv(p) for p in sorted(season.raw_dir.glob(f"*{ALL_COMPETITIONS_SUFFIX}"))]
    if not frames:
        return pd.DataFrame(columns=["Competition", "rows"])
    allc = pd.concat(frames, ignore_index=True)
    out = allc["Competition"].value_counts().rename_axis("Competition").reset_index(name="rows")
    out["is_league"] = out["Competition"] == season.competition_name
    return out


# --------------------------------------------------------------------------- #
# 2. Process
# --------------------------------------------------------------------------- #


def process_season(season: SeasonConfig | str, save: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Raw per-team files -> (played, remaining), deduplicated, league rows only."""
    season = _as_season(season)
    raw = load_raw_team_fixtures(season, league_only=True)
    if not raw:
        raise FileNotFoundError(
            f"No raw fixture files in {season.raw_dir}. Run scrape_season('{season.key}') first."
        )
    played, remaining = split_played_remaining(raw)
    if save:
        save_processed(season, played, remaining)
    return played, remaining


def load_season(season: SeasonConfig | str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Processed (played, remaining) tables for a season."""
    return load_processed(_as_season(season))


# --------------------------------------------------------------------------- #
# 3. Validate
# --------------------------------------------------------------------------- #


def validate_season(
    season: SeasonConfig | str, played: pd.DataFrame | None = None, remaining: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Data-quality checks as a table: check, ok, value, detail.

    Coverage is the one that matters most for modelling: a season scraped from
    one team's page only knows that team's matches, and every other team's
    strength is then estimated from a single game.
    """
    season = _as_season(season)
    if played is None or remaining is None:
        played, remaining = load_season(season)

    known = set(season.teams)
    all_matches = pd.concat([played.assign(_played=True), remaining.assign(_played=False)], ignore_index=True)
    seen = set(all_matches["Home Team"]).union(all_matches["Away Team"]) if not all_matches.empty else set()
    unmapped = sorted(seen - known)
    n_total = len(all_matches)

    pair_key = all_matches.apply(lambda r: (r["Home Team"], r["Away Team"]), axis=1) if n_total else pd.Series([], dtype=object)
    dup_pairs = int(pair_key.duplicated().sum()) if n_total else 0

    per_team = (
        pd.concat([all_matches["Home Team"], all_matches["Away Team"]]).value_counts()
        if n_total
        else pd.Series(dtype=int)
    )
    expected_per_team = 2 * (season.n_teams - 1)
    short_teams = sorted(t for t in known if per_team.get(t, 0) < expected_per_team)

    negative_goals = int(((played["Home Goals"] < 0) | (played["Away Goals"] < 0)).sum()) if not played.empty else 0

    checks = [
        {
            "check": "coverage: matches vs full double round-robin",
            "ok": n_total == season.expected_matches,
            "value": f"{n_total} / {season.expected_matches}",
            "detail": "partial scrape: other teams' strengths rest on very few games" if n_total < season.expected_matches else "",
        },
        {
            "check": "every team has its full fixture list",
            "ok": not short_teams,
            "value": f"{len(known) - len(short_teams)} / {len(known)} teams",
            "detail": ", ".join(short_teams[:8]) + (" ..." if len(short_teams) > 8 else ""),
        },
        {
            "check": "team names all mapped to slugs",
            "ok": not unmapped,
            "value": len(unmapped),
            "detail": ", ".join(unmapped) + (" -> add to team_name_mapping" if unmapped else ""),
        },
        {
            "check": "no duplicate home/away pairing",
            "ok": dup_pairs == 0,
            "value": dup_pairs,
            "detail": "same home/away pair listed twice: dedupe failed or a cup tie leaked in" if dup_pairs else "",
        },
        {
            "check": "no negative / missing scores in played",
            "ok": negative_goals == 0 and not played[["Home Goals", "Away Goals"]].isna().any().any() if not played.empty else True,
            "value": negative_goals,
            "detail": "",
        },
        {
            "check": "played matches",
            "ok": True,
            "value": len(played),
            "detail": f"{len(remaining)} remaining",
        },
    ]
    return pd.DataFrame(checks)


def run_pipeline(season: SeasonConfig | str, scrape: bool = True, **scrape_kwargs) -> dict:
    """Scrape (optionally) -> process -> validate, in one call. Returns every intermediate."""
    season = _as_season(season)
    report = scrape_season(season, **scrape_kwargs) if scrape else None
    played, remaining = process_season(season)
    return {
        "season": season,
        "scrape_report": report,
        "played": played,
        "remaining": remaining,
        "validation": validate_season(season, played, remaining),
    }
