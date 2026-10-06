-- PostgreSQL 16. Run with psql as an administrator, connected to any database:
--   psql -h localhost -U dba_admin -d postgres -f sql/01_admin_setup.sql
-- Mirrors 06-security/least-privilege.md. Passwords are NOT set here:
--   \password app_api   /   \password migration_owner
CREATE ROLE migration_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE app_rw NOLOGIN;
CREATE ROLE app_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    CONNECTION LIMIT 50;
GRANT app_rw TO app_api;

CREATE DATABASE appdb OWNER migration_owner;
REVOKE ALL ON DATABASE appdb FROM PUBLIC;
GRANT CONNECT ON DATABASE appdb TO app_rw, migration_owner;

\connect appdb

CREATE SCHEMA app AUTHORIZATION migration_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO app_rw;

ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner IN SCHEMA app
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner IN SCHEMA app
    GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
