-- User profile data for location-aware notifications and family workflows.

CREATE TABLE IF NOT EXISTS app.user_locations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    label           VARCHAR(80) NOT NULL,
    city            VARCHAR(80),
    district        VARCHAR(80),
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    radius_km       DOUBLE PRECISION NOT NULL DEFAULT 25,
    primary_location BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_locations_user_id ON app.user_locations(user_id);

CREATE TABLE IF NOT EXISTS app.family_members (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    name          VARCHAR(120) NOT NULL,
    relationship  VARCHAR(80),
    phone         VARCHAR(40),
    email         VARCHAR(255),
    pushover_key  VARCHAR(80),
    notify        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_family_members_user_id ON app.family_members(user_id);

CREATE TABLE IF NOT EXISTS app.past_experiences (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    title               VARCHAR(140) NOT NULL,
    event_date          DATE,
    location            VARCHAR(160),
    magnitude           DOUBLE PRECISION,
    emotional_impact    VARCHAR(80),
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_past_experiences_user_id ON app.past_experiences(user_id);
