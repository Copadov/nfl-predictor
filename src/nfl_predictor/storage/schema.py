"""Esquema de tablas, en SQL estándar (funciona tanto en SQLite como en
BigQuery con mínimos ajustes de tipos, manejados en cada backend)."""

TABLE_DDL = {
    "elo_ratings": """
        CREATE TABLE IF NOT EXISTS elo_ratings (
            game_id TEXT, season INTEGER, week INTEGER,
            team TEXT, opponent TEXT, is_home BOOLEAN,
            elo_pre REAL, elo_post REAL
        )
    """,
    "predictions": """
        CREATE TABLE IF NOT EXISTS predictions (
            season INTEGER, week INTEGER, game_id TEXT,
            gameday TEXT, home_team TEXT, away_team TEXT,
            home_elo REAL, away_elo REAL,
            pred_home_win_prob REAL, pred_away_win_prob REAL,
            pred_home_score REAL, pred_away_score REAL, pred_total_points REAL,
            moneyline_pick TEXT, moneyline_confidence REAL,
            created_at TEXT
        )
    """,
    "parlay_suggestions": """
        CREATE TABLE IF NOT EXISTS parlay_suggestions (
            season INTEGER, week INTEGER, rank INTEGER,
            game_id TEXT, pick TEXT, win_prob REAL,
            combined_prob_up_to_here REAL, created_at TEXT
        )
    """,
    "prediction_results": """
        CREATE TABLE IF NOT EXISTS prediction_results (
            season INTEGER, week INTEGER, game_id TEXT,
            moneyline_pick TEXT, actual_winner TEXT, moneyline_correct BOOLEAN,
            pred_total_points REAL, actual_total_points REAL,
            graded_at TEXT
        )
    """,
}
