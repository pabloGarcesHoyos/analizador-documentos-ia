begin;

create table if not exists public.acciones_informe (
  id uuid primary key default gen_random_uuid(),
  conversacion_id uuid not null,
  usuario_id uuid not null default auth.uid(),
  mensaje_id bigint not null,
  decision text not null check (decision in ('aprobada', 'rechazada')),
  resultado text check (resultado in ('ejecutada', 'fallida')),
  destino text not null check (length(btrim(destino)) between 1 and 300),
  huella_contenido text not null check (huella_contenido ~ '^[0-9a-f]{64}$'),
  creada_en timestamptz not null default now(),
  check (decision = 'aprobada' or resultado is null),
  unique (usuario_id, mensaje_id),
  foreign key (conversacion_id, usuario_id)
    references public.conversaciones (id, usuario_id) on delete cascade,
  foreign key (mensaje_id, conversacion_id)
    references public.mensajes (id, conversacion_id) on delete cascade
);

create index if not exists acciones_informe_conversacion_idx
  on public.acciones_informe (conversacion_id, creada_en);

alter table public.acciones_informe enable row level security;
revoke all on public.acciones_informe from public, anon, authenticated;
grant select, insert on public.acciones_informe to authenticated;
grant update (resultado) on public.acciones_informe to authenticated;

drop policy if exists acciones_informe_select_propias on public.acciones_informe;
create policy acciones_informe_select_propias on public.acciones_informe
  for select to authenticated
  using (usuario_id = (select auth.uid()));

drop policy if exists acciones_informe_insert_propias on public.acciones_informe;
create policy acciones_informe_insert_propias on public.acciones_informe
  for insert to authenticated
  with check (
    usuario_id = (select auth.uid())
    and resultado is null
    and exists (
      select 1
      from public.conversaciones as c
      where c.id = acciones_informe.conversacion_id
        and c.usuario_id = (select auth.uid())
    )
  );

drop policy if exists acciones_informe_update_resultado on public.acciones_informe;
create policy acciones_informe_update_resultado on public.acciones_informe
  for update to authenticated
  using (usuario_id = (select auth.uid()) and decision = 'aprobada' and resultado is null)
  with check (usuario_id = (select auth.uid()) and decision = 'aprobada' and resultado is not null);

notify pgrst, 'reload schema';

commit;
