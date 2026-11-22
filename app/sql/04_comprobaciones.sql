select c.relname as tabla, c.relrowsecurity as rls_activo
from pg_class as c
join pg_namespace as n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in ('analizador_fragmentos', 'lectores_corpus', 'conversaciones', 'mensajes', 'acciones_informe')
order by c.relname;

select tablename as tabla, policyname as politica, cmd as operacion, roles
from pg_policies
where schemaname = 'public'
  and tablename in ('analizador_fragmentos', 'lectores_corpus', 'conversaciones', 'mensajes', 'acciones_informe')
order by tablename, policyname;

select table_name as tabla, grantee as rol, privilege_type as privilegio
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee in ('anon', 'authenticated')
  and table_name in ('analizador_fragmentos', 'lectores_corpus', 'conversaciones', 'mensajes', 'acciones_informe')
order by table_name, grantee, privilege_type;

select p.proname as funcion, p.prosecdef as security_definer
from pg_proc as p
join pg_namespace as n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname like 'analizador_buscar%'
order by p.proname;
