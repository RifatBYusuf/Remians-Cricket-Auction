-- Non-sale events (for example, displaying or marking a player unsold) should
-- not permanently prevent an administrator from removing that player. Keep
-- the event itself for the audit trail, but clear its optional player link.
-- The sales.player_id foreign key intentionally remains restrictive so a
-- player with transaction history still cannot be deleted.
alter table public.auction_events
  drop constraint if exists auction_events_player_id_fkey;

alter table public.auction_events
  add constraint auction_events_player_id_fkey
  foreign key (player_id)
  references public.players(id)
  on delete set null;
