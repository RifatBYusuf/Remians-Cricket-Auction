-- Persist the audience end screen without changing players, sales, or budgets.
alter table public.auction_state add column ended boolean not null default false;

-- Showing a player (or clearing the display) resumes the auction.
create or replace function public.set_current_player(p_player_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  if p_player_id is not null and not exists(select 1 from public.players where id=p_player_id) then
    raise exception 'Player does not exist';
  end if;
  insert into public.auction_state(singleton,current_player_id,ended,updated_at)
  values(true,p_player_id,false,clock_timestamp())
  on conflict(singleton) do update set current_player_id=excluded.current_player_id,ended=false,updated_at=excluded.updated_at;
  if p_player_id is not null then
    insert into public.auction_events(event_type,player_id,actor_id)
    values('current_player',p_player_id,auth.uid());
  end if;
end;
$$;
revoke all on function public.set_current_player(uuid) from public, anon;
grant execute on function public.set_current_player(uuid) to authenticated;

-- Reset also restores the waiting screen.
create or replace function public.reset_auction()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_sales_deleted integer;
  v_events_deleted integer;
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  update public.auction_state set current_player_id=null,ended=false,updated_at=clock_timestamp() where singleton=true;
  select count(*)::integer into v_events_deleted from public.auction_events;
  select count(*)::integer into v_sales_deleted from public.sales;
  truncate table public.auction_events, public.sales, public.team_budget_topups restart identity;
  update public.players set status='available' where status is distinct from 'available';
  update public.teams set budget_remaining=budget_initial where budget_remaining is distinct from budget_initial;
  return jsonb_build_object('reset',true,'sales_deleted',v_sales_deleted,'events_deleted',v_events_deleted);
end;
$$;
revoke all on function public.reset_auction() from public, anon;
grant execute on function public.reset_auction() to authenticated;
