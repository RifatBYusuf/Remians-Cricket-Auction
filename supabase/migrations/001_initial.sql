-- Remians Australia Cricket Auction
-- Run in Supabase SQL Editor on a new project.

create extension if not exists pgcrypto;

create type public.player_status as enum ('available', 'sold', 'unsold');
create type public.event_type as enum ('sale', 'undo', 'unsold', 'current_player');

create table public.admin_users (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

create table public.teams (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(trim(name)) between 1 and 80),
  logo_path text,
  budget_initial bigint not null check (budget_initial = 1000000),
  budget_remaining bigint not null check (budget_remaining between 0 and budget_initial),
  display_order smallint not null unique check (display_order between 1 and 3),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.players (
  id uuid primary key default gen_random_uuid(),
  player_code text not null unique check (char_length(trim(player_code)) between 1 and 50),
  name text not null check (char_length(trim(name)) between 1 and 120),
  playing_role text not null default '' check (char_length(playing_role) <= 100),
  base_price bigint check (base_price is null or base_price >= 0),
  card_image_path text,
  photo_path text,
  status public.player_status not null default 'available',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.auction_state (
  singleton boolean primary key default true check (singleton),
  current_player_id uuid references public.players(id) on delete set null,
  updated_at timestamptz not null default now()
);

create table public.sales (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null unique,
  player_id uuid not null references public.players(id),
  team_id uuid not null references public.teams(id),
  final_price bigint not null check (final_price > 0),
  previous_status public.player_status not null,
  sold_by uuid not null references auth.users(id),
  sold_at timestamptz not null default clock_timestamp(),
  voided_at timestamptz,
  voided_by uuid references auth.users(id),
  undo_request_id uuid unique,
  check ((voided_at is null) = (voided_by is null))
);

create unique index one_active_sale_per_player
  on public.sales(player_id) where voided_at is null;

create table public.auction_events (
  id bigint generated always as identity primary key,
  event_type public.event_type not null,
  player_id uuid references public.players(id) on delete set null,
  team_id uuid references public.teams(id),
  amount bigint,
  sale_id uuid references public.sales(id),
  actor_id uuid not null references auth.users(id),
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default clock_timestamp()
);

create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger teams_touch_updated_at before update on public.teams
for each row execute function public.touch_updated_at();
create trigger players_touch_updated_at before update on public.players
for each row execute function public.touch_updated_at();

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists(select 1 from public.admin_users where user_id = auth.uid());
$$;

revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to authenticated;

create or replace function public.create_auction()
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  result jsonb;
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  if exists(select 1 from public.teams) then
    raise exception 'Auction has already been created';
  end if;
  insert into public.teams(name, budget_initial, budget_remaining, display_order)
  values ('Team 1',1000000,1000000,1),('Team 2',1000000,1000000,2),('Team 3',1000000,1000000,3);
  insert into public.auction_state(singleton) values(true) on conflict do nothing;
  select jsonb_build_object('created', true, 'teams', 3, 'budget_each', 1000000) into result;
  return result;
end;
$$;

create or replace function public.set_current_player(p_player_id uuid)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  if p_player_id is not null and not exists(select 1 from public.players where id=p_player_id) then
    raise exception 'Player does not exist';
  end if;
  insert into public.auction_state(singleton,current_player_id,updated_at)
  values(true,p_player_id,clock_timestamp())
  on conflict(singleton) do update set current_player_id=excluded.current_player_id,updated_at=excluded.updated_at;
  if p_player_id is not null then
    insert into public.auction_events(event_type,player_id,actor_id)
    values('current_player',p_player_id,auth.uid());
  end if;
end;
$$;

create or replace function public.mark_player_unsold(p_player_id uuid)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  perform 1 from public.players where id=p_player_id for update;
  if not found then raise exception 'Player does not exist'; end if;
  if exists(select 1 from public.sales where player_id=p_player_id and voided_at is null) then
    raise exception 'A sold player cannot be marked unsold';
  end if;
  update public.players set status='unsold' where id=p_player_id;
  insert into public.auction_events(event_type,player_id,actor_id) values('unsold',p_player_id,auth.uid());
end;
$$;

create or replace function public.confirm_sale(
  p_player_id uuid,
  p_team_id uuid,
  p_final_price bigint,
  p_request_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_player public.players%rowtype;
  v_team public.teams%rowtype;
  v_sale public.sales%rowtype;
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  if p_request_id is null then raise exception 'Request ID is required'; end if;

  select * into v_sale from public.sales where request_id=p_request_id;
  if found then
    return jsonb_build_object('sale_id',v_sale.id,'duplicate',true,'player_id',v_sale.player_id,
      'team_id',v_sale.team_id,'final_price',v_sale.final_price);
  end if;
  if p_final_price is null or p_final_price <= 0 then raise exception 'Final price must be greater than zero'; end if;

  select * into v_player from public.players where id=p_player_id for update;
  if not found then raise exception 'Player does not exist'; end if;
  if v_player.status='sold' or exists(select 1 from public.sales where player_id=p_player_id and voided_at is null) then
    raise exception 'Player has already been sold';
  end if;

  select * into v_team from public.teams where id=p_team_id for update;
  if not found then raise exception 'Team does not exist'; end if;
  if v_team.budget_remaining < p_final_price then raise exception 'Insufficient team funds'; end if;

  update public.teams set budget_remaining=budget_remaining-p_final_price where id=p_team_id;
  update public.players set status='sold' where id=p_player_id;
  insert into public.sales(request_id,player_id,team_id,final_price,previous_status,sold_by)
  values(p_request_id,p_player_id,p_team_id,p_final_price,v_player.status,auth.uid()) returning * into v_sale;
  insert into public.auction_events(event_type,player_id,team_id,amount,sale_id,actor_id)
  values('sale',p_player_id,p_team_id,p_final_price,v_sale.id,auth.uid());

  return jsonb_build_object('sale_id',v_sale.id,'duplicate',false,'player_id',p_player_id,
    'team_id',p_team_id,'final_price',p_final_price,'balance_remaining',v_team.budget_remaining-p_final_price);
exception
  when unique_violation then
    -- Concurrent identical requests resolve idempotently after the competing transaction commits.
    select * into v_sale from public.sales where request_id=p_request_id;
    if found then
      return jsonb_build_object('sale_id',v_sale.id,'duplicate',true,'player_id',v_sale.player_id,
        'team_id',v_sale.team_id,'final_price',v_sale.final_price);
    end if;
    raise;
end;
$$;

create or replace function public.undo_last_sale(p_request_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_sale public.sales%rowtype;
  v_player public.players%rowtype;
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  if p_request_id is null then raise exception 'Request ID is required'; end if;
  -- Serialize undo operations on the singleton row, then resolve retries idempotently.
  perform 1 from public.auction_state where singleton=true for update;
  select * into v_sale from public.sales where undo_request_id=p_request_id;
  if found then
    return jsonb_build_object('sale_id',v_sale.id,'player_id',v_sale.player_id,
      'team_id',v_sale.team_id,'refunded',v_sale.final_price,'restored_status',v_sale.previous_status,'duplicate',true);
  end if;
  select * into v_sale from public.sales where voided_at is null order by sold_at desc,id desc limit 1 for update;
  if not found then raise exception 'There is no sale to undo'; end if;
  select * into v_player from public.players where id=v_sale.player_id for update;
  if v_player.status <> 'sold' then raise exception 'Player sale state is inconsistent'; end if;
  perform 1 from public.teams where id=v_sale.team_id for update;
  update public.teams set budget_remaining=budget_remaining+v_sale.final_price where id=v_sale.team_id;
  update public.players set status=v_sale.previous_status where id=v_sale.player_id;
  update public.sales set voided_at=clock_timestamp(),voided_by=auth.uid(),undo_request_id=p_request_id where id=v_sale.id;
  insert into public.auction_events(event_type,player_id,team_id,amount,sale_id,actor_id)
  values('undo',v_sale.player_id,v_sale.team_id,v_sale.final_price,v_sale.id,auth.uid());
  return jsonb_build_object('sale_id',v_sale.id,'player_id',v_sale.player_id,
    'team_id',v_sale.team_id,'refunded',v_sale.final_price,'restored_status',v_sale.previous_status,'duplicate',false);
end;
$$;

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

grant execute on function public.create_auction() to authenticated;
grant execute on function public.set_current_player(uuid) to authenticated;
grant execute on function public.mark_player_unsold(uuid) to authenticated;
grant execute on function public.confirm_sale(uuid,uuid,bigint,uuid) to authenticated;
grant execute on function public.undo_last_sale(uuid) to authenticated;
grant execute on function public.reset_auction() to authenticated;

revoke all on function public.create_auction() from public;
revoke all on function public.set_current_player(uuid) from public;
revoke all on function public.mark_player_unsold(uuid) from public;
revoke all on function public.confirm_sale(uuid,uuid,bigint,uuid) from public;
revoke all on function public.undo_last_sale(uuid) from public;
revoke all on function public.reset_auction() from public, anon;

create or replace view public.team_scoreboard with (security_invoker=true) as
select t.id,t.name,t.logo_path,t.budget_remaining,t.display_order,
       count(s.id)::integer as player_count
from public.teams t
left join public.sales s on s.team_id=t.id and s.voided_at is null
group by t.id;

create or replace view public.player_public with (security_invoker=true) as
select p.id,p.player_code,p.name,p.playing_role,p.base_price,p.card_image_path,p.photo_path,p.status,
       s.final_price,s.sold_at,t.id as winning_team_id,t.name as winning_team_name,t.logo_path as winning_team_logo_path
from public.players p
left join public.sales s on s.player_id=p.id and s.voided_at is null
left join public.teams t on t.id=s.team_id;

create or replace view public.transaction_history with (security_invoker=true) as
select s.id,s.request_id,p.player_code,p.name as player_name,t.name as team_name,
       s.final_price,s.sold_at,s.voided_at,
       case when s.voided_at is null then 'completed' else 'undone' end as state
from public.sales s join public.players p on p.id=s.player_id join public.teams t on t.id=s.team_id;

alter table public.admin_users enable row level security;
alter table public.teams enable row level security;
alter table public.players enable row level security;
alter table public.auction_state enable row level security;
alter table public.sales enable row level security;
alter table public.auction_events enable row level security;

create policy "public reads teams" on public.teams for select to anon,authenticated using(true);
create policy "public reads players" on public.players for select to anon,authenticated using(true);
create policy "public reads state" on public.auction_state for select to anon,authenticated using(true);
create policy "public reads sales" on public.sales for select to anon,authenticated using(true);

create policy "admins manage teams" on public.teams for all to authenticated
using(public.is_admin()) with check(public.is_admin());
create policy "admins manage players" on public.players for all to authenticated
using(public.is_admin()) with check(public.is_admin());
create policy "admins manage state" on public.auction_state for all to authenticated
using(public.is_admin()) with check(public.is_admin());
create policy "admins read events" on public.auction_events for select to authenticated using(public.is_admin());
create policy "admin sees own role" on public.admin_users for select to authenticated using(user_id=auth.uid());

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('auction-assets','auction-assets',true,10485760,array['image/png','image/jpeg','image/webp'])
on conflict(id) do update set public=true,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;

create policy "public reads auction images" on storage.objects for select to anon,authenticated
using(bucket_id='auction-assets');
create policy "admins upload auction images" on storage.objects for insert to authenticated
with check(bucket_id='auction-assets' and public.is_admin());
create policy "admins update auction images" on storage.objects for update to authenticated
using(bucket_id='auction-assets' and public.is_admin()) with check(bucket_id='auction-assets' and public.is_admin());
create policy "admins delete auction images" on storage.objects for delete to authenticated
using(bucket_id='auction-assets' and public.is_admin());

grant select on public.teams,public.players,public.auction_state,public.sales to anon,authenticated;
grant select on public.team_scoreboard,public.player_public to anon,authenticated;
grant select on public.transaction_history to authenticated;
grant select,insert,update,delete on public.teams,public.players,public.auction_state to authenticated;
grant select on public.auction_events,public.admin_users to authenticated;
