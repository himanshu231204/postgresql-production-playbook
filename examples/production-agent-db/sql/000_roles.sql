-- 000_roles.sql  (PostgreSQL 16)
-- Run once as a superuser/admin. Cluster-wide objects; passwords are NOT set
-- here -- set them out of band (see 06-security/passwords-and-secrets.md).
--
-- agent_owner : owns the schema, runs migrations (DDL). Not used at runtime.
-- agent_rw    : group role with the runtime privileges (granted in 030_grants.sql).
-- agent_app   : login role used by the agent worker / API. CRUD only.
-- agent_ro    : login role for LLM-generated or ad-hoc READ queries. SELECT only,
--               read-only transactions, short statement timeout.

CREATE ROLE agent_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE agent_rw    NOLOGIN;
CREATE ROLE agent_app   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 50;
CREATE ROLE agent_ro    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 10;
GRANT agent_rw TO agent_app;

ALTER ROLE agent_app SET search_path = agent;
ALTER ROLE agent_app SET statement_timeout = '30s';
ALTER ROLE agent_app SET idle_in_transaction_session_timeout = '60s';

ALTER ROLE agent_ro  SET search_path = agent;
ALTER ROLE agent_ro  SET default_transaction_read_only = on;
ALTER ROLE agent_ro  SET statement_timeout = '5s';

-- Database owned by the migration role; no implicit access for everyone else.
CREATE DATABASE agentdb OWNER agent_owner ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE agentdb FROM PUBLIC;
GRANT CONNECT ON DATABASE agentdb TO agent_rw, agent_ro, agent_owner;
