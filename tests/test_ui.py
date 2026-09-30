from types import SimpleNamespace

from auction import ui


def test_sale_popup_is_shown_once_and_can_be_shown_after_status_resets(monkeypatch) -> None:
    messages: list[tuple[str, str]] = []
    fake_streamlit = SimpleNamespace(
        session_state={},
        toast=lambda message, icon: messages.append((message, icon)),
    )
    monkeypatch.setattr(ui, "st", fake_streamlit)
    sold_player = {
        "id": "player-1",
        "name": "Jane Doe",
        "status": "sold",
        "winning_team_id": "team-1",
        "winning_team_name": "Strikers",
        "sold_at": "2026-09-30T00:00:00Z",
    }

    ui._announce_sale(sold_player)
    ui._announce_sale(sold_player)

    assert messages == [("Jane Doe sold to Strikers", "🎉")]

    ui._announce_sale({**sold_player, "status": "available"})
    ui._announce_sale(sold_player)

    assert messages == [
        ("Jane Doe sold to Strikers", "🎉"),
        ("Jane Doe sold to Strikers", "🎉"),
    ]
