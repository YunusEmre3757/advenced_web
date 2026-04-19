-- Email (Resend) as a second notification channel alongside Pushover.

ALTER TABLE app.notification_preferences
    ADD COLUMN IF NOT EXISTS email_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS email_address VARCHAR(255);
