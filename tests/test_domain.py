from uuid import uuid4

import pytest

from auction.domain import AuctionError, InMemoryAuction, PlayerState, TeamState, parse_bdt


def auction() -> InMemoryAuction:
    return InMemoryAuction(
        teams={"t1": TeamState("t1"), "t2": TeamState("t2")},
        players={"p1": PlayerState("p1"), "p2": PlayerState("p2", status="unsold")},
    )


def test_sale_deducts_budget_and_assigns_player() -> None:
    state = auction()
    sale = state.sell("p1", "t1", 125_000, uuid4())
    assert sale.price == 125_000
    assert state.teams["t1"].balance == 875_000
    assert state.players["p1"].status == "sold"
    assert state.players["p1"].team_id == "t1"


def test_overspending_is_rejected_without_partial_changes() -> None:
    state = auction()
    with pytest.raises(AuctionError, match="insufficient funds"):
        state.sell("p1", "t1", 1_000_001, uuid4())
    assert state.teams["t1"].balance == 1_000_000
    assert state.players["p1"].status == "available"
    assert state.sales == []


def test_duplicate_request_is_idempotent() -> None:
    state = auction()
    request_id = uuid4()
    first = state.sell("p1", "t1", 100_000, request_id)
    second = state.sell("p1", "t1", 100_000, request_id)
    assert second is first
    assert state.teams["t1"].balance == 900_000
    assert len(state.sales) == 1


def test_player_cannot_be_sold_twice_with_different_request() -> None:
    state = auction()
    state.sell("p1", "t1", 100_000, uuid4())
    with pytest.raises(AuctionError, match="already been sold"):
        state.sell("p1", "t2", 110_000, uuid4())
    assert state.teams["t1"].balance == 900_000
    assert state.teams["t2"].balance == 1_000_000


def test_undo_refunds_and_restores_previous_unsold_status() -> None:
    state = auction()
    state.sell("p2", "t2", 80_000, uuid4())
    undone = state.undo_last()
    assert undone.undone is True
    assert state.teams["t2"].balance == 1_000_000
    assert state.players["p2"].status == "unsold"
    assert state.players["p2"].team_id is None
    assert state.players["p2"].final_price is None


def test_duplicate_undo_request_does_not_undo_another_sale() -> None:
    state = auction()
    state.sell("p1", "t1", 100_000, uuid4())
    state.sell("p2", "t2", 80_000, uuid4())
    request_id = uuid4()
    first = state.undo_last(request_id)
    retry = state.undo_last(request_id)
    assert retry is first
    assert state.players["p1"].status == "sold"
    assert state.teams["t1"].balance == 900_000


@pytest.mark.parametrize("value", [0, -1, "2.5", "NaN", "not money"])
def test_invalid_prices_are_rejected(value: object) -> None:
    with pytest.raises(AuctionError):
        parse_bdt(value)
