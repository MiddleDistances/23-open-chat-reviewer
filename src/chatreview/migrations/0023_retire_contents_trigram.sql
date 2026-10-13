-- Lexical retrieval uses contents_search_idx. The only remaining contents ILIKE
-- is an aggregate FILTER over semantic-window rows and cannot use this index.
-- Artifact substring search retains its separate trigram index.
DROP INDEX IF EXISTS contents_text_trgm_idx;
