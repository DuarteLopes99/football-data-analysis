import pandas as pd
import pytest

from season_model import config as cfg
from season_model.pipeline import competitions_found, process_season, validate_season


def _row(team1, location, team2, result, competition, matchweek, played):
    return {
        "Result - abv": "", "Date": "2025-10-01", "Hour": "15:30", "Location": location, "Team2": team2,
        "Result": result, "Competition": competition, "Matchweek": matchweek, "Played?": played, "Team1": team1,
    }


@pytest.fixture
def season(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "DATA_ROOT", tmp_path)
    s = cfg.SeasonConfig(key="t_2025_26", label="t", competition_name="League", primary_team="a",
                         teams={"a": "https://x/a/jogos", "b": "https://x/b/jogos"})
    # Patch the module global used by the dir property.
    monkeypatch.setattr(cfg.SeasonConfig, "dir", property(lambda self: tmp_path / "seasons" / self.key))
    a = pd.DataFrame([
        _row("a", "(C)", "b", "2-1", "League", "J1", True),
        _row("a", "(F)", "b", "-", "League", "J2", False),
        _row("a", "(C)", "cupside", "5-0", "Cup", "3", True),   # cup tie: must not reach the table
    ])
    b = pd.DataFrame([
        _row("b", "(F)", "a", "2-1", "League", "J1", True),
        _row("b", "(C)", "a", "-", "League", "J2", False),
    ])
    a.to_csv(s.raw_dir / "a_fixtures.csv", index=False)
    a.to_csv(s.raw_dir / "a_all_competitions.csv", index=False)
    b.to_csv(s.raw_dir / "b_fixtures.csv", index=False)
    return s


def test_process_dedupes_and_drops_other_competitions(season):
    played, remaining = process_season(season)
    assert len(played) == 1 and len(remaining) == 1
    assert "cupside" not in set(played["Away Team"])
    assert (season.processed_dir / "fixtures_played.csv").exists()


def test_validate_flags_a_complete_two_team_season_as_ok(season):
    played, remaining = process_season(season)
    checks = validate_season(season, played, remaining).set_index("check")
    assert checks["ok"].all(), checks


def test_validate_flags_partial_coverage(season):
    played, remaining = process_season(season)
    checks = validate_season(season, played, remaining.iloc[0:0]).set_index("check")
    assert not checks.loc["coverage: matches vs full double round-robin", "ok"]


def test_competitions_found_lists_cup_and_league(season):
    comps = competitions_found(season).set_index("Competition")
    assert comps.loc["League", "is_league"] and not comps.loc["Cup", "is_league"]


def test_process_without_raw_files_says_what_to_run(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.SeasonConfig, "dir", property(lambda self: tmp_path / self.key))
    empty = cfg.SeasonConfig(key="empty", label="e", competition_name="L", primary_team="a", teams={"a": "u"})
    with pytest.raises(FileNotFoundError, match="scrape_season"):
        process_season(empty)


def test_seeded_mansores_raw_reprocesses_to_the_stored_tables():
    """The raw Mansores export carries two Taça rows; reprocessing must still
    give the 11 + 11 league fixtures that are stored."""
    season = cfg.get_season("mansores_2025_26")
    played, remaining = process_season(season, save=False)
    assert len(played) == 11 and len(remaining) == 11
