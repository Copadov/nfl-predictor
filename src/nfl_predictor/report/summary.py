"""Genera el resumen semanal en JSON y Markdown, incluyendo el histórico
de aciertos (para que se note si el modelo va mejorando semana a semana).

El JSON es lo que se publica en GitHub Pages / se sube al repo, y es lo
que la sesión programada de los lunes de Claude lee para armar el
mensaje de chat y el reporte -- así Claude nunca necesita hablar
directamente con BigQuery (esa parte corre solo en GitHub Actions)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def accuracy_stats(backend) -> dict:
    results = backend.read("SELECT * FROM prediction_results")
    if results.empty:
        return {"total_gradado": 0, "aciertos_moneyline": None, "pct_acierto_moneyline": None}

    total = len(results)
    correct = int(results["moneyline_correct"].sum())
    mae_total_points = float((results["pred_total_points"] - results["actual_total_points"]).abs().mean())

    by_week = (
        results.sort_values(["season", "week"])
        .groupby(["season", "week"])["moneyline_correct"]
        .agg(["sum", "count"]).reset_index()
    )
    by_week["pct"] = (by_week["sum"] / by_week["count"] * 100).round(1)

    return {
        "total_gradado": total,
        "aciertos_moneyline": correct,
        "pct_acierto_moneyline": round(correct / total * 100, 1),
        "mae_total_puntos": round(mae_total_points, 1),
        "por_semana": by_week.tail(8).to_dict(orient="records"),
    }


def build_summary(result: dict, backend) -> dict:
    stats = accuracy_stats(backend)
    preds = result.get("predictions", pd.DataFrame())
    parlay = result.get("parlay", pd.DataFrame())

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": result.get("status"),
        "season": result.get("season"),
        "week": result.get("week"),
        "accuracy_historica": stats,
        "predicciones": preds.to_dict(orient="records") if not preds.empty else [],
        "parlay_sugerido": parlay.to_dict(orient="records") if not parlay.empty else [],
    }
    return summary


def write_summary_files(summary: dict, out_dir: str = "docs") -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "latest.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    if summary.get("season") and summary.get("week"):
        hist_path = out_dir / f"{summary['season']}-week{summary['week']:02d}.json"
        hist_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_path = out_dir / "latest.md"
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    return json_path, md_path


def render_markdown(summary: dict) -> str:
    lines = []
    if summary["status"] != "ok":
        lines.append("# NFL Predictor\n\nNo hay temporada activa con partidos próximos en este momento.\n")
        return "\n".join(lines)

    lines.append(f"# Pronósticos NFL — Temporada {summary['season']}, Semana {summary['week']}\n")

    acc = summary["accuracy_historica"]
    if acc["total_gradado"]:
        lines.append(
            f"**Historial del modelo:** {acc['aciertos_moneyline']}/{acc['total_gradado']} "
            f"aciertos a ganador ({acc['pct_acierto_moneyline']}%), error promedio en total de "
            f"puntos: {acc['mae_total_puntos']} pts.\n"
        )
    else:
        lines.append("**Historial del modelo:** aún no hay semanas calificadas.\n")

    lines.append("## Pronósticos de la semana\n")
    lines.append("| Partido | Pick | Prob. victoria | Marcador proyectado | Total proyectado |")
    lines.append("|---|---|---|---|---|")
    for p in summary["predicciones"]:
        matchup = f"{p['away_team']} @ {p['home_team']}"
        marcador = f"{p['away_team']} {p['pred_away_score']} - {p['pred_home_score']} {p['home_team']}"
        lines.append(
            f"| {matchup} | **{p['moneyline_pick']}** | {p['moneyline_confidence']*100:.1f}% | "
            f"{marcador} | {p['pred_total_points']} |"
        )

    if summary["parlay_sugerido"]:
        lines.append("\n## Parlay sugerido (mayor confianza)\n")
        for leg in summary["parlay_sugerido"]:
            lines.append(f"{leg['rank']}. **{leg['pick']}** gana — {leg['win_prob']*100:.1f}% de probabilidad")
        combined = summary["parlay_sugerido"][-1]["combined_prob_up_to_here"]
        lines.append(f"\nProbabilidad combinada estimada: **{combined*100:.1f}%**")
        lines.append(
            "\n_Nota: esta probabilidad es del modelo propio (basado en Elo + estadísticas), "
            "no viene de una casa de apuestas real. Sin una API de cuotas conectada todavía no "
            "podemos calcular el pago real del parlay ni comparar valor contra el mercado._"
        )

    lines.append(
        "\n---\n_Este pronóstico es analítico/informativo, no garantiza resultados. "
        "Aposta con responsabilidad y solo dinero que puedas permitirte perder._"
    )
    return "\n".join(lines)
