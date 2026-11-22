begin;

create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create table if not exists public.analizador_fragmentos (
  owner_id uuid not null default auth.uid() references auth.users(id),
  corpus_id text not null check (length(btrim(corpus_id)) between 1 and 100),
  chunk_id text not null,
  content text not null check (length(btrim(content)) between 1 and 10000),
  metadata jsonb not null,
  configuracion jsonb not null,
  embedding extensions.vector(384) not null,
  primary key (owner_id, corpus_id, chunk_id)
);

alter table public.analizador_fragmentos enable row level security;
revoke all on public.analizador_fragmentos from public, anon, authenticated;
grant usage on schema public, extensions to authenticated;
grant select, insert, update on public.analizador_fragmentos to authenticated;

drop policy if exists analizador_select_own on public.analizador_fragmentos;
create policy analizador_select_own on public.analizador_fragmentos
  for select to authenticated
  using ((select auth.uid()) = owner_id);

drop policy if exists analizador_insert_own on public.analizador_fragmentos;
create policy analizador_insert_own on public.analizador_fragmentos
  for insert to authenticated
  with check ((select auth.uid()) = owner_id);

drop policy if exists analizador_update_own on public.analizador_fragmentos;
create policy analizador_update_own on public.analizador_fragmentos
  for update to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);

create table if not exists public.lectores_corpus (
  propietario_id uuid not null references auth.users(id) on delete cascade,
  corpus_id text not null check (length(btrim(corpus_id)) between 1 and 100),
  lector_id uuid not null references auth.users(id) on delete cascade,
  autorizado_en timestamptz not null default now(),
  primary key (propietario_id, corpus_id, lector_id)
);

create index if not exists lectores_corpus_lector_idx
  on public.lectores_corpus (lector_id, propietario_id, corpus_id);

alter table public.lectores_corpus enable row level security;
revoke all on public.lectores_corpus from public, anon, authenticated;
grant select on public.lectores_corpus to authenticated;

drop policy if exists lectores_corpus_select_propio on public.lectores_corpus;
create policy lectores_corpus_select_propio on public.lectores_corpus
  for select to authenticated
  using ((select auth.uid()) in (lector_id, propietario_id));

drop policy if exists analizador_select_lector on public.analizador_fragmentos;
create policy analizador_select_lector on public.analizador_fragmentos
  for select to authenticated
  using (
    exists (
      select 1
      from public.lectores_corpus as l
      where l.lector_id = (select auth.uid())
        and l.propietario_id = analizador_fragmentos.owner_id
        and l.corpus_id = analizador_fragmentos.corpus_id
    )
  );

create or replace function public.analizador_buscar_fragmentos_autorizado(
  query_embedding extensions.vector(384),
  p_propietario_id uuid,
  p_corpus_id text,
  p_modelo text,
  p_revision text,
  match_count integer default 10
)
returns table (chunk_id text, content text, metadata jsonb, similitud double precision)
language sql
stable
security invoker
set search_path = ''
as $$
  select d.chunk_id, d.content, d.metadata,
         1 - (d.embedding operator(extensions.<=>) query_embedding) as similitud
  from public.analizador_fragmentos as d
  where d.owner_id = p_propietario_id
    and d.corpus_id = p_corpus_id
    and d.configuracion ->> 'modelo' = p_modelo
    and d.configuracion ->> 'revision' = p_revision
  order by d.embedding operator(extensions.<=>) query_embedding, d.chunk_id
  limit least(greatest(coalesce(match_count, 10), 1), 10);
$$;

revoke all on function public.analizador_buscar_fragmentos_autorizado(extensions.vector, uuid, text, text, text, integer) from public, anon;
grant execute on function public.analizador_buscar_fragmentos_autorizado(extensions.vector, uuid, text, text, text, integer) to authenticated;

notify pgrst, 'reload schema';

commit;
