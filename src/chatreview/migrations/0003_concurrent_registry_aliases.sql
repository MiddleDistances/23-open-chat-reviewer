CREATE UNIQUE INDEX project_aliases_identity_idx
ON project_aliases(project_id, machine_id, path_prefix, provider, effective_from)
NULLS NOT DISTINCT;

INSERT INTO schema_meta(key, value) VALUES ('schema_version', '3')
ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;
