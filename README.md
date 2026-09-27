# Remians Australia Cricket Auction

A projector-ready, three-team cricket auction built with Python, Streamlit, Supabase PostgreSQL and Supabase Storage. The public dashboard is read-only and refreshes from central Supabase state every 1.5 seconds. The separate admin route uses Supabase Auth, row-level security, and atomic PostgreSQL functions for sales and undo.

## What is included

- Public 65/35 auction display with the supplied Remians Australia branding
- Three persistent teams, each initialized once with **৳1,000,000 BDT**
- Protected admin console at `/?view=admin`
- Single/multiple player-card uploads, generated cards from photos, image replacement, and CSV import
- Available, sold, and unsold player states
- Atomic, row-locked, idempotent sale processing and atomic undo/refund
- Team rosters, transaction history, and CSV export
- PostgreSQL RLS and Supabase Storage policies
- Automated rule tests for sales, overspending, duplicates, and undo

The app intentionally uses only the public Supabase anon key. **Do not put a service-role key in Streamlit.** Authenticated administrator JWTs and database policies authorize every write.

## Project layout

```text
app.py                         Streamlit entry point
auction/admin.py               Protected admin workflows
auction/db.py                  Supabase access
auction/domain.py              Shared auction validation/reference model
auction/images.py              Image validation and generated cards
auction/ui.py                  Public display and theme
supabase/migrations/001_initial.sql
supabase/sample_data.sql       Optional, clearly labelled sample rows
sample_data/players.csv        Example CSV
tests/test_domain.py           Auction rule tests
```

## 1. Supabase setup

1. Create a new project at Supabase.
2. Open **SQL Editor**, paste all of `supabase/migrations/001_initial.sql`, and run it once. This creates tables, views, RPC functions, the `auction-assets` bucket, RLS, and Storage policies.
3. In **Authentication → Users**, create the administrator with an email and password. Copy that user's UUID.
4. In SQL Editor, authorize that account (replace the placeholder):

   ```sql
   insert into public.admin_users(user_id)
   values ('YOUR_AUTH_USER_UUID');
   ```

5. Get these two values from **Project Settings → API**:

   - Project URL
   - Anon/public key (the legacy `anon` key or current publishable key accepted by the Supabase client)

These are the only setup steps requiring your credentials. The admin password is entered in the protected screen and is never stored in the repository or Streamlit secrets.

### Why sale processing is safe

`confirm_sale` executes as one PostgreSQL transaction. It verifies the caller is listed in `admin_users`, locks the player and team rows, checks status and balance, deducts money, changes player state, and records the sale/history event. `request_id` has a unique constraint, so retries and repeated clicks are idempotent. A second request for the same player is rejected by both row locking and a partial unique index.

`undo_last_sale` locks the latest active sale, player, and team; refunds the exact amount; restores the player's previous `available` or `unsold` state; and records the undo in the same transaction.

## 2. Local configuration and run

Python 3.11 is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .streamlit\secrets.example.toml .streamlit\secrets.toml
```

Edit `.streamlit/secrets.toml`:

```toml
SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
SUPABASE_ANON_KEY = "YOUR_ANON_OR_PUBLISHABLE_KEY"
DEMO_MODE = false
```

Then run:

```powershell
streamlit run app.py
```

- Audience display: `http://localhost:8501/`
- Admin console: `http://localhost:8501/?view=admin`

On the first admin login, click **Create auction**. That one-time protected operation creates Team 1, Team 2, and Team 3 with exactly ৳1,000,000 each. Refreshes and app restarts do not recreate or reset budgets.

For a no-database visual preview only, set `DEMO_MODE = true`. Demo mode is deliberately read-only and must not be used for a real auction.

## 3. Add players and teams

Use the admin console:

- **Players & cards → Upload cards** accepts multiple PNG, JPG, or WebP files (maximum 10 MB and 8,000 px per side). Provide a unique player ID and name for each.
- **Create card** accepts a photo, name, role, and optional base price and generates a consistent 4:5 PNG card.
- **Edit player** changes details or replaces the displayed card.
- **CSV import** includes a downloadable template. Imports validate the whole file before database writes and update rows matching `player_id`.
- **Teams** changes names/logos and shows purchased players and prices.

Optional sample rows are in `supabase/sample_data.sql`. They are not loaded automatically.

## 4. Run an auction

1. In **Auction control**, choose a player and click **Show selected player**.
2. Conduct bidding outside the app.
3. Select the winning team, enter the whole-number final BDT price, and click **Confirm sale**.
4. The sold player, winning team, and price remain visible until another player is shown.
5. Use **Mark player unsold** to defer a player. Unsold players can be selected and sold later.
6. **Undo last sale** requires an explicit confirmation checkbox and refunds the team atomically.

The app reports success only after Supabase returns a committed RPC result. Connection errors never render a sale as successful.

## 5. Tests

```powershell
python -m pytest
```

The tests cover successful deduction/assignment, insufficient funds without partial changes, idempotent duplicate sale and undo request IDs, a second sale attempt, invalid prices, and correct undo/refund including restoration of a prior `unsold` status. The PostgreSQL migration enforces the same rules in the production transaction boundary.

## 6. Deploy through GitHub to Streamlit Community Cloud

1. Create a GitHub repository and push this project. Confirm `.streamlit/secrets.toml` is not tracked; only `secrets.example.toml` belongs in Git.
2. In Streamlit Community Cloud, choose **Create app**, select the repository/branch, and set the entry point to `app.py`.
3. Open **Advanced settings → Secrets** and paste the real values:

   ```toml
   SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
   SUPABASE_ANON_KEY = "YOUR_ANON_OR_PUBLISHABLE_KEY"
   DEMO_MODE = false
   ```

4. Deploy. Use the root app URL for the audience and append `/?view=admin` for the administrator.
5. Keep the repository private if player assets or operational details should not be public. Images themselves are publicly readable by design so the audience dashboard can display them; only authorized admins can upload/update/delete them.

## 7. Verify two-screen synchronization

1. Open the root audience URL in one browser or private/incognito window. Do not sign in there.
2. Open `/?view=admin` in a separate browser/session and sign in.
3. Show a different player. Within approximately 1–2 seconds, the audience screen should change without a manual refresh.
4. Confirm a small test sale. Verify the audience screen shows the winner and price, and the winning team's balance/player count changes once.
5. Click Confirm only once normally, then optionally test idempotency by rapidly clicking/retrying: the unique request ID cannot charge twice.
6. Undo the last sale and verify the balance, player status, and history update on both sessions.
7. Reload both browsers and restart Streamlit. Supabase-backed state should remain unchanged.

If the audience screen displays a connection warning, it retries automatically every 1.5 seconds. Check Streamlit secrets, Supabase project availability, and the migration/policies; do not re-enter a sale until the admin receives a confirmed success response.

## Security notes

- Real secrets are excluded by `.gitignore`.
- Public users receive `SELECT` only; all mutation policies require `is_admin()`.
- Security-definer RPCs set a fixed `search_path` and re-check the authenticated user.
- Storage accepts only PNG/JPEG/WebP with a 10 MB server-side limit; the app also verifies image bytes and dimensions.
- Session state holds only temporary UI/auth-client state. Auction truth, balances, current player, files, and history live in Supabase.
