"""Punto de entrada de línea de comandos.

Uso:
    python -m nfl_predictor.cli run-weekly --backend sqlite
    python -m nfl_predictor.cli run-weekly --backend bigquery --gcp-project mi-proyecto --bq-dataset nfl_predictor
"""
from __future__ import annotations

import argparse
import os
import sys

from .predict.weekly import run_weekly_update
from .report.summary import build_summary, write_summary_files
from .storage.sqlite_backend import SqliteBackend


def _get_backend(args):
    if args.backend == "sqlite":
        return SqliteBackend(args.sqlite_path)
    elif args.backend == "bigquery":
        from .storage.bigquery_backend import BigQueryBackend

        project = args.gcp_project or os.environ.get("NFL_GCP_PROJECT")
        dataset = args.bq_dataset or os.environ.get("NFL_BQ_DATASET", "nfl_predictor")
        if not project:
            print("ERROR: falta --gcp-project o la variable NFL_GCP_PROJECT", file=sys.stderr)
            sys.exit(1)
        return BigQueryBackend(project=project, dataset=dataset)
    raise ValueError(f"backend desconocido: {args.backend}")


def main() -> None:
    parser = argparse.ArgumentParser(description="NFL Predictor — actualización semanal")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run-weekly", help="Ingesta datos, actualiza Elo y genera pronósticos de la próxima semana")
    p.add_argument("--backend", choices=["sqlite", "bigquery"], default="sqlite")
    p.add_argument("--sqlite-path", default="data/nfl_predictor.db")
    p.add_argument("--gcp-project", default=None)
    p.add_argument("--bq-dataset", default=None)
    p.add_argument("--out-dir", default="docs")
    p.add_argument("--cache-path", default="data/games_cache.csv")

    args = parser.parse_args()

    if args.command == "run-weekly":
        backend = _get_backend(args)
        result = run_weekly_update(backend, cache_path=args.cache_path)
        summary = build_summary(result, backend)
        json_path, md_path = write_summary_files(summary, out_dir=args.out_dir)
        backend.close()

        print(f"Status: {result['status']}")
        if result["status"] == "ok":
            print(f"Temporada {result['season']}, semana {result['week']}: "
                  f"{len(result['predictions'])} partidos pronosticados.")
        print(f"Resumen escrito en: {json_path} / {md_path}")


if __name__ == "__main__":
    main()
