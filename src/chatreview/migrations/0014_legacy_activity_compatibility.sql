-- Allow the open-source query surface to read the established predecessor archive.
-- This is a metadata-only, automatically updatable view. The predecessor table,
-- constraints, foreign keys, data, and private-only tables remain untouched.

DO $$
DECLARE
    archive_schema text := current_schema();
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_class relation
        JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
        WHERE namespace.nspname=archive_schema
          AND relation.relname='rd_activities'
          AND relation.relkind='r'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_class relation
        JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
        WHERE namespace.nspname=archive_schema
          AND relation.relname='activities'
    ) THEN
        EXECUTE format(
            'CREATE VIEW %I.activities AS '
            'SELECT id, code, title, classification, reporting_period_start, '
            'reporting_period_end, description, uncertainty_or_hypothesis, '
            'created_at, updated_at FROM %I.rd_activities',
            archive_schema,
            archive_schema
        );
    END IF;
END
$$;
