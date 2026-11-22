begin;

alter table public.mensajes add column if not exists limitacion text not null default '';
alter table public.mensajes add column if not exists detalle_error text not null default '';

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'mensajes_limitacion_largo' and conrelid = 'public.mensajes'::regclass) then
    alter table public.mensajes add constraint mensajes_limitacion_largo check (length(limitacion) <= 2000);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'mensajes_detalle_error_largo' and conrelid = 'public.mensajes'::regclass) then
    alter table public.mensajes add constraint mensajes_detalle_error_largo check (length(detalle_error) <= 1000);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'mensajes_presentacion_solo_asistente' and conrelid = 'public.mensajes'::regclass) then
    alter table public.mensajes add constraint mensajes_presentacion_solo_asistente
      check (rol = 'asistente' or (limitacion = '' and detalle_error = ''));
  end if;
end
$$;

notify pgrst, 'reload schema';

commit;
