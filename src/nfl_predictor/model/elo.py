"""
Motor de rating Elo para NFL, con el enfoque estándar usado por FiveThirtyEight
y la comunidad de análisis deportivo:

- Rating inicial: 1500 para todos los equipos en su primera aparición.
- Home field advantage: +55 puntos Elo al equipo local (valor histórico
  promedio de la NFL; se puede recalibrar con backtest).
- K-factor base: 20.
- Multiplicador por margen de victoria (MOV), como en el modelo de 538,
  para que ganar por mucho pese más que ganar por poco, mitigado por la
  diferencia de rating (para no sobre-castigar a equipos ya favoritos).
- Regresión a la media entre temporadas: cada nueva temporada, los ratings
  se acercan un 1/3 al promedio de liga (1500), reflejando cambios de
  roster/plantilla en el offseason.

Esto es un modelo transparente y explicable -- no es una caja negra --
que se auto-actualiza cada semana conforme llegan resultados reales.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

BASE_RATING = 1500.0
HOME_ADV = 55.0
K_FACTOR = 20.0
SEASON_REGRESSION = 1.0 / 3.0  # qué tanto se jala cada equipo hacia 1500 en offseason


@dataclass
class EloState:
    ratings: dict[str, float] = field(default_factory=dict)
    last_season_seen: int | None = None

    def get(self, team: str) -> float:
        return self.ratings.get(team, BASE_RATING)

    def regress_for_new_season(self, season: int) -> None:
        if self.last_season_seen is not None and season > self.last_season_seen:
            for team in list(self.ratings.keys()):
                self.ratings[team] = BASE_RATING + (1 - SEASON_REGRESSION) * (
                    self.ratings[team] - BASE_RATING
                )
        self.last_season_seen = season


def win_probability(home_elo: float, away_elo: float) -> float:
    """Probabilidad de que gane el equipo local, incluyendo home advantage."""
    diff = (home_elo + HOME_ADV) - away_elo
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


def _mov_multiplier(point_diff: float, elo_diff_winner: float) -> float:
    """Multiplicador de margen de victoria estilo 538, con autocorrección
    para que goleadas de equipos ya muy favoritos no infle el rating."""
    point_diff = max(abs(point_diff), 1)
    return ((point_diff + 3) ** 0.8) / (7.5 + 0.006 * elo_diff_winner)


def update_ratings(state: EloState, home_team: str, away_team: str,
                    home_score: float, away_score: float) -> tuple[float, float]:
    """Actualiza el estado Elo con el resultado real de un partido.
    Regresa (home_elo_post, away_elo_post)."""
    home_elo = state.get(home_team)
    away_elo = state.get(away_team)

    prob_home = win_probability(home_elo, away_elo)
    actual_home = 1.0 if home_score > away_score else (0.5 if home_score == away_score else 0.0)

    point_diff = home_score - away_score
    elo_diff_winner = (home_elo + HOME_ADV - away_elo) if point_diff >= 0 else (away_elo - HOME_ADV - home_elo)
    mult = _mov_multiplier(point_diff, elo_diff_winner)

    shift = K_FACTOR * mult * (actual_home - prob_home)
    state.ratings[home_team] = home_elo + shift
    state.ratings[away_team] = away_elo - shift
    return state.ratings[home_team], state.ratings[away_team]


def build_elo_history(completed_games: pd.DataFrame) -> tuple[EloState, pd.DataFrame]:
    """Recorre TODOS los partidos ya jugados (en orden cronológico) y
    reconstruye el historial de ratings Elo, aplicando regresión a la
    media al inicio de cada temporada nueva.

    Regresa el estado final (para predecir la próxima semana) y una
    tabla con el rating pre/post de cada equipo en cada partido (útil
    para guardarla en la base de datos y para graficar evolución).
    """
    state = EloState()
    rows = []
    games = completed_games.sort_values(["season", "week", "gameday"])

    for _, g in games.iterrows():
        state.regress_for_new_season(int(g["season"]))
        home_pre = state.get(g["home_team"])
        away_pre = state.get(g["away_team"])
        home_post, away_post = update_ratings(
            state, g["home_team"], g["away_team"], g["home_score"], g["away_score"]
        )
        rows.append({
            "game_id": g["game_id"], "season": g["season"], "week": g["week"],
            "team": g["home_team"], "opponent": g["away_team"], "is_home": True,
            "elo_pre": home_pre, "elo_post": home_post,
        })
        rows.append({
            "game_id": g["game_id"], "season": g["season"], "week": g["week"],
            "team": g["away_team"], "opponent": g["home_team"], "is_home": False,
            "elo_pre": away_pre, "elo_post": away_post,
        })

    return state, pd.DataFrame(rows)
