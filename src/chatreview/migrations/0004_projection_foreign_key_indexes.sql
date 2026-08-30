CREATE INDEX events_canonical_event_idx
ON events(canonical_event_id)
WHERE canonical_event_id IS NOT NULL;

CREATE INDEX episodes_first_event_idx ON episodes(first_event_id);
CREATE INDEX episodes_last_event_idx ON episodes(last_event_id);
CREATE INDEX semantic_windows_first_event_idx ON semantic_windows(first_event_id);
CREATE INDEX semantic_windows_last_event_idx ON semantic_windows(last_event_id);
CREATE INDEX work_interval_evidence_event_idx ON work_interval_evidence(event_id);

INSERT INTO schema_meta(key, value) VALUES ('schema_version', '4')
ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;
