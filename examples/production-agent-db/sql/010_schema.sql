-- 010_schema.sql  (PostgreSQL 16, no extensions required)
-- Run connected to the target database as agent_owner.
-- gen_random_uuid() is built in since PostgreSQL 13.

CREATE SCHEMA IF NOT EXISTS agent AUTHORIZATION agent_owner;
SET search_path = agent;

-- ---------------------------------------------------------------- users
CREATE TABLE users (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_ref text        NOT NULL UNIQUE,          -- id in your identity provider
    display_name text        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- -------------------------------------------------------- conversations
CREATE TABLE conversations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    title      text,
    status     text        NOT NULL DEFAULT 'active'
               CHECK (status IN ('active', 'archived')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- Serves: "list this user's conversations, newest first".
CREATE INDEX conversations_user_recent_idx
    ON conversations (user_id, updated_at DESC);

-- ----------------------------------------------------------- agent_runs
-- One execution of an agent against a conversation. `version` is the
-- optimistic-concurrency counter: every state change must bump it.
CREATE TABLE agent_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    status          text        NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    version         integer     NOT NULL DEFAULT 0,
    attempt         integer     NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    agent_version   text        NOT NULL,              -- prompt/code release, for evals and rollbacks
    error           text,
    started_at      timestamptz,
    finished_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT agent_runs_finished_has_timestamp
        CHECK ((status IN ('succeeded', 'failed', 'cancelled')) = (finished_at IS NOT NULL))
);
CREATE INDEX agent_runs_conversation_idx ON agent_runs (conversation_id, created_at DESC);
-- Serves: "which runs are in flight?" (reaper, dashboards). Partial: small.
CREATE INDEX agent_runs_active_idx ON agent_runs (status, updated_at)
    WHERE status IN ('queued', 'running');

-- ------------------------------------------------------------- messages
-- seq gives a stable per-conversation order independent of clock skew.
CREATE TABLE messages (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id uuid        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    run_id          uuid        REFERENCES agent_runs (id) ON DELETE SET NULL,
    seq             integer     NOT NULL CHECK (seq > 0),
    role            text        NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content         text        NOT NULL,
    token_count     integer     CHECK (token_count >= 0),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, seq)   -- also serves "load conversation in order"
);
CREATE INDEX messages_run_idx ON messages (run_id) WHERE run_id IS NOT NULL;

-- ----------------------------------------------------------- tool_calls
-- UNIQUE (run_id, idempotency_key) is the idempotency guard: a retried step
-- cannot create (or execute) the same call twice.
CREATE TABLE tool_calls (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid        NOT NULL REFERENCES agent_runs (id) ON DELETE CASCADE,
    idempotency_key text        NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    tool_name       text        NOT NULL CHECK (tool_name ~ '^[a-z][a-z0-9_]{0,62}$'),
    arguments       jsonb       NOT NULL CHECK (jsonb_typeof(arguments) = 'object'),
    result          jsonb,
    status          text        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    error           text,
    attempts        integer     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    created_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    UNIQUE (run_id, idempotency_key),
    CONSTRAINT tool_calls_result_only_when_succeeded
        CHECK (result IS NULL OR status = 'succeeded'),
    CONSTRAINT tool_calls_completed_consistent
        CHECK ((status IN ('succeeded', 'failed')) = (completed_at IS NOT NULL))
);

-- --------------------------------------------------------- workflow_state
-- Resumable checkpoint: one row per run. `step` is the next step to execute;
-- `state` is small, validated working data. `version` = optimistic lock.
CREATE TABLE workflow_state (
    run_id     uuid PRIMARY KEY REFERENCES agent_runs (id) ON DELETE CASCADE,
    workflow   text        NOT NULL,
    step       text        NOT NULL,
    state      jsonb       NOT NULL DEFAULT '{}'::jsonb
               CHECK (jsonb_typeof(state) = 'object' AND pg_column_size(state) < 65536),
    version    integer     NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------- tasks
-- Durable job queue claimed with FOR UPDATE SKIP LOCKED. A claim is a
-- lease: lease_expires_at lets a reaper requeue work from dead workers.
CREATE TABLE tasks (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           uuid        REFERENCES agent_runs (id) ON DELETE CASCADE,
    queue            text        NOT NULL DEFAULT 'default',
    payload          jsonb       NOT NULL DEFAULT '{}'::jsonb
                     CHECK (jsonb_typeof(payload) = 'object'),
    status           text        NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'claimed', 'succeeded', 'failed', 'dead')),
    priority         integer     NOT NULL DEFAULT 0,
    available_at     timestamptz NOT NULL DEFAULT now(),
    claimed_by       text,
    claimed_at       timestamptz,
    lease_expires_at timestamptz,
    attempts         integer     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts     integer     NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    last_error       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tasks_claim_fields_consistent
        CHECK ((status = 'claimed') = (claimed_by IS NOT NULL AND lease_expires_at IS NOT NULL))
);
-- Serves the claim query. Partial: only pending rows are indexed, so the index
-- stays small however many finished tasks accumulate. Cost: maintained on every
-- status transition into/out of 'pending'.
CREATE INDEX tasks_claim_idx ON tasks (queue, priority DESC, available_at)
    WHERE status = 'pending';
-- Serves the reaper: expired leases.
CREATE INDEX tasks_lease_idx ON tasks (lease_expires_at) WHERE status = 'claimed';

-- ------------------------------------------------------------ audit_logs
-- Append-only. No foreign keys on purpose: audit rows must outlive the rows
-- they describe. Immutability is enforced in 030_grants.sql and 040_audit.sql.
CREATE TABLE audit_logs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_type  text        NOT NULL CHECK (actor_type IN ('user', 'agent', 'system')),
    actor_id    text        NOT NULL,
    action      text        NOT NULL,
    entity_type text        NOT NULL,
    entity_id   text        NOT NULL,
    details     jsonb       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX audit_logs_entity_idx ON audit_logs (entity_type, entity_id, occurred_at);
-- BRIN: tiny index for time-range scans; works because rows arrive in time order.
CREATE INDEX audit_logs_time_brin ON audit_logs USING brin (occurred_at);

-- ----------------------------------------------------------- model_usage
CREATE TABLE model_usage (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        uuid        NOT NULL REFERENCES agent_runs (id) ON DELETE CASCADE,
    provider      text        NOT NULL,
    model         text        NOT NULL,
    input_tokens  integer     NOT NULL CHECK (input_tokens >= 0),
    output_tokens integer     NOT NULL CHECK (output_tokens >= 0),
    cost_usd      numeric(12, 6) NOT NULL CHECK (cost_usd >= 0),  -- priced at call time
    latency_ms    integer     CHECK (latency_ms >= 0),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX model_usage_run_idx ON model_usage (run_id);
CREATE INDEX model_usage_time_model_idx ON model_usage (created_at, model);

-- -------------------------------------------------------- evaluation_runs
CREATE TABLE evaluation_runs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text        NOT NULL,
    dataset       text        NOT NULL,
    agent_version text        NOT NULL,
    status        text        NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running', 'succeeded', 'failed')),
    metrics       jsonb       NOT NULL DEFAULT '{}'::jsonb
                  CHECK (jsonb_typeof(metrics) = 'object'),
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz
);
CREATE INDEX evaluation_runs_version_idx ON evaluation_runs (agent_version, started_at DESC);
