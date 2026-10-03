from types import SimpleNamespace
import csv
import io

from auction import admin


def test_new_player_code_is_generated_automatically(monkeypatch) -> None:
    monkeypatch.setattr(admin, "uuid4", lambda: SimpleNamespace(hex="1234567890abcdef"))

    assert admin._new_player_code() == "PLAYER-1234567890AB"


def test_player_label_uses_filename_without_extension() -> None:
    assert admin._player_label("Jane Doe.card.png", "PLAYER-1") == "Jane Doe.card"
    assert admin._player_label(".png", "PLAYER-1") == "PLAYER-1"


def test_teams_csv_exports_purchased_players_and_empty_teams() -> None:
    teams = [{"id": "t1", "name": "Team, One"}, {"id": "t2", "name": "Empty team"}]
    players = [
        {"name": "Jane, Doe", "winning_team_id": "t1", "status": "sold"},
        {"name": "José", "winning_team_id": "t1", "status": "sold"},
        {"name": "Unsold player", "winning_team_id": None, "status": "unsold"},
    ]
    result = admin._teams_csv(teams, players).decode("utf-8-sig")
    assert list(csv.DictReader(io.StringIO(result))) == [
        {"Team name": "Team, One", "Player": "Jane, Doe"},
        {"Team name": "Team, One", "Player": "José"},
        {"Team name": "Empty team", "Player": ""},
    ]
