-- PostgreSQL 16. Run as migration_owner (NOT the application role):
--   psql -h localhost -U migration_owner -d appdb -f sql/02_schema.sql
-- Plain SQL keeps this example self-contained; in a real project this
-- is an Alembic migration (see 09-alembic/).
CREATE TABLE app.customers (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       text NOT NULL,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT customers_email_key UNIQUE (email),
    CONSTRAINT customers_email_not_blank CHECK (length(btrim(email)) > 0)
);

CREATE TABLE app.orders (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  bigint NOT NULL
                 REFERENCES app.customers (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    status       text NOT NULL DEFAULT 'pending',
    total_cents  bigint NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT orders_status_check
        CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    CONSTRAINT orders_total_nonnegative CHECK (total_cents >= 0)
);

-- Serves: WHERE customer_id = $1 ORDER BY id (order list) and the
-- WHERE customer_id IN (...) query issued by selectinload(). Tradeoff: extra
-- write cost on every orders INSERT; PostgreSQL does not index FK columns
-- automatically, and without it each lookup scans the whole table.
CREATE INDEX orders_customer_id_id_idx ON app.orders (customer_id, id);
