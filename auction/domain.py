"""Pure auction rules used for fast validation and unit tests.

PostgreSQL repeats and ultimately enforces these rules inside locked transactions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from uuid import UUID


class AuctionError(ValueError):
    """A user-correctable auction rule violation."""


def parse_bdt(value: object) -> int:
    """Return a positive, whole-number BDT amount."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AuctionError("Price must be a valid number.") from exc
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise AuctionError("Price must be a whole number of BDT.")
    if amount <= 0:
        raise AuctionError("Price must be greater than zero.")
    if amount > Decimal("999999999999"):
        raise AuctionError("Price is too large.")
    return int(amount)


def validate_sale(status: str, price: object, team_balance: int) -> int:
    amount = parse_bdt(price)
    if status == "sold":
        raise AuctionError("This player has already been sold.")
    if amount > team_balance:
        raise AuctionError("The selected team has insufficient funds.")
    return amount


@dataclass
class PlayerState:
    player_id: str
    status: str = "available"
    team_id: str | None = None
    final_price: int | None = None


@dataclass
class TeamState:
    team_id: str
    balance: int = 1_000_000


@dataclass
class SaleState:
    request_id: UUID
    player_id: str
    team_id: str
    price: int
    undone: bool = False
    undo_request_id: UUID | None = None
    previous_status: str = "available"


@dataclass
class InMemoryAuction:
    """Small reference model mirroring the database transaction contract."""

    teams: dict[str, TeamState]
    players: dict[str, PlayerState]
    sales: list[SaleState] = field(default_factory=list)

    def sell(self, player_id: str, team_id: str, price: object, request_id: UUID) -> SaleState:
        existing = next((s for s in self.sales if s.request_id == request_id), None)
        if existing:
            return existing
        player = self.players[player_id]
        team = self.teams[team_id]
        amount = validate_sale(player.status, price, team.balance)
        sale = SaleState(request_id, player_id, team_id, amount, previous_status=player.status)
        team.balance -= amount
        player.status, player.team_id, player.final_price = "sold", team_id, amount
        self.sales.append(sale)
        return sale

    def undo_last(self, request_id: UUID | None = None) -> SaleState:
        if request_id is not None:
            existing = next((s for s in self.sales if s.undo_request_id == request_id), None)
            if existing:
                return existing
        sale = next((s for s in reversed(self.sales) if not s.undone), None)
        if sale is None:
            raise AuctionError("There is no sale to undo.")
        player = self.players[sale.player_id]
        team = self.teams[sale.team_id]
        if player.status != "sold" or player.team_id != sale.team_id:
            raise AuctionError("The latest sale no longer matches the player record.")
        team.balance += sale.price
        player.status = sale.previous_status
        player.team_id = None
        player.final_price = None
        sale.undone = True
        sale.undo_request_id = request_id
        return sale
