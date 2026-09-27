-- OPTIONAL, clearly labelled sample players. Run only after create_auction().
insert into public.players(player_code,name,playing_role,base_price) values
  ('RA-001','Sample Batter','Top-order batter',50000),
  ('RA-002','Sample Bowler','Right-arm fast',40000),
  ('RA-003','Sample All-rounder','Batting all-rounder',60000)
on conflict(player_code) do nothing;

