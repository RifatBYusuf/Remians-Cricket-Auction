from __future__ import annotations

from typing import Any

from auction.config import Settings


class DatabaseError(RuntimeError):
    pass


def make_client(settings: Settings) -> Any:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise DatabaseError(
            "Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY "
            "to Streamlit secrets, or enable DEMO_MODE for a read-only preview."
        )
    try:
        from supabase import create_client
    except ImportError as exc:
        raise DatabaseError("The Supabase client is not installed. Run pip install -r requirements.txt.") from exc
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def public_snapshot(client: Any) -> dict[str, Any]:
    """Fetch uncached public state; every refresh goes to Supabase."""
    try:
        state_rows = client.table("auction_state").select("*").eq("singleton", True).execute().data
        teams = (
            client.table("team_scoreboard")
            .select("id,name,logo_path,budget_remaining,player_count")
            .order("display_order")
            .execute()
            .data
        )
        state = state_rows[0] if state_rows else None
        player = None
        if state and state.get("current_player_id"):
            rows = (
                client.table("player_public")
                .select("*")
                .eq("id", state["current_player_id"])
                .execute()
                .data
            )
            player = rows[0] if rows else None
        return {"state": state, "teams": teams, "player": player}
    except Exception as exc:
        raise DatabaseError(f"Could not load auction data: {exc}") from exc


def storage_url(client: Any, bucket: str, path: str | None) -> str | None:
    if not path:
        return None
    return client.storage.from_(bucket).get_public_url(path)


def require_admin_session(client: Any, email: str, password: str) -> dict[str, Any]:
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        if not response.user:
            raise DatabaseError("Login failed.")
        check = client.rpc("is_admin").execute().data
        if not check:
            client.auth.sign_out()
            raise DatabaseError("This account is not authorized as an auction administrator.")
        return {"user_id": response.user.id, "email": response.user.email}
    except DatabaseError:
        raise
    except Exception as exc:
        raise DatabaseError("Invalid credentials or Supabase is unavailable.") from exc


def upload_asset(client: Any, bucket: str, path: str, content: bytes, content_type: str) -> str:
    try:
        client.storage.from_(bucket).upload(
            path,
            content,
            {"content-type": content_type, "upsert": "true"},
        )
        return path
    except Exception as exc:
        raise DatabaseError(f"Image upload failed: {exc}") from exc
