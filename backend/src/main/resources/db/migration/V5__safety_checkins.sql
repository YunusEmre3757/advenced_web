-- "Guvendeyim" / "Yardim lazim" check-ins. Users broadcast their post-quake
-- status to family members. Kept as an append-only audit; latest row wins.

CREATE TABLE IF NOT EXISTS app.safety_checkins (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    status       VARCHAR(20) NOT NULL,
    event_id     VARCHAR(120),
    note         VARCHAR(500),
    latitude     DOUBLE PRECISION,
    longitude    DOUBLE PRECISION,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_safety_checkins_user_created
    ON app.safety_checkins (user_id, created_at DESC);
