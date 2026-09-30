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
  .player-image {display:block;width:100%;height:min(61vh,720px);object-fit:contain;border-radius:16px;background:#eef3f8}
  .placeholder {height:min(61vh,720px);display:grid;place-items:center;text-align:center;border-radius:16px;
    background:linear-gradient(135deg,#173b70,#24599e);color:white;font-weight:900;font-size:2rem;padding:2rem}
  .player-name {font-size:clamp(1.8rem,3vw,3rem);font-weight:950;color:#12233f;margin:.65rem 0 .1rem}
  .player-meta {font-size:1.2rem;color:#54708d;font-weight:650}
  .sold-banner {margin-top:.7rem;background:linear-gradient(90deg,#138a43,#1ba758);color:white;border-radius:14px;
    padding:.8rem 1rem;font-size:clamp(1rem,2vw,1.5rem);font-weight:900;text-align:center}
  div[data-testid="stToast"] {position:fixed;top:7.5rem;left:33%;right:auto;bottom:auto;
    transform:translateX(-50%);width:min(52vw,700px);min-height:120px;padding:1.25rem 1.75rem;
    display:flex;align-items:center;justify-content:center;border:3px solid #fff;border-radius:22px;
    background:linear-gradient(135deg,#087b3d,#18a85c);color:#fff;
    box-shadow:0 18px 55px #061b2f80;z-index:100000}
  div[data-testid="stToast"] [data-testid="stMarkdownContainer"] p {
    color:#fff;font-size:clamp(1.5rem,3vw,2.75rem);font-weight:950;line-height:1.15;text-align:center}
  div[data-testid="stToast"] > div:first-child {font-size:clamp(1.5rem,3vw,2.5rem)}
  .status-banner {margin-top:.7rem;background:#edf2f7;color:#173b70;border-radius:14px;padding:.7rem 1rem;
    font-size:1.1rem;font-weight:800;text-align:center;text-transform:uppercase;letter-spacing:.08em}
  .score-title {font-weight:950;color:#173b70;font-size:1.5rem;margin:.1rem 0 .6rem}
  .team-card {background:white;border-left:8px solid #159447;border-radius:18px;padding:1rem;margin-bottom:.8rem;
    box-shadow:0 9px 24px #173b7015;border-top:1px solid #e1e9f1;border-right:1px solid #e1e9f1;border-bottom:1px solid #e1e9f1}
  .team-card-1 {background:rgba(179,229,197,.4)}
  .team-card-2 {background:rgba(244,183,183,.4)}
  .team-card-3 {background:rgba(246,225,145,.4)}
  .team-row{display:flex;align-items:center;gap:.8rem}.team-logo{width:66px;height:66px;object-fit:contain;border-radius:12px;background:#f0f4f8}
  .team-fallback{width:66px;height:66px;display:grid;place-items:center;border-radius:12px;background:#173b70;color:white;font-size:1.7rem;font-weight:950}
  .team-name{font-size:clamp(1.05rem,1.7vw,1.4rem);font-weight:900;color:#12233f}.team-balance{font-size:clamp(1.35rem,2.3vw,2rem);font-weight:950;color:#159447}
  .team-count{color:#657b91;font-weight:700}.updated{text-align:right;color:#6c8298;font-size:.8rem;margin-top:.5rem}
  [data-testid="stMetric"] {background:white;border:1px solid #dce6f0;padding:.8rem;border-radius:14px}
  div.stButton > button {border-radius:10px;font-weight:800}
  @media (max-width:900px){.block-container{padding:.5rem 1rem}.brand-logo{width:54px;height:48px}
    div[data-testid="stToast"] {top:6rem;left:50%;width:min(88vw,700px)}}
</style>
""",
        unsafe_allow_html=True,
    )


def _data_uri(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


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


def _announce_sale(player: dict[str, Any] | None) -> None:
    """Show each completed sale once per display session."""
    session_key = "public_sale_announcement"
    if not player or player.get("status") != "sold":
        st.session_state.pop(session_key, None)
        return

    sale_key = (
        player.get("id") or player.get("name"),
        player.get("winning_team_id") or player.get("winning_team_name"),
        player.get("sold_at") or player.get("final_price"),
    )
    if st.session_state.get(session_key) == sale_key:
        return

    player_name = str(player.get("name") or "Player")
    team_name = str(player.get("winning_team_name") or "team")
    st.toast(f"{player_name} sold to {team_name}", icon="🎉")
    st.session_state[session_key] = sale_key


def render_public(snapshot: dict[str, Any], client: Any | None = None) -> None:
    player = snapshot.get("player")
    teams = snapshot.get("teams", [])
    state = snapshot.get("state") or {}
    _announce_sale(player)
    left, right = st.columns([65, 35], gap="large")
    with left:
        if not player:
            player_html = (
                '<div class="player-panel">'
                '<div class="placeholder">🏏<br>WAITING FOR THE NEXT PLAYER</div>'
                '<div class="player-name">Auction ready</div>'
                '<div class="player-meta">The selected player will appear here.</div>'
                '</div>'
            )
        else:
            image_url = storage_url(client, "auction-assets", player.get("card_image_path")) if client else player.get("card_image_path")
            if image_url:
                card_html = f'<img class="player-image" src="{_safe(image_url)}" alt="Player card for {_safe(player["name"])}">'
            else:
                card_html = '<div class="placeholder">🏏<br>PLAYER CARD<br><span style="font-size:1rem">IMAGE COMING SOON</span></div>'
            detail = player.get("playing_role") or "Cricket player"
            if player.get("base_price"):
                detail += f" &nbsp;•&nbsp; Base {money(player['base_price'])}"
            if player.get("status") == "sold":
                status_html = f'<div class="sold-banner">SOLD TO {_safe(player.get("winning_team_name"))} &nbsp;—&nbsp; {money(player.get("final_price"))}</div>'
            else:
                status_html = f'<div class="status-banner">{_safe(player.get("status", "available"))}</div>'
            player_html = (
                '<div class="player-panel">'
                f'{card_html}'
                f'<div class="player-name">{_safe(player["name"])}</div>'
                f'<div class="player-meta">{_safe(detail)}</div>'
                f'{status_html}'
                '</div>'
            )
        st.markdown(player_html, unsafe_allow_html=True)
    with right:
        st.markdown('<div class="score-title">TEAM BALANCES</div>', unsafe_allow_html=True)
        for team_number, team in enumerate(teams, 1):
            logo_url = storage_url(client, "auction-assets", team.get("logo_path")) if client else team.get("logo_path")
            logo = f'<img class="team-logo" src="{_safe(logo_url)}">' if logo_url else f'<div class="team-fallback">{_safe(team.get("name", "T")[:1])}</div>'
            st.markdown(
                f'<div class="team-card team-card-{team_number}"><div class="team-row">{logo}<div><div class="team-name">{_safe(team["name"])}</div>'
                f'<div class="team-balance">{money(team["budget_remaining"])}</div>'
                f'<div class="team-count">{int(team.get("player_count", 0))} player(s) purchased</div></div></div></div>',
                unsafe_allow_html=True,
            )
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
