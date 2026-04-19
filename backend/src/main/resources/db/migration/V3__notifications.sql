-- Notification preferences and delivery audit for location-based earthquake alerts.

CREATE TABLE IF NOT EXISTS app.notification_preferences (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id               UUID NOT NULL UNIQUE REFERENCES app.users(id) ON DELETE CASCADE,
    pushover_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
    pushover_user_key     VARCHAR(80),
    min_magnitude         DOUBLE PRECISION NOT NULL DEFAULT 3.0,
    notify_family_members BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notification_preferences_user_id
    ON app.notification_preferences(user_id);

CREATE TABLE IF NOT EXISTS app.notification_deliveries (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    event_id            VARCHAR(120) NOT NULL,
    channel             VARCHAR(40) NOT NULL,
    recipient_type      VARCHAR(40) NOT NULL,
    recipient_label     VARCHAR(160),
    recipient_key_hash  VARCHAR(96) NOT NULL,
    status              VARCHAR(40) NOT NULL,
    provider_message    VARCHAR(500),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_delivery_recipient
    ON app.notification_deliveries(user_id, event_id, channel, recipient_key_hash);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_user_event
    ON app.notification_deliveries(user_id, event_id);
