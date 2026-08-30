from __future__ import annotations

import json
import math
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson

from chatreview.config import Settings
from chatreview.db import Row, Session, database, ensure_vector_index
from chatreview.providers.base import stable_hash
from chatreview.search import SearchFilters

DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_MODEL_REVISION = "72bb2d1e482afe83dcebe9496edc693ad1967a0f"
SEMANTIC_VERSION = 6
SEMANTIC_POLICY = "postgresql-pgvector-conversation-and-episode-runs-v1"
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOP_WORDS = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "you",
    "your",
    "are",
    "was",
    "were",
    "have",
    "has",
    "had",
    "not",
    "but",
    "can",
    "will",
    "would",
    "should",
    "into",
    "then",
    "than",
    "when",
    "where",
    "what",
    "which",
    "while",
    "about",
    "after",
    "before",
    "using",
    "use",
    "used",
    "user",
    "assistant",
    "tool",
    "output",
    "message",
}


@dataclass(slots=True)
class DeriveOptions:
    model_name: str = DEFAULT_MODEL
    model_revision: str = DEFAULT_MODEL_REVISION
    dimensions: int = 512
    window_chars: int = 6000
    overlap_events: int = 1
    batch_size: int = 16
    max_projection_fit: int = 200_000
    device: str | None = None
    profile: str = "conversation"
    offline: bool = False
    force: bool = False


@dataclass(slots=True)
class DeriveSummary:
    run_id: int
    run_key: str
    windows: int
    clusters: int
    output_dir: Path
    reused: bool = False


class SemanticDeriver:
    def __init__(
        self,
        settings: Settings,
        *,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.progress = progress or (lambda _: None)

    def run(self, options: DeriveOptions | None = None) -> DeriveSummary:
        options = options or DeriveOptions()
        _validate_options(options)
        np, hdbscan, umap, SentenceTransformer = _semantic_imports()
        self.settings.ensure_output_dirs()
        with database(self.settings.database_url) as connection:
            config = {
                "semantic_version": SEMANTIC_VERSION,
                "semantic_policy": SEMANTIC_POLICY,
                "corpus_revision": corpus_revision(connection),
                "profile": options.profile,
                "model_name": options.model_name,
                "model_revision": options.model_revision,
                "dimensions": options.dimensions,
                "window_chars": options.window_chars,
                "overlap_events": options.overlap_events,
            }
            if options.profile == "episodes":
                episode_generation = connection.execute(
                    "SELECT value FROM schema_meta WHERE key='episode_generation'"
                ).fetchone()
                if episode_generation is None:
                    raise RuntimeError(
                        "episode derivation is missing; run `chatreview episodes` first"
                    )
                config["episode_generation"] = episode_generation["value"]
            run_key = stable_hash(orjson.dumps(config, option=orjson.OPT_SORT_KEYS))[:24]
            output_dir = self.settings.derived_dir / run_key
            output_dir.mkdir(parents=True, exist_ok=True)
            existing = connection.execute(
                "SELECT * FROM semantic_runs WHERE run_key=?", (run_key,)
            ).fetchone()
            if existing and existing["status"] == "complete" and not options.force:
                return DeriveSummary(
                    run_id=int(existing["id"]),
                    run_key=run_key,
                    windows=int(existing["chunk_count"]),
                    clusters=_cluster_count(connection, int(existing["id"])),
                    output_dir=output_dir,
                    reused=True,
                )
            if (
                existing
                and existing["status"] == "failed"
                and not options.force
                and self._activation_ready(connection, existing)
            ):
                run_id = int(existing["id"])
                self.progress(
                    "Resuming activation from complete stored embeddings and projection"
                )
                try:
                    return self._activate_run(
                        connection,
                        run_id=run_id,
                        run_key=run_key,
                        window_count=int(existing["expected_count"]),
                        cluster_count=_cluster_count(connection, run_id),
                        config=config,
                        profile=options.profile,
                        output_dir=output_dir,
                    )
                except BaseException as exc:
                    connection.rollback()
                    connection.execute(
                        "UPDATE semantic_runs SET status='failed', error=? WHERE id=?",
                        (f"{type(exc).__name__}: {exc}", run_id),
                    )
                    connection.commit()
                    raise
            run_id = self._prepare_run(connection, existing, run_key, config, options)
            vector_path: Path | None = None
            vectors: Any | None = None
            try:
                self.progress("Building deterministic semantic windows")
                window_count = self._build_windows(connection, run_id, options)
                connection.execute(
                    "UPDATE semantic_runs SET chunk_count=?, expected_count=? WHERE id=?",
                    (window_count, window_count, run_id),
                )
                connection.commit()
                if window_count == 0:
                    raise RuntimeError("no searchable text units are available; run ingest first")

                self.progress(
                    f"Loading local embedding model {options.model_name}@{options.model_revision[:12]}"
                )
                target_devices = _target_devices(options.device)
                model = SentenceTransformer(
                    options.model_name,
                    revision=options.model_revision,
                    truncate_dim=options.dimensions,
                    trust_remote_code=False,
                    device="cpu" if len(target_devices) > 1 else options.device,
                    model_kwargs={"torch_dtype": "auto"},
                    local_files_only=options.offline,
                )
                with tempfile.NamedTemporaryFile(
                    prefix="chatreview-embeddings-",
                    suffix=".f32",
                    dir=output_dir,
                    delete=False,
                ) as scratch:
                    vector_path = Path(scratch.name)
                vectors = np.memmap(
                    str(vector_path),
                    dtype="float32",
                    mode="w+",
                    shape=(window_count, options.dimensions),
                )
                self.progress(f"Embedding {window_count:,} windows")
                self._encode_windows(
                    connection,
                    run_id,
                    model,
                    vectors,
                    options,
                    target_devices=target_devices,
                )
                vectors.flush()

                self.progress("Computing clusters and 2D projection")
                projection, labels = _cluster_and_project(
                    vectors,
                    np=np,
                    hdbscan=hdbscan,
                    umap=umap,
                    max_fit=options.max_projection_fit,
                    progress=self.progress,
                )
                self._persist_projection(connection, run_id, projection, labels)
                cluster_count = self._summarize_clusters(connection, run_id, labels)
                embedded = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM semantic_windows WHERE run_id=? AND embedding IS NOT NULL",
                        (run_id,),
                    ).fetchone()[0]
                )
                if embedded != window_count:
                    raise RuntimeError(
                        f"embedding run is incomplete: expected {window_count}, stored {embedded}"
                    )
                summary = self._activate_run(
                    connection,
                    run_id=run_id,
                    run_key=run_key,
                    window_count=window_count,
                    cluster_count=cluster_count,
                    config=config,
                    profile=options.profile,
                    output_dir=output_dir,
                )
                _close_memmap(vectors)
                vectors = None
                assert vector_path is not None
                vector_path.unlink(missing_ok=True)
                return summary
            except BaseException as exc:
                _close_memmap(vectors)
                if vector_path is not None:
                    vector_path.unlink(missing_ok=True)
                connection.rollback()
                connection.execute(
                    "UPDATE semantic_runs SET status='failed', error=? WHERE id=?",
                    (f"{type(exc).__name__}: {exc}", run_id),
                )
                connection.commit()
                raise

    @staticmethod
    def _activation_ready(connection: Session, run: Row) -> bool:
        """Return whether a failed run has all durable data needed for activation."""

        expected = int(run["expected_count"])
        if expected <= 0 or int(run["chunk_count"]) != expected:
            return False
        counts = connection.execute(
            """
            SELECT COUNT(*) AS windows,
                   COUNT(embedding) AS embeddings,
                   COUNT(projection_x) AS projections,
                   COUNT(cluster_id) AS cluster_assignments
            FROM semantic_windows WHERE run_id=?
            """,
            (run["id"],),
        ).fetchone()
        assert counts is not None
        return all(int(counts[key]) == expected for key in counts)

    def _activate_run(
        self,
        connection: Session,
        *,
        run_id: int,
        run_key: str,
        window_count: int,
        cluster_count: int,
        config: dict[str, Any],
        profile: str,
        output_dir: Path,
    ) -> DeriveSummary:
        """Audit a complete stored vector run and atomically make it searchable."""

        self.progress("Building the cosine HNSW index")
        connection.commit()
        ensure_vector_index(self.settings.database_url)
        audit_vectors = [
            _vector_list(row["embedding"])
            for row in connection.execute(
                """
                SELECT embedding FROM semantic_windows
                WHERE run_id=? AND embedding IS NOT NULL
                ORDER BY id LIMIT 100
                """,
                (run_id,),
            )
        ]
        recall_at_10 = hnsw_recall_at_10(
            connection, run_id=run_id, query_vectors=audit_vectors
        )
        if recall_at_10 < 0.95:
            raise RuntimeError(
                f"HNSW Recall@10 {recall_at_10:.4f} is below the 0.95 activation threshold"
            )
        manifest = {
            **config,
            "run_id": run_id,
            "run_key": run_key,
            "window_count": window_count,
            "cluster_count": cluster_count,
            "vector_storage": "PostgreSQL pgvector",
            "hnsw_recall_at_10": recall_at_10,
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        )
        connection.execute(
            """
            UPDATE semantic_runs SET is_active=false
            WHERE profile=? AND id<>? AND is_active
            """,
            (profile, run_id),
        )
        connection.execute(
            """
            UPDATE semantic_runs SET status='complete', is_active=true,
                completed_at=CURRENT_TIMESTAMP, error=NULL WHERE id=?
            """,
            (run_id,),
        )
        connection.commit()
        _prune_embedding_runs(connection, profile)
        return DeriveSummary(run_id, run_key, window_count, cluster_count, output_dir)

    def _prepare_run(
        self,
        connection: Session,
        existing: Row | None,
        run_key: str,
        config: dict[str, Any],
        options: DeriveOptions,
    ) -> int:
        config_json = orjson.dumps(config, option=orjson.OPT_SORT_KEYS).decode()
        if existing:
            run_id = int(existing["id"])
            connection.execute("DELETE FROM semantic_windows WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM cluster_summaries WHERE run_id=?", (run_id,))
            connection.execute(
                """
                UPDATE semantic_runs SET status='building', is_active=false,
                    config_json=?, chunk_count=0, expected_count=0,
                    started_at=CURRENT_TIMESTAMP, completed_at=NULL, error=NULL
                WHERE id=?
                """,
                (config_json, run_id),
            )
        else:
            row = connection.execute(
                """
                INSERT INTO semantic_runs(
                    run_key, model_name, model_revision, dimensions, window_chars,
                    overlap_events, profile, corpus_fingerprint, derivation_version,
                    status, config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'building', ?)
                RETURNING id
                """,
                (
                    run_key,
                    options.model_name,
                    options.model_revision,
                    options.dimensions,
                    options.window_chars,
                    options.overlap_events,
                    options.profile,
                    config["corpus_revision"],
                    SEMANTIC_VERSION,
                    config_json,
                ),
            ).fetchone()
            assert row is not None
            run_id = int(row["id"])
        connection.commit()
        return run_id

    def _build_windows(self, connection: Session, run_id: int, options: DeriveOptions) -> int:
        if options.profile == "episodes":
            return self._build_episode_windows(
                connection,
                run_id,
                max_chars=options.window_chars,
            )
        profile_clause = _semantic_profile_clause(options.profile)
        sessions = connection.execute(
            """
            SELECT DISTINCT s.id, s.session_key
            FROM sessions s JOIN events e ON e.session_id=s.id
            JOIN text_units t ON t.event_id=e.id
            ORDER BY s.id
            """
        ).fetchall()
        total = 0
        for session_index, session in enumerate(sessions, start=1):
            rows = connection.execute(
                f"""
                SELECT e.id AS event_id, e.role, e.event_type, e.subtype, e.timestamp,
                       t.kind, t.label,
                       CASE
                           WHEN t.kind='tool-input' THEN substr(c.text, 1, 2500)
                           WHEN t.kind='tool-output' THEN substr(c.text, 1, 3000)
                           ELSE substr(c.text, 1, 12000)
                       END AS text
                FROM events e
                JOIN sources sf ON sf.id=e.source_id
                JOIN text_units t ON t.event_id=e.id
                JOIN contents c ON c.id=t.content_id
                WHERE e.session_id=?
                  AND e.canonical_event_id IS NULL
                  AND sf.source_kind<>'history'
                  AND ({profile_clause})
                ORDER BY e.timestamp NULLS FIRST, e.ordinal, t.unit_index
                """,
                (session["id"],),
            ).fetchall()
            event_segments = _event_segments(rows, options.window_chars)
            windows = _rolling_windows(
                event_segments,
                max_chars=options.window_chars,
                overlap_events=options.overlap_events,
            )
            for sequence_no, window in enumerate(windows):
                text = window["text"]
                content_hash = stable_hash(text)
                content_row = connection.execute(
                    "SELECT id FROM contents WHERE content_hash=?", (content_hash,)
                ).fetchone()
                if content_row:
                    content_id = int(content_row["id"])
                else:
                    inserted = connection.execute(
                        """
                        INSERT INTO contents(content_hash, text, char_count) VALUES (?, ?, ?)
                        RETURNING id
                        """,
                        (content_hash, text, len(text)),
                    ).fetchone()
                    assert inserted is not None
                    content_id = int(inserted["id"])
                window_key = stable_hash(
                    f"{session['session_key']}\0{window['first_event_id']}\0"
                    f"{window['last_event_id']}\0{sequence_no}\0{content_hash}"
                )
                connection.execute(
                    """
                    INSERT INTO semantic_windows(
                        run_id, window_key, session_id, first_event_id, last_event_id,
                        sequence_no, content_id, vector_ordinal
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        window_key,
                        session["id"],
                        window["first_event_id"],
                        window["last_event_id"],
                        sequence_no,
                        content_id,
                        total,
                    ),
                )
                total += 1
            if session_index % 100 == 0:
                connection.commit()
                self.progress(f"  windowed {session_index:,}/{len(sessions):,} sessions")
        connection.commit()
        return total

    def _build_episode_windows(
        self,
        connection: Session,
        run_id: int,
        *,
        max_chars: int,
    ) -> int:
        episodes = connection.execute(
            """
            SELECT ep.id, ep.episode_key, ep.session_id, ep.sequence_no,
                   ep.first_event_id, ep.last_event_id, c.text AS document
            FROM episodes ep
            JOIN contents c ON c.id=ep.document_content_id
            ORDER BY ep.session_id, ep.sequence_no, ep.id
            """
        ).fetchall()
        for vector_ordinal, episode in enumerate(episodes):
            window_key = stable_hash(f"episode\0{episode['episode_key']}")
            text = _episode_embedding_text(episode["document"], max_chars=max_chars)
            content_hash = stable_hash(text)
            content = connection.execute(
                "SELECT id FROM contents WHERE content_hash=?",
                (content_hash,),
            ).fetchone()
            if content is None:
                inserted = connection.execute(
                    """
                    INSERT INTO contents(content_hash, text, char_count) VALUES (?, ?, ?)
                    RETURNING id
                    """,
                    (content_hash, text, len(text)),
                ).fetchone()
                assert inserted is not None
                content_id = int(inserted["id"])
            else:
                content_id = int(content["id"])
            connection.execute(
                """
                INSERT INTO semantic_windows(
                    run_id, window_key, session_id, episode_id, first_event_id,
                    last_event_id, sequence_no, content_id, vector_ordinal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    window_key,
                    episode["session_id"],
                    episode["id"],
                    episode["first_event_id"],
                    episode["last_event_id"],
                    episode["sequence_no"],
                    content_id,
                    vector_ordinal,
                ),
            )
            if vector_ordinal and vector_ordinal % 10_000 == 0:
                connection.commit()
                self.progress(f"  staged {vector_ordinal:,}/{len(episodes):,} episodes")
        connection.commit()
        return len(episodes)

    def _encode_windows(
        self,
        connection: Session,
        run_id: int,
        model: Any,
        vectors: Any,
        options: DeriveOptions,
        *,
        target_devices: list[str],
    ) -> None:
        processed = 0
        if len(target_devices) > 1:
            pool = model.start_multi_process_pool(target_devices)
            fetch_size = max(options.batch_size * 250, 4_000)
            try:
                last_ordinal = -1
                while rows := connection.execute(
                    """
                    SELECT w.vector_ordinal, c.text
                    FROM semantic_windows w JOIN contents c ON c.id=w.content_id
                    WHERE w.run_id=? AND w.vector_ordinal>? ORDER BY w.vector_ordinal LIMIT ?
                    """,
                    (run_id, last_ordinal, fetch_size),
                ).fetchall():
                    texts = [row["text"] for row in rows]
                    encoded = model.encode_multi_process(
                        texts,
                        pool,
                        batch_size=options.batch_size,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )
                    updates = []
                    for row, vector in zip(rows, encoded, strict=True):
                        vectors[int(row["vector_ordinal"])] = vector
                        updates.append((vector.tolist(), run_id, int(row["vector_ordinal"])))
                    connection.executemany(
                        """
                        UPDATE semantic_windows SET embedding=?
                        WHERE run_id=? AND vector_ordinal=?
                        """,
                        updates,
                    )
                    connection.commit()
                    last_ordinal = int(rows[-1]["vector_ordinal"])
                    processed += len(rows)
                    self.progress(f"  embedded {processed:,} windows")
            finally:
                model.stop_multi_process_pool(pool)
        else:
            last_ordinal = -1
            while rows := connection.execute(
                """
                SELECT w.vector_ordinal, c.text
                FROM semantic_windows w JOIN contents c ON c.id=w.content_id
                WHERE w.run_id=? AND w.vector_ordinal>? ORDER BY w.vector_ordinal LIMIT ?
                """,
                (run_id, last_ordinal, options.batch_size),
            ).fetchall():
                texts = [row["text"] for row in rows]
                encoded = model.encode(
                    texts,
                    batch_size=options.batch_size,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
                updates = []
                for row, vector in zip(rows, encoded, strict=True):
                    vectors[int(row["vector_ordinal"])] = vector
                    updates.append((vector.tolist(), run_id, int(row["vector_ordinal"])))
                connection.executemany(
                    """
                    UPDATE semantic_windows SET embedding=?
                    WHERE run_id=? AND vector_ordinal=?
                    """,
                    updates,
                )
                connection.commit()
                last_ordinal = int(rows[-1]["vector_ordinal"])
                processed += len(rows)
                if processed % max(options.batch_size * 20, 1000) < options.batch_size:
                    self.progress(f"  embedded {processed:,} windows")

    def _persist_projection(
        self, connection: Session, run_id: int, projection: Any, labels: Any
    ) -> None:
        batch = []
        for ordinal in range(len(labels)):
            batch.append(
                (
                    int(labels[ordinal]),
                    float(projection[ordinal][0]),
                    float(projection[ordinal][1]),
                    run_id,
                    ordinal,
                )
            )
            if len(batch) == 10_000:
                connection.executemany(
                    """
                    UPDATE semantic_windows
                    SET cluster_id=?, projection_x=?, projection_y=?
                    WHERE run_id=? AND vector_ordinal=?
                    """,
                    batch,
                )
                connection.commit()
                batch.clear()
        if batch:
            connection.executemany(
                """
                UPDATE semantic_windows SET cluster_id=?, projection_x=?, projection_y=?
                WHERE run_id=? AND vector_ordinal=?
                """,
                batch,
            )
        connection.commit()

    def _summarize_clusters(self, connection: Session, run_id: int, labels: Any) -> int:
        cluster_ids = sorted({int(label) for label in labels if int(label) >= 0})
        global_words: Counter[str] = Counter()
        cluster_words: dict[int, Counter[str]] = defaultdict(Counter)
        counts: Counter[int] = Counter(int(label) for label in labels)
        cursor = connection.execute(
            """
            SELECT w.cluster_id, c.text FROM semantic_windows w
            JOIN contents c ON c.id=w.content_id WHERE w.run_id=?
            """,
            (run_id,),
        )
        for row in cursor:
            cluster_id = int(row["cluster_id"])
            words = {word.lower() for word in WORD_PATTERN.findall(row["text"][:12_000])}
            words.difference_update(STOP_WORDS)
            global_words.update(words)
            if cluster_id >= 0:
                cluster_words[cluster_id].update(words)
        total_windows = max(len(labels), 1)
        for cluster_id in cluster_ids:
            scored = []
            cluster_size = max(counts[cluster_id], 1)
            for word, frequency in cluster_words[cluster_id].items():
                global_frequency = global_words[word]
                score = (frequency / cluster_size) * math.log1p(total_windows / global_frequency)
                scored.append((score, word))
            keywords = [word for _, word in sorted(scored, reverse=True)[:8]]
            label = " · ".join(keywords[:3]) if keywords else f"Cluster {cluster_id}"
            connection.execute(
                """
                INSERT INTO cluster_summaries(run_id, cluster_id, label, keywords_json, window_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, cluster_id, label, json.dumps(keywords), counts[cluster_id]),
            )
        if counts[-1]:
            connection.execute(
                """
                INSERT INTO cluster_summaries(run_id, cluster_id, label, keywords_json, window_count)
                VALUES (?, -1, 'Unclustered', '[]', ?)
                """,
                (run_id, counts[-1]),
            )
        connection.commit()
        return len(cluster_ids)


class SemanticSearchService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._run_id: int | None = None
        self._model: Any = None

    def available_run(
        self,
        connection: Session,
        *,
        profile: str | None = None,
        run_key: str | None = None,
    ) -> dict[str, Any] | None:
        clauses = ["status='complete'"]
        parameters: list[Any] = []
        if profile:
            clauses.append("profile=?")
            parameters.append(profile)
        if run_key:
            clauses.append("run_key=?")
            parameters.append(run_key)
        row = connection.execute(
            f"""
            SELECT * FROM semantic_runs WHERE {" AND ".join(clauses)}
            ORDER BY
                is_active DESC,
                CASE WHEN profile='conversation' THEN 0 ELSE 1 END,
                completed_at DESC, id DESC LIMIT 1
            """,
            parameters,
        ).fetchone()
        if row is None:
            return None
        result = {key: row[key] for key in row.keys()}
        result["freshness"] = semantic_run_freshness(connection, result)
        return result

    def search(
        self,
        connection: Session,
        query: str,
        *,
        filters: SearchFilters | None = None,
        limit: int = 30,
        profile: str | None = None,
        run_key: str | None = None,
    ) -> list[dict[str, Any]]:
        run = self.available_run(connection, profile=profile, run_key=run_key)
        if run is None:
            return []
        self._load(run)
        vector = self._model.encode(
            [query],
            prompt_name="query",
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32")[0].tolist()
        filters = filters or SearchFilters()
        clauses = ["w.run_id=?", "w.embedding IS NOT NULL"]
        filter_parameters: list[Any] = [run["id"]]
        mapping = (
            ("s.provider=?", filters.provider),
            ("(project.project_key=? OR project.name=? OR s.project=?)", filters.project),
            ("contributor.display_name=?", filters.contributor),
            ("(activity.code=? OR activity.title=?)", filters.activity),
            ("activity.classification=?", filters.activity_classification),
            ("s.started_at>=?", filters.date_from),
            ("s.ended_at<=?", filters.date_to),
        )
        for clause, value in mapping:
            if not value:
                continue
            clauses.append(clause)
            filter_parameters.extend([value] * clause.count("?"))
        connection.execute("SET LOCAL hnsw.ef_search=100")
        connection.execute("SET LOCAL hnsw.iterative_scan='strict_order'")
        rows = connection.execute(
            f"""
            SELECT CASE WHEN w.episode_id IS NULL THEN 'window' ELSE 'occurrence' END
                       AS target_type,
                   COALESCE(episode.episode_key, w.window_key) AS target_key,
                   w.id AS window_id, w.window_key, w.sequence_no, w.cluster_id,
                   w.episode_id, w.projection_x, w.projection_y,
                   w.first_event_id, w.last_event_id,
                   NULL::double precision AS lexical_score,
                   (1 - (w.embedding <=> ?::vector))::double precision AS semantic_score,
                   left(c.text, 1000) AS snippet,
                   s.id AS session_id, s.session_key, s.external_id,
                   s.provider, COALESCE(project.name, s.project) AS project,
                   project.project_key, contributor.display_name AS contributor,
                   activity.code AS activity, activity.title AS activity_title,
                   activity.classification AS activity_classification,
                   first_event.timestamp, source.path AS source_path,
                   first_event.raw_record_id, raw.payload_hash AS provenance_hash,
                   ? AS semantic_run_key, ? AS semantic_profile
            FROM semantic_windows w
            JOIN contents c ON c.id=w.content_id
            JOIN sessions s ON s.id=w.session_id
            JOIN events first_event ON first_event.id=w.first_event_id
            JOIN sources source ON source.id=first_event.source_id
            JOIN raw_records raw ON raw.id=first_event.raw_record_id
            LEFT JOIN episodes episode ON episode.id=w.episode_id
            LEFT JOIN LATERAL (
                SELECT override.activity_id, override.project_id
                FROM occurrence_activity_overrides override
                WHERE override.episode_key=COALESCE(
                    episode.episode_key,
                    (
                        SELECT linked_episode.episode_key
                        FROM episode_events link
                        JOIN episodes linked_episode ON linked_episode.id=link.episode_id
                        WHERE link.event_id=first_event.id
                        ORDER BY linked_episode.id LIMIT 1
                    )
                )
            ) occurrence ON true
            LEFT JOIN projects project
              ON project.id=COALESCE(occurrence.project_id, s.project_id)
            LEFT JOIN contributors contributor ON contributor.id=s.contributor_id
            LEFT JOIN LATERAL (
                SELECT a.code, a.title, a.classification
                FROM activities a
                WHERE a.id=COALESCE(
                    occurrence.activity_id,
                    (
                        SELECT defaults.activity_id
                        FROM project_default_activities defaults
                        WHERE defaults.project_id=COALESCE(occurrence.project_id, s.project_id)
                          AND COALESCE(first_event.timestamp, clock_timestamp())
                              >= defaults.effective_from
                          AND COALESCE(first_event.timestamp, clock_timestamp())
                              < defaults.effective_to
                        ORDER BY defaults.effective_from DESC LIMIT 1
                    )
                )
            ) activity ON true
            WHERE {" AND ".join(clauses)}
            ORDER BY w.embedding <=> ?::vector
            LIMIT ?
            """,
            [
                vector,
                run["run_key"],
                run["profile"],
                *filter_parameters,
                vector,
                min(max(limit, 1), 500),
            ],
        ).fetchall()
        return [dict(row) for row in rows]

    def _load(self, run: dict[str, Any]) -> None:
        if self._run_id == int(run["id"]):
            return
        _, _, _, SentenceTransformer = _semantic_imports()
        self._model = SentenceTransformer(
            run["model_name"],
            revision=run["model_revision"],
            truncate_dim=int(run["dimensions"]),
            trust_remote_code=False,
            model_kwargs={"torch_dtype": "auto"},
            local_files_only=True,
        )
        self._run_id = int(run["id"])


def map_points(
    connection: Session,
    *,
    run_id: int | None = None,
    profile: str | None = None,
    provider: str | None = None,
    project: str | None = None,
    cluster_id: int | None = None,
    limit: int = 200_000,
) -> dict[str, Any]:
    if run_id is None:
        profile_clause = "" if profile is None else "AND profile=?"
        profile_parameters = () if profile is None else (profile,)
        run = connection.execute(
            f"""
            SELECT id FROM semantic_runs
            WHERE status='complete'
              {profile_clause}
            ORDER BY
                is_active DESC,
                CASE WHEN profile='conversation' THEN 0 ELSE 1 END,
                completed_at DESC LIMIT 1
            """,
            profile_parameters,
        ).fetchone()
        if run is None:
            return {"run": None, "points": [], "clusters": []}
        run_id = int(run["id"])
    clauses = ["w.run_id=?", "w.projection_x IS NOT NULL"]
    parameters: list[Any] = [run_id]
    if provider:
        clauses.append("s.provider=?")
        parameters.append(provider)
    if project:
        clauses.append("s.project=?")
        parameters.append(project)
    if cluster_id is not None:
        clauses.append("w.cluster_id=?")
        parameters.append(cluster_id)
    total = int(
        connection.execute(
            f"""
            SELECT COUNT(*) FROM semantic_windows w JOIN sessions s ON s.id=w.session_id
            WHERE {" AND ".join(clauses)}
            """,
            parameters,
        ).fetchone()[0]
    )
    stride = max(1, math.ceil(total / max(limit, 1)))
    point_parameters = [*parameters, stride, min(total, limit)]
    points = [
        {key: row[key] for key in row.keys()}
        for row in connection.execute(
            f"""
            SELECT w.id, w.window_key, w.sequence_no, w.cluster_id, w.episode_id,
                   ep.episode_key,
                   w.projection_x AS x, w.projection_y AS y,
                   s.id AS session_id, s.provider, s.project,
                   substr(c.text, 1, 300) AS preview
            FROM semantic_windows w
            JOIN sessions s ON s.id=w.session_id
            JOIN contents c ON c.id=w.content_id
            LEFT JOIN episodes ep ON ep.id=w.episode_id
            WHERE {" AND ".join(clauses)} AND (w.vector_ordinal % ?)=0
            ORDER BY w.vector_ordinal LIMIT ?
            """,
            point_parameters,
        ).fetchall()
    ]
    clusters = [
        {key: row[key] for key in row.keys()}
        for row in connection.execute(
            """
            SELECT cluster_id, label, keywords_json, window_count
            FROM cluster_summaries WHERE run_id=? ORDER BY window_count DESC
            """,
            (run_id,),
        ).fetchall()
    ]
    run_row = connection.execute(
        """
        SELECT id, run_key, model_name, model_revision, dimensions, chunk_count,
               completed_at, status, error, profile, corpus_fingerprint, config_json
        FROM semantic_runs WHERE id=?
        """,
        (run_id,),
    ).fetchone()
    run_data = {key: run_row[key] for key in run_row.keys()} if run_row else None
    if run_data is not None:
        run_data.pop("config_json")
        run_data["freshness"] = semantic_run_freshness(connection, {"config_json": run_row["config_json"]})
    return {
        "run": run_data,
        "total": total,
        "sample_stride": stride,
        "points": points,
        "clusters": clusters,
    }


def _event_segments(rows: list[Row], max_chars: int) -> list[dict[str, Any]]:
    grouped: list[tuple[int, list[str]]] = []
    current_event: int | None = None
    current_parts: list[str] = []
    for row in rows:
        event_id = int(row["event_id"])
        if current_event is not None and event_id != current_event:
            grouped.append((current_event, current_parts))
            current_parts = []
        current_event = event_id
        header = row["role"] or row["kind"] or row["event_type"]
        current_parts.append(f"[{header}]\n{row['text']}")
    if current_event is not None:
        grouped.append((current_event, current_parts))

    segments = []
    for event_id, parts in grouped:
        text = "\n\n".join(parts)
        if len(text) <= max_chars:
            segments.append({"event_id": event_id, "text": text})
            continue
        for start in range(0, len(text), max_chars):
            segments.append({"event_id": event_id, "text": text[start : start + max_chars]})
    return segments


def _episode_embedding_text(document: str, *, max_chars: int) -> str:
    """Keep every populated evidence section while bounding attention memory."""
    if len(document) <= max_chars:
        return document
    matches = list(re.finditer(r"(?m)^\[([A-Z ]+)\]\n", document))
    if not matches:
        return document[:max_chars]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(document)
        sections.append((match.group(1), document[match.end() : end].strip()))
    sections = [(name, value) for name, value in sections if value]
    if not sections:
        return document[:max_chars]
    header_chars = sum(len(name) + 4 for name, _ in sections)
    available = max(max_chars - header_chars - (2 * max(len(sections) - 1, 0)), 1)
    budgets = _balanced_budgets([len(value) for _, value in sections], available)
    parts = []
    for (name, value), budget in zip(sections, budgets, strict=True):
        if len(value) > budget:
            value = value[: max(budget - 1, 0)] + ("…" if budget else "")
        parts.append(f"[{name}]\n{value}")
    return "\n\n".join(parts)[:max_chars]


def _balanced_budgets(lengths: list[int], total: int) -> list[int]:
    budgets = [0] * len(lengths)
    remaining = total
    active = set(range(len(lengths)))
    while active and remaining > 0:
        share = max(remaining // len(active), 1)
        progressed = False
        for index in list(active):
            need = lengths[index] - budgets[index]
            addition = min(need, share, remaining)
            budgets[index] += addition
            remaining -= addition
            progressed = progressed or addition > 0
            if budgets[index] >= lengths[index]:
                active.remove(index)
            if remaining == 0:
                break
        if not progressed:
            break
    return budgets


def _rolling_windows(
    segments: list[dict[str, Any]], *, max_chars: int, overlap_events: int
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        if not current:
            return
        windows.append(
            {
                "first_event_id": current[0]["event_id"],
                "last_event_id": current[-1]["event_id"],
                "text": "\n\n".join(item["text"] for item in current),
            }
        )

    for segment in segments:
        proposed = sum(len(item["text"]) + 2 for item in current) + len(segment["text"])
        if current and proposed > max_chars:
            flush()
            retained: list[dict[str, Any]] = []
            retained_events: set[int] = set()
            for item in reversed(current):
                if item["event_id"] not in retained_events and len(retained_events) >= overlap_events:
                    break
                retained.insert(0, item)
                retained_events.add(item["event_id"])
            current = retained
            while (
                current and sum(len(item["text"]) + 2 for item in current) + len(segment["text"]) > max_chars
            ):
                current.pop(0)
        current.append(segment)
    flush()
    return windows


def _cluster_and_project(vectors: Any, *, np: Any, hdbscan: Any, umap: Any, max_fit: int, progress: Any):
    count = len(vectors)
    if count < 5:
        projection = np.zeros((count, 2), dtype="float32")
        if count:
            projection[:, : min(2, vectors.shape[1])] = np.asarray(vectors[:, : min(2, vectors.shape[1])])
        return projection, np.full(count, -1, dtype="int32")
    rng = np.random.default_rng(42)
    if count > max_fit:
        fit_indices = np.sort(rng.choice(count, size=max_fit, replace=False))
        fit_vectors = np.asarray(vectors[fit_indices])
        progress(f"  fitting UMAP/HDBSCAN on a deterministic {max_fit:,}-window sample")
    else:
        fit_indices = np.arange(count)
        fit_vectors = np.asarray(vectors)
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=min(30, max(2, len(fit_vectors) - 1)),
        min_dist=0.08,
        metric="cosine",
        random_state=42,
        init="random",
        n_jobs=1,
        low_memory=True,
    )
    fit_projection = reducer.fit_transform(fit_vectors).astype("float32")
    min_cluster = max(5, min(50, len(fit_vectors) // 250))
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster,
        min_samples=max(2, min_cluster // 3),
        metric="euclidean",
        prediction_data=count > max_fit,
    )
    # Clustering the deterministic manifold is both tractable for large corpora and
    # keeps cluster boundaries coherent with the map that a reviewer actually sees.
    fit_labels = clusterer.fit_predict(fit_projection).astype("int32")
    if count <= max_fit:
        return fit_projection, fit_labels
    projection = np.empty((count, 2), dtype="float32")
    labels = np.full(count, -1, dtype="int32")
    projection[fit_indices] = fit_projection
    labels[fit_indices] = fit_labels
    mask = np.ones(count, dtype=bool)
    mask[fit_indices] = False
    remaining = np.flatnonzero(mask)
    for start in range(0, len(remaining), 20_000):
        indices = remaining[start : start + 20_000]
        batch = np.asarray(vectors[indices])
        projection[indices] = reducer.transform(batch).astype("float32")
        predicted, _ = hdbscan.approximate_predict(clusterer, batch)
        labels[indices] = predicted.astype("int32")
        progress(f"  projected {min(start + len(indices), len(remaining)):,}/{len(remaining):,} remaining")
    return projection, labels


def _semantic_filter(row: Row, filters: SearchFilters) -> bool:
    if filters.provider and row["provider"] != filters.provider:
        return False
    if filters.project and row["project"] != filters.project:
        return False
    if filters.date_from and row["ended_at"] and row["ended_at"] < filters.date_from:
        return False
    if filters.date_to and row["started_at"] and row["started_at"] > filters.date_to:
        return False
    return True


def _cluster_count(connection: Session, run_id: int) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM cluster_summaries WHERE run_id=? AND cluster_id>=0", (run_id,)
        ).fetchone()[0]
    )


def corpus_revision(connection: Session) -> str:
    """Fingerprint the exact catalog state consumed by a semantic derivation."""
    rows = connection.execute(
        """
        SELECT source.machine_id, source.provider, source.path, source.source_kind,
               revision.id AS source_revision_id, revision.parser_version,
               revision.size_bytes, revision.ingested_offset, revision.ingested_lines,
               revision.head_hash, revision.checkpoint_hash, revision.aggregate_hash,
               revision.status, revision.error_count
        FROM sources source
        JOIN source_revisions revision ON revision.id=source.active_revision_id
        ORDER BY source.machine_id, source.provider, source.path
        """
    ).fetchall()
    snapshot = [[row[key] for key in row.keys()] for row in rows]
    return stable_hash(orjson.dumps(snapshot))


def semantic_run_freshness(connection: Session, run: dict[str, Any]) -> str:
    config = _config_json(run.get("config_json"))
    recorded = config.get("corpus_revision")
    if not recorded:
        return "unknown"
    if recorded != corpus_revision(connection):
        return "stale"
    if config.get("profile") == "episodes" and config.get("episode_generation"):
        generation = connection.execute(
            "SELECT value FROM schema_meta WHERE key='episode_generation'"
        ).fetchone()
        if generation is None or generation["value"] != config["episode_generation"]:
            return "stale"
    return "current"


def list_semantic_runs(connection: Session) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, run_key, model_name, model_revision, dimensions, chunk_count,
               completed_at, status, error, config_json
        FROM semantic_runs
        ORDER BY completed_at DESC, id DESC
        """
    ).fetchall()
    result = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        config = _config_json(item.pop("config_json"))
        item["profile"] = config.get("profile", "legacy")
        item["freshness"] = semantic_run_freshness(
            connection,
            {"config_json": row["config_json"]},
        )
        result.append(item)
    return result


def _config_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = orjson.loads(value)
    except (orjson.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _validate_options(options: DeriveOptions) -> None:
    if options.dimensions != 512:
        raise ValueError("PostgreSQL semantic runs use the fixed vector(512) profile")
    if options.window_chars < 500:
        raise ValueError("window_chars must be at least 500")
    if options.overlap_events < 0:
        raise ValueError("overlap_events cannot be negative")
    if options.batch_size < 1:
        raise ValueError("batch_size must be positive")
    if options.profile not in {"conversation", "episodes"}:
        raise ValueError("profile must be conversation or episodes")


def _target_devices(value: str | None) -> list[str]:
    if not value:
        return []
    return [device.strip() for device in value.split(",") if device.strip()]


def _semantic_profile_clause(profile: str) -> str:
    conversation = """
        t.kind IN (
            'user-message', 'assistant-message', 'message', 'reasoning',
            'agent-message', 'context-summary', 'compaction-summary',
            'last-prompt', 'ai-title', 'pasted-content', 'error'
        )
    """
    if profile == "conversation":
        return conversation
    if profile == "episodes":
        return "0"
    raise ValueError(f"unknown semantic profile: {profile}")


def _semantic_imports():
    try:
        import hdbscan
        import numpy as np
        import umap
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("semantic dependencies are not installed; run `uv sync --extra semantic`") from exc
    return np, hdbscan, umap, SentenceTransformer


def _prune_embedding_runs(connection: Session, profile: str) -> None:
    """Keep vectors for only the active and immediately previous complete runs."""

    old = connection.execute(
        """
        SELECT id FROM semantic_runs
        WHERE profile=? AND status='complete'
        ORDER BY is_active DESC, completed_at DESC NULLS LAST, id DESC
        OFFSET 2
        """,
        (profile,),
    ).fetchall()
    for row in old:
        connection.execute("DELETE FROM semantic_windows WHERE run_id=?", (row["id"],))
        connection.execute("DELETE FROM cluster_summaries WHERE run_id=?", (row["id"],))
        connection.execute(
            "UPDATE semantic_runs SET status='stale', is_active=false WHERE id=?",
            (row["id"],),
        )
    connection.commit()


def hnsw_recall_at_10(
    connection: Session,
    *,
    run_id: int,
    query_vectors: list[list[float]],
) -> float:
    """Compare HNSW results with exact pgvector search for activation audits."""

    recalls = []
    for vector in query_vectors:
        connection.execute("SET LOCAL hnsw.ef_search=100")
        connection.execute("SET LOCAL hnsw.iterative_scan='strict_order'")
        approximate = {
            int(row["id"])
            for row in connection.execute(
                """
                SELECT id FROM semantic_windows
                WHERE run_id=? AND embedding IS NOT NULL
                ORDER BY embedding <=> ?::vector LIMIT 10
                """,
                (run_id, vector),
            )
        }
        connection.execute("SET LOCAL enable_indexscan=off")
        connection.execute("SET LOCAL enable_bitmapscan=off")
        exact = {
            int(row["id"])
            for row in connection.execute(
                """
                SELECT id FROM semantic_windows
                WHERE run_id=? AND embedding IS NOT NULL
                ORDER BY embedding <=> ?::vector LIMIT 10
                """,
                (run_id, vector),
            )
        }
        connection.execute("SET LOCAL enable_indexscan=on")
        connection.execute("SET LOCAL enable_bitmapscan=on")
        recalls.append(len(approximate & exact) / max(len(exact), 1))
    return sum(recalls) / len(recalls) if recalls else 1.0


def _vector_list(value: Any) -> list[float]:
    if hasattr(value, "to_list"):
        return list(value.to_list())
    if hasattr(value, "tolist"):
        return list(value.tolist())
    if isinstance(value, str):
        return [float(item) for item in value.strip("[]").split(",")]
    return list(value)


def _close_memmap(value: Any | None) -> None:
    if value is None:
        return
    value.flush()
    mapped = getattr(value, "_mmap", None)
    if mapped is not None:
        mapped.close()
