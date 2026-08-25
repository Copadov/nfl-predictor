"""
Backtest walk-forward del modelo Elo + proyección de puntos.

Para cada temporada de prueba (por default 2022-2025), predice cada
semana usando SOLO información disponible antes de esa semana (nada de
fuga de datos del futuro), y compara:

  1. Precisión a ganador (moneyline) del modelo propio.
  2. Precisión de "quién es favorito según la línea de Vegas"
     (el spread_line histórico que trae nflverse) -- como referencia de
     qué tan buena es una casa de apuestas real, para saber si nuestro
     modelo es competitivo o todavía necesita ajuste.

Correr con:  python scripts/backtest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from nfl_predictor.ingest.nflverse import completed_games, fetch_games
from nfl_predictor.model.elo import build_elo_history, win_probability

TEST_SEASONS = [2022, 2023, 2024, 2025]


def main():
    all_games = fetch_games(cache_path="data/games_cache.csv")
    done = completed_games(all_games)

    rows = []
    for season in TEST_SEASONS:
        for week in sorted(done[done["season"] == season]["week"].unique()):
            # Solo partidos estrictamente anteriores a (season, week) para entrenar.
            train = done[(done["season"] < season) | ((done["season"] == season) & (done["week"] < week))]
            test = done[(done["season"] == season) & (done["week"] == week)]
            if train.empty or test.empty:
                continue

            state, _ = build_elo_history(train)
            for _, g in test.iterrows():
                home_elo = state.get(g["home_team"])
                away_elo = state.get(g["away_team"])
                prob_home = win_probability(home_elo, away_elo)
                model_pick = g["home_team"] if prob_home >= 0.5 else g["away_team"]
                actual_winner = g["home_team"] if g["home_score"] > g["away_score"] else g["away_team"]

                vegas_pick = None
                if pd.notna(g.get("home_moneyline")):
                    # home_moneyline negativo => el local es favorito (convención estándar americana)
                    vegas_pick = g["home_team"] if g["home_moneyline"] < 0 else g["away_team"]

                rows.append({
                    "season": season, "week": week, "game_id": g["game_id"],
                    "model_correct": model_pick == actual_winner,
                    "vegas_correct": (vegas_pick == actual_winner) if vegas_pick else None,
                })

    result = pd.DataFrame(rows)
    print(f"Total partidos evaluados: {len(result)}\n")

    print("=== Precisión del modelo propio (Elo) por temporada ===")
    print((result.groupby("season")["model_correct"].mean() * 100).round(1).astype(str) + "%")

    print(f"\nPrecisión global del modelo: {result['model_correct'].mean()*100:.1f}%")

    vegas = result.dropna(subset=["vegas_correct"])
    if not vegas.empty:
        print(f"Precisión de 'favorito según línea de Vegas' (referencia): {vegas['vegas_correct'].mean()*100:.1f}%")
        print(f"(evaluado sobre {len(vegas)} partidos con línea disponible)")

    result.to_csv("data/backtest_results.csv", index=False)
    print("\nDetalle guardado en data/backtest_results.csv")


if __name__ == "__main__":
    main()
