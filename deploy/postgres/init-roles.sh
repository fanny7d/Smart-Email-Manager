#!/bin/sh
set -eu

psql --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=migrator_password="$SEM_MIGRATOR_DB_PASSWORD" \
  --set=app_password="$SEM_APP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE sem_migrator LOGIN PASSWORD %L', :'migrator_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sem_migrator') \gexec
SELECT format('CREATE ROLE sem_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sem_app') \gexec

ALTER ROLE sem_migrator PASSWORD :'migrator_password';
ALTER ROLE sem_app PASSWORD :'app_password';
ALTER DATABASE smart_email_manager OWNER TO sem_migrator;
ALTER SCHEMA public OWNER TO sem_migrator;

GRANT CONNECT ON DATABASE smart_email_manager TO sem_app;
GRANT USAGE ON SCHEMA public TO sem_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sem_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sem_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sem_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO sem_app;
SQL
