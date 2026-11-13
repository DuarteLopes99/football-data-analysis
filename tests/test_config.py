from season_model.config import FERMEDO_2024_25, MANSORES_2025_26, define_season, epoca_id_for, get_season, with_epoca


def test_every_team_url_is_pinned_to_the_season_id():
    """Without epoca_id a zerozero "jogos" page shows the *current* season, so a
    2025/26 re-scrape run during 2026/27 would silently fetch the wrong year."""
    for season in (MANSORES_2025_26, FERMEDO_2024_25):
        for url in season.team_urls.values():
            assert f"epoca_id={season.epoca_id}" in url
            assert "grp=1" in url


def test_with_epoca_replaces_an_existing_id_instead_of_appending():
    url = with_epoca("https://www.zerozero.pt/equipa/x/1/jogos?grp=1&epoca_id=150", 155)
    assert url.count("epoca_id") == 1 and url.endswith("epoca_id=155")


def test_epoca_id_matches_the_two_known_seasons():
    assert epoca_id_for(2024) == FERMEDO_2024_25.epoca_id == 154
    assert epoca_id_for(2025) == MANSORES_2025_26.epoca_id == 155


def test_define_season_registers_for_the_session():
    s = define_season("test_league_2026_27", "Test League 26/27", "a", {"a": "https://x/jogos", "b": "https://y/jogos"}, epoca_id=156)
    assert get_season("test_league_2026_27") is s
    assert s.expected_matches == 2
