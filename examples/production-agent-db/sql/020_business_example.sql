-- 020_business_example.sql
-- Example business table used by the transactional-consistency demo.
-- Replace with your own domain tables; the point is that agent state and
-- business data live in the SAME database so one transaction covers both.
SET search_path = agent;

CREATE TABLE support_tickets (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    uuid        NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    subject    text        NOT NULL,
    status     text        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    resolution text,
    closed_by_tool_call uuid REFERENCES tool_calls (id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT support_tickets_closed_has_resolution
        CHECK (status = 'open' OR resolution IS NOT NULL)
);
CREATE INDEX support_tickets_user_idx ON support_tickets (user_id, created_at DESC);
