revoke all on table public.admin_users, public.teams, public.players, public.auction_state,
  public.sales, public.auction_events, public.team_scoreboard, public.player_public,
  public.transaction_history from anon, authenticated;

grant select (id,name,logo_path,budget_initial,budget_remaining,display_order,created_at,updated_at)
  on public.teams to anon, authenticated;
grant select (id,player_code,name,playing_role,base_price,card_image_path,photo_path,status,created_at,updated_at)
  on public.players to anon, authenticated;
grant select on public.auction_state to anon, authenticated;
grant select (id,player_id,team_id,final_price,sold_at,voided_at) on public.sales to anon;
grant select on public.sales to authenticated;
grant select on public.team_scoreboard, public.player_public to anon, authenticated;
grant select on public.transaction_history, public.auction_events, public.admin_users to authenticated;
grant insert, update, delete on public.teams, public.players, public.auction_state to authenticated;

revoke all on function public.touch_updated_at() from public, anon, authenticated;
revoke all on function public.is_admin() from public, anon, authenticated;
revoke all on function public.create_auction() from public, anon, authenticated;
revoke all on function public.set_current_player(uuid) from public, anon, authenticated;
revoke all on function public.mark_player_unsold(uuid) from public, anon, authenticated;
revoke all on function public.confirm_sale(uuid,uuid,bigint,uuid) from public, anon, authenticated;
revoke all on function public.undo_last_sale(uuid) from public, anon, authenticated;
grant execute on function public.is_admin() to authenticated;
grant execute on function public.create_auction() to authenticated;
grant execute on function public.set_current_player(uuid) to authenticated;
grant execute on function public.mark_player_unsold(uuid) to authenticated;
grant execute on function public.confirm_sale(uuid,uuid,bigint,uuid) to authenticated;
grant execute on function public.undo_last_sale(uuid) to authenticated;
alter function public.touch_updated_at() set search_path = pg_catalog;
alter function public.is_admin() security invoker;

drop policy if exists "admins manage teams" on public.teams;
drop policy if exists "admins manage players" on public.players;
drop policy if exists "admins manage state" on public.auction_state;
drop policy if exists "admin sees own role" on public.admin_users;
create policy "admins insert teams" on public.teams for insert to authenticated with check (public.is_admin());
create policy "admins update teams" on public.teams for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admins delete teams" on public.teams for delete to authenticated using (public.is_admin());
create policy "admins insert players" on public.players for insert to authenticated with check (public.is_admin());
create policy "admins update players" on public.players for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admins delete players" on public.players for delete to authenticated using (public.is_admin());
create policy "admins insert state" on public.auction_state for insert to authenticated with check (public.is_admin());
create policy "admins update state" on public.auction_state for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admins delete state" on public.auction_state for delete to authenticated using (public.is_admin());
create policy "admin sees own role" on public.admin_users for select to authenticated using (user_id=(select auth.uid()));

create index if not exists auction_events_actor_id_idx on public.auction_events(actor_id);
create index if not exists auction_events_player_id_idx on public.auction_events(player_id);
create index if not exists auction_events_sale_id_idx on public.auction_events(sale_id);
create index if not exists auction_events_team_id_idx on public.auction_events(team_id);
create index if not exists auction_state_current_player_id_idx on public.auction_state(current_player_id);
create index if not exists sales_sold_by_idx on public.sales(sold_by);
create index if not exists sales_team_id_idx on public.sales(team_id);
create index if not exists sales_voided_by_idx on public.sales(voided_by);

create or replace function public.confirm_sale(
  p_player_id uuid, p_team_id uuid, p_final_price bigint, p_request_id uuid
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare
  v_player public.players%rowtype;
  v_team public.teams%rowtype;
  v_sale public.sales%rowtype;
begin
  if not public.is_admin() then raise exception 'Administrator authorization required' using errcode='42501'; end if;
  if p_request_id is null then raise exception 'Request ID is required'; end if;
  if p_final_price is null or p_final_price <= 0 then raise exception 'Final price must be greater than zero'; end if;

  select * into v_sale from public.sales where request_id=p_request_id;
  if found then
    if (v_sale.player_id,v_sale.team_id,v_sale.final_price) is distinct from
       (p_player_id,p_team_id,p_final_price) then
      raise exception 'Request ID has already been used with different sale details';
    end if;
    return jsonb_build_object('sale_id',v_sale.id,'duplicate',true,'player_id',v_sale.player_id,
      'team_id',v_sale.team_id,'final_price',v_sale.final_price);
  end if;

  select * into v_player from public.players where id=p_player_id for update;
  if not found then raise exception 'Player does not exist'; end if;

  select * into v_sale from public.sales where request_id=p_request_id;
  if found then
    if (v_sale.player_id,v_sale.team_id,v_sale.final_price) is distinct from
       (p_player_id,p_team_id,p_final_price) then
      raise exception 'Request ID has already been used with different sale details';
    end if;
    return jsonb_build_object('sale_id',v_sale.id,'duplicate',true,'player_id',v_sale.player_id,
      'team_id',v_sale.team_id,'final_price',v_sale.final_price);
  end if;

  if v_player.status='sold' or exists(
    select 1 from public.sales where player_id=p_player_id and voided_at is null
  ) then raise exception 'Player has already been sold'; end if;

  select * into v_team from public.teams where id=p_team_id for update;
  if not found then raise exception 'Team does not exist'; end if;
  if v_team.budget_remaining < p_final_price then raise exception 'Insufficient team funds'; end if;

  update public.teams set budget_remaining=budget_remaining-p_final_price where id=p_team_id;
  update public.players set status='sold' where id=p_player_id;
  insert into public.sales(request_id,player_id,team_id,final_price,previous_status,sold_by)
  values(p_request_id,p_player_id,p_team_id,p_final_price,v_player.status,auth.uid())
  returning * into v_sale;
  insert into public.auction_events(event_type,player_id,team_id,amount,sale_id,actor_id)
  values('sale',p_player_id,p_team_id,p_final_price,v_sale.id,auth.uid());

  return jsonb_build_object('sale_id',v_sale.id,'duplicate',false,'player_id',p_player_id,
    'team_id',p_team_id,'final_price',p_final_price,
    'balance_remaining',v_team.budget_remaining-p_final_price);
exception when unique_violation then
  select * into v_sale from public.sales where request_id=p_request_id;
  if found then
    if (v_sale.player_id,v_sale.team_id,v_sale.final_price) is distinct from
       (p_player_id,p_team_id,p_final_price) then
      raise exception 'Request ID has already been used with different sale details';
    end if;
    return jsonb_build_object('sale_id',v_sale.id,'duplicate',true,'player_id',v_sale.player_id,
      'team_id',v_sale.team_id,'final_price',v_sale.final_price);
  end if;
  raise;
end;
$$;
revoke all on function public.confirm_sale(uuid,uuid,bigint,uuid) from public, anon;
grant execute on function public.confirm_sale(uuid,uuid,bigint,uuid) to authenticated;
