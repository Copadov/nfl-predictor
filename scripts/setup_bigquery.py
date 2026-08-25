"""Corre esto UNA vez para crear el dataset y las tablas en BigQuery.

    export GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/tu/service-account.json
    python scripts/setup_bigquery.py --project TU_PROYECTO --dataset nfl_predictor
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nfl_predictor.storage.bigquery_backend import BigQueryBackend

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--dataset", default="nfl_predictor")
    parser.add_argument("--location", default="US")
    args = parser.parse_args()

    backend = BigQueryBackend(project=args.project, dataset=args.dataset, location=args.location)
    print(f"Dataset '{args.dataset}' y tablas creadas/verificadas en el proyecto '{args.project}'.")
    backend.close()
