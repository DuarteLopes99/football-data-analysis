"""Season/competition configuration.

Each season is described declaratively (team slugs, their zerozero.pt fixtures
pages, the zerozero season id and the exact competition name to filter on), so
the pipeline and the model never hardcode a team or a season. A new season or
division is a new ``SeasonConfig``, either added to ``SEASONS`` below or built
inline in a notebook with ``define_season()``.

**Why ``epoca_id`` matters.** A zerozero "jogos" URL without ``epoca_id`` shows
the *current* season. That is fine while a season is live and silently wrong
the day the next one starts: re-scraping "2025/26" in November 2026 without it
returns 2026/27 fixtures. Every URL is therefore pinned to the config's
``epoca_id`` by ``SeasonConfig.team_urls``, whatever the stored URL says.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"

# Two seasons with a known zerozero id: 2024/25 -> 154 and 2025/26 -> 155. The
# ids look sequential per season, which is what ``epoca_id_for`` assumes.
# Check the "Época" selector on any zerozero team page before trusting a
# value it computes for a season further away from these two.
_EPOCA_ANCHOR_START_YEAR = 2025
_EPOCA_ANCHOR_ID = 155


def epoca_id_for(start_year: int) -> int:
    """zerozero.pt ``epoca_id`` for the season starting in ``start_year`` (2025 -> 2025/26).

    Extrapolated from the two known ids (154 = 2024/25, 155 = 2025/26). Verify
    on the site for anything more than a season or two away.
    """
    return _EPOCA_ANCHOR_ID + (start_year - _EPOCA_ANCHOR_START_YEAR)


def with_epoca(url: str, epoca_id: int | None) -> str:
    """Return ``url`` with its ``epoca_id`` query parameter set (or left alone if ``None``)."""
    if epoca_id is None:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["epoca_id"] = str(epoca_id)
    query.setdefault("grp", "1")
    return urlunsplit(parts._replace(query=urlencode(query)))


@dataclass(frozen=True)
class SeasonConfig:
    key: str
    """Directory-safe identifier, e.g. ``mansores_2025_26`` -> ``data/seasons/<key>/``."""

    label: str
    """Human-readable name shown in notebooks."""

    competition_name: str
    """Exact zerozero.pt competition string used to filter scraped fixture rows.

    This is the **league** only. The table and the Monte Carlo prediction are
    defined over a single round-robin competition, and cup ties or play-off
    rounds would corrupt both. Copy it from a scraped row (the pipeline keeps
    an all-competitions file for exactly this) rather than guessing.
    """

    primary_team: str
    """Slug (key into ``teams``) of the team this season's collection is centred on."""

    teams: dict[str, str] = field(default_factory=dict)
    """Team slug -> zerozero.pt "jogos" (fixtures) page URL."""

    team_name_mapping: dict[str, str] = field(default_factory=dict)
    """zerozero.pt display name (as it appears in scraped tables) -> team slug."""

    epoca_id: int | None = None
    """zerozero.pt season id. Pinned onto every team URL by ``team_urls``."""

    extra_competitions: tuple[str, ...] = ()
    """Other competitions the primary team played (cups, play-offs). Kept for
    reference only: never used by the table or the predictor."""

    @property
    def team_urls(self) -> dict[str, str]:
        """``teams`` with every URL pinned to ``epoca_id``. The scraper reads this, not ``teams``."""
        return {slug: with_epoca(url, self.epoca_id) for slug, url in self.teams.items()}

    @property
    def n_teams(self) -> int:
        return len(self.teams)

    @property
    def expected_matches(self) -> int:
        """Matches in a full double round-robin: every pair plays home and away."""
        return self.n_teams * (self.n_teams - 1)

    @property
    def dir(self) -> Path:
        return DATA_ROOT / "seasons" / self.key

    @property
    def raw_dir(self) -> Path:
        path = self.dir / "raw"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def processed_dir(self) -> Path:
        path = self.dir / "processed"
        path.mkdir(parents=True, exist_ok=True)
        return path


def define_season(
    key: str,
    competition_name: str,
    primary_team: str,
    teams: dict[str, str],
    team_name_mapping: dict[str, str] | None = None,
    epoca_id: int | None = None,
    label: str | None = None,
    register: bool = True,
) -> SeasonConfig:
    """Build (and by default register) a season from a notebook, without editing this file.

    Registered seasons live only for the Python session. Once a season is worth
    keeping, copy the printed config into ``SEASONS`` below so the next run has it.
    """
    season = SeasonConfig(
        key=key,
        label=label or key,
        competition_name=competition_name,
        primary_team=primary_team,
        teams=dict(teams),
        team_name_mapping=dict(team_name_mapping or {}),
        epoca_id=epoca_id,
    )
    if register:
        SEASONS[season.key] = season
    return season


MANSORES_2025_26 = SeasonConfig(
    key="mansores_2025_26",
    label="Mansores — AF Aveiro II Divisão Zona Norte 25/26",
    competition_name="AF Aveiro II Divisão Zona Norte 25/26",
    primary_team="mansores",
    epoca_id=155,
    teams={
        "mansores": "https://www.zerozero.pt/equipa/mansores/10972/jogos?grp=1",
        "ad_sanjoanense": "https://www.zerozero.pt/equipa/ad-sanjoanense/263339/jogos?grp=1",
        "milheiroense": "https://www.zerozero.pt/equipa/milheiroense/3607/jogos?grp=1",
        "são_martinho": "https://www.zerozero.pt/equipa/ccr-sao-martinho/16114/jogos?grp=1",
        "vila_viçosa": "https://www.zerozero.pt/equipa/ccr-vila-vicosa/216307/jogos?grp=1",
        "uniao_da_mata": "https://www.zerozero.pt/equipa/uniao-da-mata/106047/jogos?grp=1",
        "espinho_b": "https://www.zerozero.pt/equipa/sc-espinho/359178/jogos?grp=1",
        "caldas_sjorge": "https://www.zerozero.pt/equipa/caldas-s-jorge/16113/jogos?grp=1",
        "crc_vale": "https://www.zerozero.pt/equipa/crc-vale/51040/jogos?grp=1",
        "cd_tarei": "https://www.zerozero.pt/equipa/cd-tarei/363742/jogos?grp=1",
        "ef_rui_dolores": "https://www.zerozero.pt/equipa/ef-rui-dolores/364010/jogos?grp=1",
        "mosteiro_fc": "https://www.zerozero.pt/equipa/mosteiro-fc/363741/jogos?grp=1",
    },
    team_name_mapping={
        "Mansores": "mansores",
        "AD SanjoanenseB": "ad_sanjoanense",
        "CCR São Martinho": "são_martinho",
        "CCR Vila Viçosa": "vila_viçosa",
        "Milheiroense": "milheiroense",
        "União da Mata": "uniao_da_mata",
        "SC EspinhoB": "espinho_b",
        "Caldas S. Jorge": "caldas_sjorge",
        "CRC Vale": "crc_vale",
        "CD TareiS23": "cd_tarei",
        "EF Rui DoloresS23": "ef_rui_dolores",
        "Mosteirô FCS23": "mosteiro_fc",
    },
    extra_competitions=(
        "Taça Pecol - Prof. José Valente Pinho Leão 25/26",
        "Apuramento de Campeão",
    ),
)

FERMEDO_2024_25 = SeasonConfig(
    key="fermedo_2024_25",
    label="UD Fermedo — AF Aveiro 2ª Divisão Zona Norte 24/25",
    competition_name="AF Aveiro 2ª Divisão Zona Norte 24/25",
    primary_team="fermedo",
    epoca_id=154,
    teams={
        "fermedo": "https://www.zerozero.pt/equipa/ud-fermedo/37219/jogos?grp=1",
        "caldas_sjorge": "https://www.zerozero.pt/equipa/caldas-s-jorge/16113/jogos?grp=1",
        "macieira_cambra": "https://www.zerozero.pt/equipa/macieira-cambra/10975/jogos?grp=1",
        "nege": "https://www.zerozero.pt/equipa/nege/329973/jogos?grp=1",
        "sanguedo": "https://www.zerozero.pt/equipa/sanguedo/6472/jogos?grp=1",
        "valega": "https://www.zerozero.pt/equipa/ccr-valega/18244/jogos?grp=1",
        "macieirense": "https://www.zerozero.pt/equipa/macieirense/10970/jogos?grp=1",
        "são_martinho": "https://www.zerozero.pt/equipa/ccr-sao-martinho/16114/jogos?grp=1",
        "vila_viçosa": "https://www.zerozero.pt/equipa/ccr-vila-vicosa/216307/jogos?grp=1",
        "rocas_vouga": "https://www.zerozero.pt/equipa/rocas-do-vouga/327358/jogos?grp=1",
        "são_vicente_pereira": "https://www.zerozero.pt/equipa/s-vicente-pereira/312991/jogos?grp=1",
        "fajoes": "https://www.zerozero.pt/equipa/gd-fajoes/6476/jogos?grp=1",
        "milheiroense": "https://www.zerozero.pt/equipa/milheiroense/3607/jogos?grp=1",
        "flograde_b": "https://www.zerozero.pt/equipa/florgrade-fc/275834/jogos?grp=1",
        "santiais": "https://www.zerozero.pt/equipa/santiais/11520/jogos?grp=1",
        "cucujaes": "https://www.zerozero.pt/equipa/at-cucujaes/312992/jogos?grp=1",
    },
    team_name_mapping={
        "UD Fermedo": "fermedo",
        "Caldas S. Jorge": "caldas_sjorge",
        "Macieira Cambra": "macieira_cambra",
        "NEGES23": "nege",
        "Sanguedo": "sanguedo",
        "CCR Válega": "valega",
        "Macieirense": "macieirense",
        "CCR São Martinho": "são_martinho",
        "CCR Vila Viçosa": "vila_viçosa",
        "Rocas do VougaS23": "rocas_vouga",
        "S. Vicente PereiraS23": "são_vicente_pereira",
        "S. Vicente Pereira": "são_vicente_pereira",
        "Milheiroense": "milheiroense",
        "Florgrade FCB": "flograde_b",
        "Florgrade FC": "flograde_b",
        "Santiais": "santiais",
        "At. CucujãesS23": "cucujaes",
        "GD Fajões": "fajoes",
    },
)

SEASONS: dict[str, SeasonConfig] = {
    MANSORES_2025_26.key: MANSORES_2025_26,
    FERMEDO_2024_25.key: FERMEDO_2024_25,
}


def get_season(key: str) -> SeasonConfig:
    try:
        return SEASONS[key]
    except KeyError as exc:
        available = ", ".join(sorted(SEASONS))
        raise KeyError(f"Unknown season '{key}'. Available: {available}") from exc


def list_seasons() -> list[SeasonConfig]:
    return list(SEASONS.values())
