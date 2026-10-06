-- 050_state_machine.sql -- run as agent_owner.
-- CHECK constraints list the VALID STATUSES. They cannot see the old row, so
-- they cannot enforce legal TRANSITIONS. A trigger does that.
SET search_path = agent;

CREATE FUNCTION enforce_run_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = OLD.status THEN
        RETURN NEW;
    END IF;
    IF NOT (
        (OLD.status = 'queued'  AND NEW.status IN ('running', 'cancelled')) OR
        (OLD.status = 'running' AND NEW.status IN ('succeeded', 'failed', 'cancelled', 'queued'))
    ) THEN
        RAISE EXCEPTION 'illegal agent_runs transition % -> %', OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER agent_runs_transition
    BEFORE UPDATE OF status ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION enforce_run_transition();
