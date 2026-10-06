-- 040_audit.sql -- run as agent_owner.
SET search_path = agent;

-- 1. Defense in depth: reject UPDATE/DELETE on audit_logs even for roles that
--    do have the privilege (e.g. the owner). A superuser can still disable
--    triggers; use REVOKE + restricted admin access + external log shipping.
CREATE FUNCTION audit_logs_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only (% not allowed)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE TRIGGER audit_logs_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
CREATE TRIGGER audit_logs_no_truncate
    BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable();

-- 2. Automatic audit rows for status transitions, written in the SAME
--    transaction as the change. Actor comes from a per-transaction setting the
--    app sets with set_config('agent.actor', ..., true); falls back to the DB role.
CREATE FUNCTION audit_status_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    actor text := coalesce(nullif(current_setting('agent.actor', true), ''), session_user);
BEGIN
    IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO audit_logs (actor_type, actor_id, action, entity_type, entity_id, details)
        VALUES ('agent', actor, TG_TABLE_NAME || '.status_changed', TG_TABLE_NAME, NEW.id::text,
                jsonb_build_object('from', CASE WHEN TG_OP = 'UPDATE' THEN OLD.status END,
                                   'to', NEW.status));
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER agent_runs_audit
    AFTER INSERT OR UPDATE ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION audit_status_change();
CREATE TRIGGER tool_calls_audit
    AFTER INSERT OR UPDATE ON tool_calls
    FOR EACH ROW EXECUTE FUNCTION audit_status_change();
