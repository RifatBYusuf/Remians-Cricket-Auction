alter table public.auction_events
  drop constraint if exists auction_events_player_id_fkey;

alter table public.auction_events
  add constraint auction_events_player_id_fkey
  foreign key (player_id)
  references public.players(id)
  on delete set null;
