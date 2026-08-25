"""
Ingesta de datos NFL desde el proyecto open-source nflverse.

Fuente principal: https://github.com/nflverse/nfldata (mantenido por la
comunidad nflverse, el mismo dataset que usa el paquete nfl_data_py).
Incluye calendario completo, resultados y líneas históricas de casas de
apuestas (moneyline, spread, total) desde 1999 hasta la temporada actual.

No requiere API key. Es 100% gratuito.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"

# Columnas que realmente usamos (el CSV trae ~46 columnas, filtramos a lo
# necesario para el modelo y para no acarrear columnas ruidosas).
KEEP_COLS = [
    "game_id", "season", "game_type", "week", "gameday", "weekday", "gametime",
    "away_team", "home_team", "away_score", "home_score", "location",
    "away_moneyline", "home_moneyline", "spread_line", "total_line",
    "away_rest", "home_rest", "div_game", "roof", "surface",
]


def fetch_games(cache_path: str | Path | None = None, force_refresh: bool = False) -> pd.DataFrame:
    """Descarga (o lee de caché) el calendario histórico + actual de la NFL.

    Args:
        cache_path: si se da, guarda/lee un CSV local para no golpear la red
            en cada corrida de pruebas.
        force_refresh: ignora la caché y vuelve a descargar.
    """
    cache_path = Path(cache_path) if cache_path else None

    if cache_path and cache_path.exists() and not force_refresh:
        df = pd.read_csv(cache_path, low_memory=False)
    else:
        resp = requests.get(GAMES_URL, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache_path, index=False)

    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols].copy()
    df["gameday"] = pd.to_datetime(df["gameday"])
    return df


def completed_games(df: pd.DataFrame) -> pd.DataFrame:
    """Solo partidos que ya tienen marcador (para entrenar el modelo)."""
    return df[df["home_score"].notna() & df["away_score"].notna()].copy()


def upcoming_week(df: pd.DataFrame, as_of: pd.Timestamp) -> tuple[int, int] | None:
    """Determina la próxima semana (season, week) con partidos sin jugar
    a partir de la fecha `as_of`. Regresa None si no hay temporada activa
    próxima (p.ej. fuera de temporada y sin calendario publicado)."""
    future = df[(df["gameday"] >= as_of.normalize()) & df["home_score"].isna()]
    if future.empty:
        return None
    row = future.sort_values(["season", "week", "gameday"]).iloc[0]
    return int(row["season"]), int(row["week"])


def games_for_week(df: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    return df[(df["season"] == season) & (df["week"] == week)].sort_values("gameday").copy()
