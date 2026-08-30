ALTER TABLE events
ADD COLUMN projection_index integer NOT NULL DEFAULT 0;

ALTER TABLE events
DROP CONSTRAINT events_raw_record_id_key;

ALTER TABLE events
DROP CONSTRAINT events_source_revision_id_line_no_key;

ALTER TABLE events
ADD CONSTRAINT events_raw_record_projection_key
UNIQUE (raw_record_id, projection_index);

CREATE INDEX events_source_line_projection_idx
ON events(source_revision_id, line_no, projection_index);
