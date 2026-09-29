-- Batch insert validation avoids a PL/pgSQL invocation and index probe per member.
-- The AFTER trigger is transactional: a referenced target aborts the entire insert.
DROP TRIGGER immutable_referenced_evidence ON timesheet_evidence_members;
CREATE TRIGGER immutable_referenced_evidence BEFORE UPDATE OR DELETE
    ON timesheet_evidence_members FOR EACH ROW EXECUTE FUNCTION protect_referenced_evidence_members();
CREATE FUNCTION protect_inserted_evidence_members() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM (SELECT DISTINCT evidence_set_id FROM inserted_evidence) target
        JOIN work_intervals w ON w.evidence_set_id=target.evidence_set_id
    ) THEN
        RAISE EXCEPTION 'Referenced evidence sets are immutable';
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER immutable_inserted_evidence AFTER INSERT ON timesheet_evidence_members
    REFERENCING NEW TABLE AS inserted_evidence
    FOR EACH STATEMENT EXECUTE FUNCTION protect_inserted_evidence_members();
