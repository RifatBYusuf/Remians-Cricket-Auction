create or replace function public.reset_auction()
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_sales_deleted integer;
  v_events_deleted integer;
begin
  if not public.is_admin() then
    raise exception 'Administrator authorization required' using errcode='42501';
  end if;

  update public.auction_state
  set current_player_id=null, updated_at=clock_timestamp()
  where singleton=true;

  select count(*)::integer into v_events_deleted from public.auction_events;
  select count(*)::integer into v_sales_deleted from public.sales;
  truncate table public.auction_events, public.sales restart identity;

  update public.players set status='available' where status is distinct from 'available';
  update public.teams set budget_remaining=budget_initial where budget_remaining is distinct from budget_initial;

  return jsonb_build_object(
    'reset', true,
    'sales_deleted', v_sales_deleted,
    'events_deleted', v_events_deleted
  );
end;
$$;

revoke all on function public.reset_auction() from public, anon;
grant execute on function public.reset_auction() to authenticated;
