ALTER TABLE source_revisions
ADD COLUMN provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb;
