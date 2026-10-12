-- Additive reviewed migration. Production execution requires owner approval.
CREATE TABLE IF NOT EXISTS shared_session_selections (
    sequence BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES shared_sessions(session_id),
    selected_at_utc TEXT NOT NULL,
    UNIQUE(session_id)
);
