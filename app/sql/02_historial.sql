begin;

create table if not exists public.conversaciones (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  titulo text not null check (length(btrim(titulo)) between 1 and 120),
  creada_en timestamptz not null default now(),
  unique (id, usuario_id)
);

create index if not exists conversaciones_usuario_idx
  on public.conversaciones (usuario_id, creada_en desc);

create table if not exists public.mensajes (
  id bigint generated always as identity primary key,
  conversacion_id uuid not null,
  usuario_id uuid not null default auth.uid(),
  rol text not null check (rol in ('usuario', 'asistente')),
  contenido text not null check (length(btrim(contenido)) between 1 and 20000),
  estado text check (estado is null or length(estado) between 1 and 60),
  fuentes jsonb not null default '[]'::jsonb check (jsonb_typeof(fuentes) = 'array'),
  herramientas jsonb not null default '[]'::jsonb check (jsonb_typeof(herramientas) = 'array'),
  traza jsonb,
  creado_en timestamptz not null default now(),
  unique (id, conversacion_id),
  foreign key (conversacion_id, usuario_id)
    references public.conversaciones (id, usuario_id) on delete cascade
);

create index if not exists mensajes_conversacion_idx
  on public.mensajes (conversacion_id, id);

alter table public.conversaciones enable row level security;
alter table public.mensajes enable row level security;

revoke all on public.conversaciones from public, anon, authenticated;
revoke all on public.mensajes from public, anon, authenticated;
grant select, insert on public.conversaciones to authenticated;
grant select, insert on public.mensajes to authenticated;

drop policy if exists conversaciones_select_propias on public.conversaciones;
create policy conversaciones_select_propias on public.conversaciones
  for select to authenticated
  using (usuario_id = (select auth.uid()));

drop policy if exists conversaciones_insert_propias on public.conversaciones;
create policy conversaciones_insert_propias on public.conversaciones
  for insert to authenticated
  with check (usuario_id = (select auth.uid()));

drop policy if exists mensajes_select_propios on public.mensajes;
create policy mensajes_select_propios on public.mensajes
  for select to authenticated
  using (
    usuario_id = (select auth.uid())
    and exists (
      select 1
      from public.conversaciones as c
      where c.id = mensajes.conversacion_id
        and c.usuario_id = (select auth.uid())
    )
  );

drop policy if exists mensajes_insert_propios on public.mensajes;
create policy mensajes_insert_propios on public.mensajes
  for insert to authenticated
  with check (
    usuario_id = (select auth.uid())
    and exists (
      select 1
      from public.conversaciones as c
      where c.id = mensajes.conversacion_id
        and c.usuario_id = (select auth.uid())
    )
  );

notify pgrst, 'reload schema';

commit;
