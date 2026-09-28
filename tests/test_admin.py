from types import SimpleNamespace

from auction import admin


def test_new_player_code_is_generated_automatically(monkeypatch) -> None:
    monkeypatch.setattr(admin, "uuid4", lambda: SimpleNamespace(hex="1234567890abcdef"))

    assert admin._new_player_code() == "PLAYER-1234567890AB"


def test_player_label_uses_filename_without_extension() -> None:
    assert admin._player_label("Jane Doe.card.png", "PLAYER-1") == "Jane Doe.card"
    assert admin._player_label(".png", "PLAYER-1") == "PLAYER-1"
