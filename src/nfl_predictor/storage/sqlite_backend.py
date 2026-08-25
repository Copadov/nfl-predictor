"""Backend local en SQLite. Cero configuración -- funciona en el momento,
en tu laptop o en cualquier runner de CI. Es el backend por default y
también sirve como fallback si GCP no está configurado todavía."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .schema import TABLE_DDL


class SqliteBackend:
    def __init__(self, db_path: str | Path = "data/nfl_predictor.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        cur = self.conn.cursor()
        for ddl in TABLE_DDL.values():
            cur.execute(ddl)
        self.conn.commit()

    def replace_week(self, table: str, season: int, week: int, df: pd.DataFrame) -> None:
        """Borra lo que hubiera para esa (season, week) en `table` y
        escribe la nueva versión -- así una corrida se puede re-ejecutar
        sin duplicar filas."""
        cur = self.conn.cursor()
        cur.execute(f"DELETE FROM {table} WHERE season = ? AND week = ?", (season, week))
        self.conn.commit()
        if not df.empty:
            df.to_sql(table, self.conn, if_exists="append", index=False)

    def append(self, table: str, df: pd.DataFrame) -> None:
        if not df.empty:
            df.to_sql(table, self.conn, if_exists="append", index=False)

    def read(self, query: str, params: tuple = ()) -> pd.DataFrame:
        return pd.read_sql_query(query, self.conn, params=params)

    def close(self) -> None:
        self.conn.close()
