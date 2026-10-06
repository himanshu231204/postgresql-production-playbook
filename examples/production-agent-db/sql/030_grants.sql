-- 030_grants.sql  -- run as agent_owner (or superuser) after 010/020.
SET search_path = agent;

REVOKE ALL ON SCHEMA agent FROM PUBLIC;
GRANT USAGE ON SCHEMA agent TO agent_rw, agent_ro;

-- Runtime role: CRUD on mutable tables. No DELETE on users (use ON DELETE RESTRICT
-- + a privacy erasure procedure run by an admin role instead).
GRANT SELECT, INSERT, UPDATE ON users, conversations TO agent_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON agent_runs, messages, tool_calls, workflow_state,
      tasks, support_tickets, evaluation_runs TO agent_rw;
GRANT SELECT, INSERT ON model_usage TO agent_rw;      -- usage is a ledger: no edits

-- Audit log is append-only for the runtime role: INSERT + SELECT only.
-- (Identity column uses an implicit sequence: grant USAGE on it.)
GRANT SELECT, INSERT ON audit_logs TO agent_rw;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM agent_rw;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA agent TO agent_rw;

-- Read-only role: only what an LLM-facing "query" tool may see. NOT audit_logs,
-- NOT tool_calls.arguments (may hold PII), NOT users.
GRANT SELECT ON support_tickets, model_usage TO agent_ro;
GRANT SELECT (id, conversation_id, status, created_at) ON agent_runs TO agent_ro;
