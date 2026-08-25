"""Backend de producción en BigQuery (capa 'Always Free' de GCP: 10GB de
almacenamiento + 1TB de consultas al mes, gratis para siempre dentro de
esa cuota -- este proyecto nunca se acerca a esos límites).

Este backend solo se usa desde GitHub Actions (o cualquier entorno con
salida a internet completa hacia googleapis.com); IMPORTANTE: el sandbox
de Claude donde se generó este proyecto tiene una allowlist de red que
NO incluye bigquery.googleapis.com, así que este archivo no se pudo
probar en vivo ahí -- pero usa el cliente oficial de Google exactamente
como está documentado, así que debería funcionar sin cambios en GitHub
Actions o en tu máquina con `gcloud auth application-default login`.

Requiere la variable de entorno GOOGLE_APPLICATION_CREDENTIALS apuntando
al JSON de la service account, y las variables NFL_GCP_PROJECT /
NFL_BQ_DATASET (ver config/config.example.yaml).
"""
from __future__ import annotations

import pandas as pd

from .schema import TABLE_DDL

# Traducción mínima de tipos SQLite -> BigQuery para las mismas tablas.
BQ_SCHEMA = {
    "elo_ratings": [
        ("game_id", "STRING"), ("season", "INTEGER"), ("week", "INTEGER"),
        ("team", "STRING"), ("opponent", "STRING"), ("is_home", "BOOLEAN"),
        ("elo_pre", "FLOAT"), ("elo_post", "FLOAT"),
    ],
    "predictions": [
        ("season", "INTEGER"), ("week", "INTEGER"), ("game_id", "STRING"),
        ("gameday", "STRING"), ("home_team", "STRING"), ("away_team", "STRING"),
        ("home_elo", "FLOAT"), ("away_elo", "FLOAT"),
        ("pred_home_win_prob", "FLOAT"), ("pred_away_win_prob", "FLOAT"),
        ("pred_home_score", "FLOAT"), ("pred_away_score", "FLOAT"), ("pred_total_points", "FLOAT"),
        ("moneyline_pick", "STRING"), ("moneyline_confidence", "FLOAT"),
        ("created_at", "STRING"),
    ],
    "parlay_suggestions": [
        ("season", "INTEGER"), ("week", "INTEGER"), ("rank", "INTEGER"),
        ("game_id", "STRING"), ("pick", "STRING"), ("win_prob", "FLOAT"),
        ("combined_prob_up_to_here", "FLOAT"), ("created_at", "STRING"),
    ],
    "prediction_results": [
        ("season", "INTEGER"), ("week", "INTEGER"), ("game_id", "STRING"),
        ("moneyline_pick", "STRING"), ("actual_winner", "STRING"), ("moneyline_correct", "BOOLEAN"),
        ("pred_total_points", "FLOAT"), ("actual_total_points", "FLOAT"),
        ("graded_at", "STRING"),
    ],
}


class BigQueryBackend:
    def __init__(self, project: str, dataset: str, location: str = "US"):
        from google.cloud import bigquery  # import diferido: no requerido si usas SQLite

        self.client = bigquery.Client(project=project)
        self.project = project
        self.dataset = dataset
        self.location = location
        self._ensure_dataset_and_tables()

    def _ensure_dataset_and_tables(self) -> None:
        from google.cloud import bigquery

        ds_ref = bigquery.Dataset(f"{self.project}.{self.dataset}")
        ds_ref.location = self.location
        self.client.create_dataset(ds_ref, exists_ok=True)

        for table_name, cols in BQ_SCHEMA.items():
            table_id = f"{self.project}.{self.dataset}.{table_name}"
            schema = [bigquery.SchemaField(name, dtype) for name, dtype in cols]
            table = bigquery.Table(table_id, schema=schema)
            self.client.create_table(table, exists_ok=True)

    def replace_week(self, table: str, season: int, week: int, df: pd.DataFrame) -> None:
        from google.cloud import bigquery

        table_id = f"{self.project}.{self.dataset}.{table}"
        self.client.query(
            f"DELETE FROM `{table_id}` WHERE season = @season AND week = @week",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("season", "INT64", season),
                bigquery.ScalarQueryParameter("week", "INT64", week),
            ]),
        ).result()
        if not df.empty:
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
            self.client.load_table_from_dataframe(df, table_id, job_config=job_config).result()

    def append(self, table: str, df: pd.DataFrame) -> None:
        from google.cloud import bigquery

        if df.empty:
            return
        table_id = f"{self.project}.{self.dataset}.{table}"
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
        self.client.load_table_from_dataframe(df, table_id, job_config=job_config).result()

    def read(self, query: str, params: tuple = ()) -> pd.DataFrame:
        # Nota: BigQuery usa parámetros nombrados (@nombre), no placeholders
        # posicionales como SQLite. Para las lecturas de reporte usamos SQL
        # ya formateado (ver report/summary.py) en vez de placeholders.
        return self.client.query(query).result().to_dataframe()

    def close(self) -> None:
        self.client.close()
