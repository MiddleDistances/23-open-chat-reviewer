-- Earlier maintenance releases installed this guard only after reclaiming.
-- Preserve that retirement state while making the schema reproducible on fresh installs.
INSERT INTO schema_meta(key,value)
SELECT 'timesheet_legacy_evidence_retired','1'
WHERE EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid='work_interval_evidence'::regclass
      AND tgname='retired_evidence_writes' AND NOT tgisinternal
)
ON CONFLICT (key) DO NOTHING;

CREATE OR REPLACE FUNCTION reject_legacy_evidence_writes()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
    IF EXISTS (SELECT 1 FROM schema_meta
               WHERE key='timesheet_legacy_evidence_retired' AND value='1') THEN
        RAISE EXCEPTION 'Legacy timesheet evidence retired; deploy shared-evidence writer';
    END IF;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS retired_evidence_writes ON work_interval_evidence;
CREATE TRIGGER retired_evidence_writes BEFORE INSERT OR UPDATE
    ON work_interval_evidence FOR EACH STATEMENT
    EXECUTE FUNCTION reject_legacy_evidence_writes();
