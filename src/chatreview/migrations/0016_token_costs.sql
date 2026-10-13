-- Immutable operator price books and atomic, reproducible derived snapshots.
CREATE TABLE token_price_books (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version text NOT NULL UNIQUE,
    content_hash text NOT NULL UNIQUE,
    book_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE token_cost_settings (
    id integer PRIMARY KEY CHECK(id=1),
    price_book_id bigint NOT NULL REFERENCES token_price_books(id)
);
CREATE TABLE token_cost_snapshots (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_key text NOT NULL UNIQUE,
    corpus_fingerprint text NOT NULL,
    price_book_id bigint NOT NULL REFERENCES token_price_books(id),
    algorithm_version integer NOT NULL,
    timezone text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    coverage_json jsonb NOT NULL
);
-- Dimensions are copied as snapshot evidence, not live FKs: unattributed usage and
-- later project/session deletion must not mutate an already published cost report.
CREATE TABLE token_cost_rows (
    snapshot_id bigint NOT NULL REFERENCES token_cost_snapshots(id) ON DELETE CASCADE,
    row_index bigint NOT NULL,
    row_json jsonb NOT NULL,
    PRIMARY KEY(snapshot_id, row_index)
);
