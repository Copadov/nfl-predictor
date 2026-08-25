"""
Proyección de puntos (para el pick de Over/Under) a partir de promedios
móviles de puntos anotados y recibidos por equipo, ponderando partidos
recientes más que partidos viejos (media móvil exponencial).

Nota: sin una línea de casa de apuestas real (odds API) no podemos decir
"pasa" o "no pasa" un total específico -- eso requiere una API de cuotas
(ver README, sección "Agregar odds reales"). Lo que sí podemos dar, solo
con estadísticas, es una proyección propia del total de puntos del
partido, que es la pieza que luego se compara contra la línea de la casa
quien la tenga.
"""
from __future__ import annotations

import pandas as pd

LEAGUE_AVG_POINTS = 22.0  # promedio histórico aproximado de puntos por equipo por partido
EWM_SPAN = 8  # partidos de "memoria" para el promedio móvil


def team_scoring_profile(completed_games: pd.DataFrame) -> pd.DataFrame:
    """Regresa, para cada (season, week, team), el promedio móvil de
    puntos anotados y recibidos hasta ANTES de ese partido (para no
    filtrar información del futuro al hacer backtest)."""
    games = completed_games.sort_values(["season", "week", "gameday"])

    long_rows = []
    for _, g in games.iterrows():
        long_rows.append({"season": g["season"], "week": g["week"], "gameday": g["gameday"],
                           "team": g["home_team"], "points_for": g["home_score"],
                           "points_against": g["away_score"]})
        long_rows.append({"season": g["season"], "week": g["week"], "gameday": g["gameday"],
                           "team": g["away_team"], "points_for": g["away_score"],
                           "points_against": g["home_score"]})
    long_df = pd.DataFrame(long_rows).sort_values(["team", "gameday"])

    long_df["avg_points_for"] = (
        long_df.groupby("team", group_keys=False)["points_for"]
        .apply(lambda s: s.shift(1).ewm(span=EWM_SPAN, min_periods=1).mean())
    )
    long_df["avg_points_against"] = (
        long_df.groupby("team", group_keys=False)["points_against"]
        .apply(lambda s: s.shift(1).ewm(span=EWM_SPAN, min_periods=1).mean())
    )
    long_df["avg_points_for"] = long_df["avg_points_for"].fillna(LEAGUE_AVG_POINTS)
    long_df["avg_points_against"] = long_df["avg_points_against"].fillna(LEAGUE_AVG_POINTS)
    return long_df


def latest_profile_per_team(profile: pd.DataFrame) -> pd.DataFrame:
    """Último valor conocido de avg_points_for/against por equipo (para
    proyectar la próxima semana, ya con toda la información disponible
    hasta hoy)."""
    return profile.sort_values("gameday").groupby("team").tail(1).set_index("team")


def project_score(home_team: str, away_team: str, latest: pd.DataFrame) -> tuple[float, float]:
    """Proyección simple de marcador: promedio entre 'lo que anota este
    equipo normalmente' y 'lo que concede el rival normalmente'."""
    def team_off(team: str) -> float:
        return latest.loc[team, "avg_points_for"] if team in latest.index else LEAGUE_AVG_POINTS

    def team_def(team: str) -> float:
        return latest.loc[team, "avg_points_against"] if team in latest.index else LEAGUE_AVG_POINTS

    home_proj = (team_off(home_team) + team_def(away_team)) / 2.0
    away_proj = (team_off(away_team) + team_def(home_team)) / 2.0
    return round(home_proj, 1), round(away_proj, 1)
