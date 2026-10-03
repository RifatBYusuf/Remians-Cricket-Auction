from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import streamlit as st

from auction.db import storage_url


BRAND_BLUE = "#173B70"


def inject_css() -> None:
    st.markdown(
        """
<style>
  #MainMenu, footer, header[data-testid="stHeader"] {visibility:hidden;height:0}
  .stApp {background:radial-gradient(circle at 20% 0%,#fff 0,#f3f7fb 42%,#e9f0f7 100%)}
  .block-container {max-width:1600px;padding:1rem 2.2rem 2rem}
  .brandbar {display:flex;align-items:center;justify-content:space-between;background:#173b70;
    color:white;padding:.7rem 1.2rem;border-radius:18px;margin-bottom:1rem;box-shadow:0 8px 25px #173b7022}
  .brand-left {display:flex;align-items:center;gap:.9rem}.brand-logo {width:72px;height:60px;object-fit:contain;
    border-radius:10px;background:white;padding:3px}.brand-title{font-weight:900;font-size:clamp(1.1rem,2.4vw,2rem);letter-spacing:.02em}
  .live-pill{font-weight:800;background:#e63946;padding:.45rem .8rem;border-radius:999px;white-space:nowrap}
  .player-panel {background:white;border:1px solid #dce6f0;border-radius:24px;padding:1rem;
    box-shadow:0 14px 35px #173b7018}
  .player-image {display:block;width:100%;height:min(72.2545vh,852.84px);object-fit:contain;border-radius:16px;background:#eef3f8}
  .placeholder {height:min(72.2545vh,852.84px);display:grid;place-items:center;text-align:center;border-radius:16px;
    background:linear-gradient(135deg,#173b70,#24599e);color:white;font-weight:900;font-size:2rem;padding:2rem}
  .player-name {font-size:clamp(1.8rem,3vw,3rem);font-weight:950;color:#12233f;margin:.65rem 0 .1rem}
  .player-meta {font-size:1.2rem;color:#54708d;font-weight:650}
  .sold-banner {margin-top:.7rem;background:#edf2f7;color:#12233f;border-radius:14px;
    padding:.8rem 1rem;font-size:clamp(1rem,2vw,1.5rem);font-weight:900;text-align:center}
  .status-banner {margin-top:.7rem;background:#edf2f7;color:#173b70;border-radius:14px;padding:.7rem 1rem;
    font-size:1.1rem;font-weight:800;text-align:center;text-transform:uppercase;letter-spacing:.08em}
  .score-title {font-weight:950;color:#173b70;font-size:1.5rem;margin:.1rem 0 .6rem}
  .team-card {background:white;border-left:8px solid #159447;border-radius:18px;padding:1rem;margin-bottom:.8rem;
    box-shadow:0 9px 24px #173b7015;border-top:1px solid #e1e9f1;border-right:1px solid #e1e9f1;border-bottom:1px solid #e1e9f1}
  .team-card-1, .sold-banner-1 {background:rgba(179,229,197,.4)}
  .team-card-2, .sold-banner-2 {background:rgba(244,183,183,.4)}
  .team-card-3, .sold-banner-3 {background:rgba(246,225,145,.4)}
  .team-row{display:flex;align-items:center;gap:.8rem}.team-logo{width:66px;height:66px;object-fit:contain;border-radius:12px;background:#f0f4f8}
  .team-fallback{width:66px;height:66px;display:grid;place-items:center;border-radius:12px;background:#173b70;color:white;font-size:1.7rem;font-weight:950}
  .team-name{font-size:clamp(1.05rem,1.7vw,1.4rem);font-weight:900;color:#12233f}.team-balance{font-size:29px;font-weight:950;color:#159447;white-space:nowrap}
  .team-count{color:#657b91;font-weight:700}.updated{text-align:right;color:#6c8298;font-size:.8rem;margin-top:.5rem}
  .balance-counter{display:block;height:1.2em;line-height:1.2;overflow:hidden;font-variant-numeric:tabular-nums}
  .balance-frames{display:block;animation:balance-countdown 1.1s steps(24,end) forwards}
  .balance-frame{display:block;height:1.2em;line-height:1.2}
  @keyframes balance-countdown{from{transform:translateY(0)}to{transform:translateY(calc(-100% + 1.2em))}}
  @media (prefers-reduced-motion:reduce){.balance-frames{animation:none;transform:translateY(calc(-100% + 1.2em))}}
  [data-testid="stMetric"] {background:white;border:1px solid #dce6f0;padding:.8rem;border-radius:14px}
  div.stButton > button {border-radius:10px;font-weight:800}
  @media (max-width:900px){.block-container{padding:.5rem 1rem}.brand-logo{width:54px;height:48px}}
</style>
""",
        unsafe_allow_html=True,
    )


def _data_uri(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _team_logo(team: dict[str, Any], client: Any | None = None) -> str | None:
    white_logos = {
        "royal strikers": "Royal Strikers (white).jpeg",
        "sydney avengers": "Sydney Avengers (White).jpeg",
        "sydney chasers": "Sydney Chasers (White).jpeg",
        "sydne chasers": "Sydney Chasers (White).jpeg",
    }
    filename = white_logos.get(" ".join(str(team.get("name", "")).lower().split()))
    if filename:
        path = Path(__file__).resolve().parents[1] / "Team logo" / filename
        if path.is_file():
            return _data_uri(path)
    return storage_url(client, "auction-assets", team.get("logo_path")) if client else team.get("logo_path")


def brand_header(admin: bool = False) -> None:
    logo_path = Path(__file__).resolve().parents[1] / "logo.jpg"
    logo = _data_uri(logo_path) if logo_path.exists() else ""
    label = "ADMIN CONSOLE" if admin else "LIVE AUCTION"
    st.markdown(
        f'<div class="brandbar"><div class="brand-left"><img class="brand-logo" src="{logo}">'
        f'<div><div class="brand-title">REMIANS AUSTRALIA</div><div>CRICKET PLAYER AUCTION</div></div></div>'
        f'<div class="live-pill">{label}</div></div>',
        unsafe_allow_html=True,
    )


def money(value: int | None) -> str:
    return f"${int(value or 0):,} AUD"


def _safe(value: Any) -> str:
    import html

    return html.escape(str(value or ""))


def _balance_html(team: dict[str, Any], previous: tuple[int, int] | None) -> str:
    balance = int(team["budget_remaining"])
    count = int(team.get("player_count", 0))
    if previous is None or balance >= previous[0] or count <= previous[1]:
        return money(balance)
    frames = "".join(
        f'<span class="balance-frame">{money(round(previous[0] + (balance - previous[0]) * (1 - (1 - step / 24) ** 3)))}</span>'
        for step in range(25)
    )
    return (
        f'<span class="balance-counter" role="img" aria-label="{money(balance)}">'
        f'<span class="balance-frames" aria-hidden="true">{frames}</span></span>'
    )


def render_public(snapshot: dict[str, Any], client: Any | None = None) -> None:
    player = snapshot.get("player")
    teams = snapshot.get("teams", [])
    state = snapshot.get("state") or {}
    left, right = st.columns([76.9925, 23.0075], gap="large")
    with left:
        if state.get("ended") or not player:
            panel_text = "Auction ended" if state.get("ended") else "WAITING FOR THE NEXT PLAYER"
            ready_text = "" if state.get("ended") else '<div class="player-name" style="text-align:center">Auction Ready</div>'
            player_html = (
                '<div class="player-panel">'
                f'<div class="placeholder">{panel_text}</div>'
                f'{ready_text}'
                '</div>'
            )
        else:
            image_url = storage_url(client, "auction-assets", player.get("card_image_path")) if client else player.get("card_image_path")
            if image_url:
                card_html = f'<img class="player-image" src="{_safe(image_url)}" alt="Player card for {_safe(player["name"])}">'
            else:
                card_html = '<div class="placeholder">🏏<br>PLAYER CARD<br><span style="font-size:1rem">IMAGE COMING SOON</span></div>'
            detail = player.get("playing_role") or ""
            if player.get("base_price"):
                separator = " &nbsp;•&nbsp; " if detail else ""
                detail += f"{separator}Base {money(player['base_price'])}"
            if player.get("status") == "sold":
                winning_team_number = next(
                    (
                        number for number, team in enumerate(teams, 1)
                        if (
                            team.get("id") == player["winning_team_id"]
                            if player.get("winning_team_id")
                            else team.get("name") == player.get("winning_team_name")
                        )
                    ),
                    0,
                )
                status_html = f'<div class="sold-banner sold-banner-{winning_team_number}">SOLD TO {_safe(player.get("winning_team_name"))} &nbsp;—&nbsp; {money(player.get("final_price"))}</div>'
            else:
                status_html = f'<div class="status-banner">{_safe(player.get("status", "available"))}</div>'
            player_html = (
                '<div class="player-panel">'
                f'{card_html}'
                f'<div class="player-meta">{_safe(detail)}</div>'
                f'{status_html}'
                '</div>'
            )
        st.markdown(player_html, unsafe_allow_html=True)
    with right:
        st.markdown('<div class="score-title">TEAM BALANCES</div>', unsafe_allow_html=True)
        previous_balances = st.session_state.get("public_team_balances", {})
        current_balances = {}
        for team_number, team in enumerate(teams, 1):
            team_key = str(team.get("id") or team["name"])
            balance_html = _balance_html(team, previous_balances.get(team_key))
            current_balances[team_key] = (int(team["budget_remaining"]), int(team.get("player_count", 0)))
            logo_url = _team_logo(team, client)
            logo = f'<img class="team-logo" src="{_safe(logo_url)}">' if logo_url else f'<div class="team-fallback">{_safe(team.get("name", "T")[:1])}</div>'
            st.markdown(
                f'<div class="team-card team-card-{team_number}"><div class="team-row">{logo}<div><div class="team-name">{_safe(team["name"])}</div>'
                f'<div class="team-balance">{balance_html}</div>'
                f'<div class="team-count">{int(team.get("player_count", 0))} {"player" if int(team.get("player_count", 0)) == 1 else "players"} purchased</div></div></div></div>',
                unsafe_allow_html=True,
            )
        st.session_state["public_team_balances"] = current_balances
        if state.get("updated_at"):
            st.markdown(f'<div class="updated">Synced {state["updated_at"]}</div>', unsafe_allow_html=True)


def demo_snapshot() -> dict[str, Any]:
    return {
        "state": {"updated_at": "read-only preview"},
        "player": {
            "name": "Shakib Rahman",
            "playing_role": "All-rounder",
            "base_price": 50_000,
            "status": "sold",
            "winning_team_name": "Team 2",
            "final_price": 175_000,
        },
        "teams": [
            {"name": "Team 1", "budget_remaining": 1_000_000, "player_count": 0},
            {"name": "Team 2", "budget_remaining": 825_000, "player_count": 1},
            {"name": "Team 3", "budget_remaining": 1_000_000, "player_count": 0},
        ],
    }
