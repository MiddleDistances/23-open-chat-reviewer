-- Optional, rebuildable usage projection. Raw archive identity is unchanged.
CREATE TABLE event_token_usage (
    event_id bigint PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    extraction_version integer NOT NULL,
    status text NOT NULL CHECK (status IN ('available', 'missing', 'unavailable')),
    usage_json jsonb,
    CHECK ((status = 'available') = (usage_json IS NOT NULL))
);
