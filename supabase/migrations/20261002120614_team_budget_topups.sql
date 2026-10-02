-- Allow funds above the original budget without changing reset behavior.
alter table public.teams drop constraint if exists teams_check;
alter table public.teams drop constraint if exists teams_budget_remaining_check;
alter table public.teams add constraint teams_budget_remaining_check check (budget_remaining >= 0);

create table public.team_budget_topups (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null unique,
  team_id uuid not null references public.teams(id),
  amount bigint not null default 500000 check (amount = 500000),
  added_by uuid not null references auth.users(id),
  added_at timestamptz not null default clock_timestamp(),
  retracted_at timestamptz,
  retracted_by uuid references auth.users(id),
  check ((retracted_at is null) = (retracted_by is null))
);
create index team_budget_topups_team_id_idx on public.team_budget_topups(team_id);
create index team_budget_topups_added_by_idx on public.team_budget_topups(added_by);
create index team_budget_topups_retracted_by_idx on public.team_budget_topups(retracted_by);
alter table public.team_budget_topups enable row level security;
create policy "admins read budget topups" on public.team_budget_topups
  for select to authenticated using ((select public.is_admin()));
revoke all on public.team_budget_topups from anon, authenticated;
grant select on public.team_budget_topups to authenticated;

create function public.add_team_budget(p_team_id uuid, p_request_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_topup public.team_budget_topups%rowtype;
  v_balance bigint;
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  if p_request_id is null then raise exception 'Request ID is required'; end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_request_id::text, 0));
  select * into v_topup from public.team_budget_topups where request_id=p_request_id;
  if found then
    if v_topup.team_id is distinct from p_team_id then raise exception 'Request ID has already been used for another team'; end if;
    return jsonb_build_object('topup_id',v_topup.id,'duplicate',true,'amount',v_topup.amount);
  end if;
  select budget_remaining into v_balance from public.teams where id=p_team_id for update;
  if not found then raise exception 'Team does not exist'; end if;
  update public.teams set budget_remaining=budget_remaining+500000 where id=p_team_id;
  insert into public.team_budget_topups(request_id,team_id,added_by)
  values(p_request_id,p_team_id,auth.uid()) returning * into v_topup;
  return jsonb_build_object('topup_id',v_topup.id,'duplicate',false,'amount',500000,'balance_remaining',v_balance+500000);
end;
$$;

create function public.retract_team_budget(p_topup_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_topup public.team_budget_topups%rowtype;
  v_balance bigint;
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  select * into v_topup from public.team_budget_topups where id=p_topup_id for update;
  if not found then raise exception 'Budget top-up does not exist'; end if;
  if v_topup.retracted_at is not null then
    return jsonb_build_object('topup_id',v_topup.id,'duplicate',true,'amount',v_topup.amount);
  end if;
  select budget_remaining into v_balance from public.teams where id=v_topup.team_id for update;
  if v_balance < v_topup.amount then
    raise exception 'Cannot retract top-up: team has less than $500,000 AUD remaining. Undo a sale or add funds first';
  end if;
  update public.teams set budget_remaining=budget_remaining-v_topup.amount where id=v_topup.team_id;
  update public.team_budget_topups set retracted_at=clock_timestamp(),retracted_by=auth.uid() where id=v_topup.id;
  return jsonb_build_object('topup_id',v_topup.id,'duplicate',false,'amount',v_topup.amount,'balance_remaining',v_balance-v_topup.amount);
end;
$$;
revoke all on function public.add_team_budget(uuid,uuid) from public, anon;
revoke all on function public.retract_team_budget(uuid) from public, anon;
grant execute on function public.add_team_budget(uuid,uuid) to authenticated;
grant execute on function public.retract_team_budget(uuid) to authenticated;

create or replace function public.reset_auction()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_sales_deleted integer;
  v_events_deleted integer;
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  update public.auction_state set current_player_id=null,updated_at=clock_timestamp() where singleton=true;
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
