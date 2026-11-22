begin;

alter table public.mensajes add column if not exists propuesta_informe jsonb;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'mensajes_propuesta_informe_valida' and conrelid = 'public.mensajes'::regclass) then
    alter table public.mensajes add constraint mensajes_propuesta_informe_valida check (
      propuesta_informe is null
      or (
        rol = 'asistente'
        and jsonb_typeof(propuesta_informe) = 'object'
        and jsonb_typeof(propuesta_informe -> 'contenido') = 'string'
        and length(propuesta_informe ->> 'contenido') between 1 and 20000
        and (propuesta_informe ->> 'huella_contenido') ~ '^[0-9a-f]{64}$'
        and (propuesta_informe ->> 'destino') ~ '^informe_[0-9a-f]{12}[.]md$'
      )
    );
  end if;
end
$$;

notify pgrst, 'reload schema';

commit;
