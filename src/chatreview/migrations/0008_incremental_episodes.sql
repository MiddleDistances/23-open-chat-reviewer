CREATE TABLE episode_session_state (
    session_id bigint PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    segmentation_version integer NOT NULL,
    input_event_count bigint NOT NULL CHECK (input_event_count >= 0),
    input_max_event_id bigint NOT NULL,
    input_event_id_sum numeric NOT NULL,
    episode_count bigint NOT NULL CHECK (episode_count >= 0),
    built_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Seed the incremental ledger from the current complete generation. This makes
-- the migration itself additive: the first post-upgrade refresh only rebuilds
-- sessions whose effective event set has actually changed.
WITH session_inputs AS (
    SELECT e.session_id,
           COUNT(*) AS input_event_count,
           MAX(e.id) AS input_max_event_id,
           SUM(e.id::numeric) AS input_event_id_sum
    FROM events e
    JOIN sources source ON source.id=e.source_id
    WHERE e.session_id IS NOT NULL
      AND e.canonical_event_id IS NULL
      AND source.source_kind<>'history'
      AND e.event_type NOT IN ('compacted', 'parse-error', 'last-prompt', 'ai-title')
      AND EXISTS (SELECT 1 FROM text_units unit WHERE unit.event_id=e.id)
    GROUP BY e.session_id
), episode_counts AS (
    SELECT session_id, MAX(segmentation_version) AS segmentation_version,
           COUNT(*) AS episode_count
    FROM episodes
    GROUP BY session_id
)
INSERT INTO episode_session_state(
    session_id, segmentation_version, input_event_count,
    input_max_event_id, input_event_id_sum, episode_count
)
SELECT input.session_id, episodes.segmentation_version, input.input_event_count,
       input.input_max_event_id, input.input_event_id_sum, episodes.episode_count
FROM session_inputs input
JOIN episode_counts episodes ON episodes.session_id=input.session_id;

INSERT INTO schema_meta(key, value) VALUES ('schema_version', '8')
ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;
