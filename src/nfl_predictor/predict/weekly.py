"""Orquestador principal: esto es lo que corre cada lunes.

Pasos:
1. Descarga el calendario/resultados más reciente (nflverse).
2. Reconstruye el historial de Elo con TODOS los partidos ya jugados
   (temporadas anteriores + lo que va de la actual), incluyendo
   regresión a la media entre temporadas.
3. Cierra el ciclo de retroalimentación: califica las predicciones de la
   semana pasada contra el resultado real (para medir qué tan certero
   viene siendo el modelo).
4. Identifica la próxima semana con partidos por jugar.
5. Genera predicciones (ganador, marcador proyectado, total proyectado)
   para esos partidos.
6. Arma una sugerencia de parlay con las N picks de mayor confianza.
7. Guarda todo en el backend de almacenamiento (SQLite o BigQuery).
8. Devuelve un resumen para el reporte semanal.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..ingest.nflverse import completed_games, fetch_games, games_for_week, upcoming_week
from ..model.elo import build_elo_history, win_probability
from ..model.scoring import latest_profile_per_team, project_score, team_scoring_profile

PARLAY_SIZE = 3


def _grade_previous_predictions(backend, all_games: pd.DataFrame) -> pd.DataFrame:
    """Compara predicciones ya guardadas contra resultados reales
    disponibles y guarda el resultado en prediction_results. Esto es lo
    que permite decir 'llevamos X% de acierto en las últimas N semanas'."""
    preds = backend.read("SELECT * FROM predictions")
    if preds.empty:
        return pd.DataFrame()

    finished = completed_games(all_games)[["game_id", "home_team", "away_team", "home_score", "away_score"]]
    merged = preds.merge(finished, on="game_id", how="inner", suffixes=("", "_actual"))
    if merged.empty:
        return pd.DataFrame()

    merged["actual_winner"] = merged.apply(
        lambda r: r["home_team"] if r["home_score"] > r["away_score"] else r["away_team"], axis=1
    )
    merged["moneyline_correct"] = merged["moneyline_pick"] == merged["actual_winner"]
    merged["actual_total_points"] = merged["home_score"] + merged["away_score"]
    merged["graded_at"] = datetime.now(timezone.utc).isoformat()

    results = merged[[
        "season", "week", "game_id", "moneyline_pick", "actual_winner", "moneyline_correct",
        "pred_total_points", "actual_total_points", "graded_at",
    ]]
    already_graded = backend.read("SELECT game_id FROM prediction_results")
    new_results = results[~results["game_id"].isin(already_graded.get("game_id", pd.Series(dtype=str)))]
    backend.append("prediction_results", new_results)
    return new_results


def run_weekly_update(backend, cache_path: str = "data/games_cache.csv",
                       as_of: pd.Timestamp | None = None) -> dict:
    as_of = as_of or pd.Timestamp.now(tz="America/Mexico_City")

    all_games = fetch_games(cache_path=cache_path, force_refresh=True)
    done = completed_games(all_games)

    graded = _grade_previous_predictions(backend, all_games)

    elo_state, elo_history = build_elo_history(done)
    scoring_profile = team_scoring_profile(done)
    latest_scoring = latest_profile_per_team(scoring_profile)

    backend.append("elo_ratings", elo_history[~elo_history["game_id"].isin(
        backend.read("SELECT DISTINCT game_id FROM elo_ratings").get("game_id", pd.Series(dtype=str))
    )])

    target = upcoming_week(all_games, as_of.tz_localize(None))
    if target is None:
        return {"status": "sin_temporada_activa", "graded": graded, "predictions": pd.DataFrame(), "parlay": pd.DataFrame()}

    season, week = target
    week_games = games_for_week(all_games, season, week)

    now_iso = datetime.now(timezone.utc).isoformat()
    pred_rows = []
    for _, g in week_games.iterrows():
        home_elo = elo_state.get(g["home_team"])
        away_elo = elo_state.get(g["away_team"])
        prob_home = win_probability(home_elo, away_elo)
        home_score, away_score = project_score(g["home_team"], g["away_team"], latest_scoring)

        pick = g["home_team"] if prob_home >= 0.5 else g["away_team"]
        confidence = prob_home if prob_home >= 0.5 else (1 - prob_home)

        pred_rows.append({
            "season": season, "week": week, "game_id": g["game_id"],
            "gameday": str(g["gameday"].date()), "home_team": g["home_team"], "away_team": g["away_team"],
            "home_elo": round(home_elo, 1), "away_elo": round(away_elo, 1),
            "pred_home_win_prob": round(prob_home, 4), "pred_away_win_prob": round(1 - prob_home, 4),
            "pred_home_score": home_score, "pred_away_score": away_score,
            "pred_total_points": round(home_score + away_score, 1),
            "moneyline_pick": pick, "moneyline_confidence": round(confidence, 4),
            "created_at": now_iso,
        })

    predictions = pd.DataFrame(pred_rows)
    backend.replace_week("predictions", season, week, predictions)

    parlay = predictions.sort_values("moneyline_confidence", ascending=False).head(PARLAY_SIZE).copy()
    parlay = parlay.sort_values("moneyline_confidence", ascending=False).reset_index(drop=True)
    parlay["rank"] = parlay.index + 1
    parlay["combined_prob_up_to_here"] = parlay["moneyline_confidence"].cumprod()
    parlay_rows = parlay[["season", "week", "rank", "game_id", "moneyline_pick", "moneyline_confidence", "combined_prob_up_to_here"]].rename(
        columns={"moneyline_pick": "pick", "moneyline_confidence": "win_prob"}
    )
    parlay_rows["created_at"] = now_iso
    backend.replace_week("parlay_suggestions", season, week, parlay_rows)

    return {
        "status": "ok", "season": season, "week": week,
        "graded": graded, "predictions": predictions, "parlay": parlay_rows,
    }
