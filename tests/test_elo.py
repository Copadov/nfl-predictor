import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from nfl_predictor.model.elo import EloState, build_elo_history, update_ratings, win_probability


def test_equal_ratings_home_favored_by_home_advantage():
    p = win_probability(1500, 1500)
    assert p > 0.5  # el local siempre tiene ligera ventaja por el home advantage


def test_winner_rating_goes_up():
    state = EloState()
    state.ratings["A"] = 1500
    state.ratings["B"] = 1500
    home_post, away_post = update_ratings(state, "A", "B", home_score=27, away_score=10)
    assert home_post > 1500
    assert away_post < 1500


def test_build_elo_history_no_crash_on_empty():
    state, hist = build_elo_history(pd.DataFrame(columns=[
        "game_id", "season", "week", "gameday", "home_team", "away_team", "home_score", "away_score"
    ]))
    assert hist.empty


def test_season_regression_pulls_toward_mean():
    state = EloState()
    state.ratings["A"] = 1700
    state.last_season_seen = 2024
    state.regress_for_new_season(2025)
    assert 1500 < state.ratings["A"] < 1700


if __name__ == "__main__":
    test_equal_ratings_home_favored_by_home_advantage()
    test_winner_rating_goes_up()
    test_build_elo_history_no_crash_on_empty()
    test_season_regression_pulls_toward_mean()
    print("OK: todos los tests pasaron")
