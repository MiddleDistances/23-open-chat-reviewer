from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier
from psycopg_pool import ConnectionPool

SCHEMA_VERSION = 14
MIGRATION_LOCK_ID = 0x43485256574D4947  # "CHR VWMIG", stable across processes.
MIGRATIONS_DIR = Path(__file__).with_name("migrations")
LEGACY_MIGRATION_CHECKSUMS = {
    (
        1,
        "0001_postgresql_archive.sql",
    ): frozenset(
        {
            # The private predecessor archive used rd_activities and retained
            # additional R&D tables. Migration 0014 provides the only alias the
            # open-source read/query surface needs without rewriting that history.
            "f7abb72c1878dc702ce80f2febef40cf897cbff08bb938f0b5e8e8c76575e740"
        }
    )
}
SEARCH_INDEXES = {
    "sources_path_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS sources_path_trgm_idx "
        "ON sources USING gin(path gin_trgm_ops)"
    ),
    "projects_name_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS projects_name_trgm_idx "
        "ON projects USING gin(name gin_trgm_ops)"
    ),
    "projects_repository_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS projects_repository_trgm_idx "
        "ON projects USING gin(repository_url gin_trgm_ops)"
    ),
    "project_aliases_path_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS project_aliases_path_trgm_idx "
        "ON project_aliases USING gin(path_prefix gin_trgm_ops)"
    ),
    "activities_title_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS activities_title_trgm_idx "
        "ON activities USING gin(title gin_trgm_ops)"
    ),
    "sessions_project_text_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS sessions_project_text_trgm_idx "
        "ON sessions USING gin(project gin_trgm_ops)"
    ),
    "sessions_cwd_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS sessions_cwd_trgm_idx "
        "ON sessions USING gin(cwd gin_trgm_ops)"
    ),
    "sessions_title_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS sessions_title_trgm_idx "
        "ON sessions USING gin(title gin_trgm_ops)"
    ),
    "contents_search_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS contents_search_idx ON contents USING gin(search_vector)"
    ),
    "contents_text_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS contents_text_trgm_idx "
        "ON contents USING gin(text gin_trgm_ops)"
    ),
    "artifacts_value_trgm_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS artifacts_value_trgm_idx "
        "ON artifacts USING gin(value gin_trgm_ops)"
    ),
    "semantic_windows_embedding_hnsw_idx": (
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS semantic_windows_embedding_hnsw_idx "
        "ON semantic_windows USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    ),
}
VECTOR_INDEX = "semantic_windows_embedding_hnsw_idx"


class DatabaseError(RuntimeError):
    """Raised when the PostgreSQL archive cannot satisfy its interface."""


class Row(dict[str, Any]):
    """Dictionary row that also supports the legacy positional reads being removed."""

    __slots__ = ("_columns",)

    def __init__(self, values: Mapping[str, Any]) -> None:
        super().__init__(values)
        self._columns = tuple(values)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            key = self._columns[key]
        return super().__getitem__(key)


class Cursor:
    """Small result interface used by the rest of ChatReviewer."""

    __slots__ = ("_cursor",)

    def __init__(self, cursor: psycopg.Cursor[dict[str, Any]]) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self) -> Row | None:
        value = self._cursor.fetchone()
        return Row(value) if value is not None else None

    def fetchmany(self, size: int = 0) -> list[Row]:
        values = self._cursor.fetchmany(size) if size else self._cursor.fetchmany()
        return [Row(value) for value in values]

    def fetchall(self) -> list[Row]:
        return [Row(value) for value in self._cursor.fetchall()]

    def __iter__(self) -> Iterator[Row]:
        for value in self._cursor:
            yield Row(value)


class Session:
    """The single PostgreSQL seam used by feature modules and tests.

    Callers receive dictionary-like rows and explicit transaction controls. SQL
    placeholder conversion is deliberately private: PostgreSQL connection, pooling,
    row factories, pgvector registration, and transaction details do not escape this
    module.
    """

    __slots__ = ("_connection",)

    def __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None:
        self._connection = connection

    @property
    def raw_connection(self) -> psycopg.Connection[dict[str, Any]]:
        """Expose the owned connection only for PostgreSQL COPY and vector internals."""

        return self._connection

    def execute(self, query: str, parameters: Sequence[Any] | Mapping[str, Any] | None = None) -> Cursor:
        converted = _qmark_to_psycopg(query) if parameters is not None else query
        cursor = self._connection.execute(converted, parameters)
        return Cursor(cursor)

    def executemany(self, query: str, parameters: Iterable[Sequence[Any]]) -> Cursor:
        cursor = self._connection.cursor(row_factory=dict_row)
        cursor.executemany(_qmark_to_psycopg(query), parameters)
        return Cursor(cursor)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    @contextmanager
    def advisory_lock(self, identity: str) -> Iterator[None]:
        """Hold one session-level advisory lock across resumable batch commits."""

        key = advisory_key(identity)
        self._connection.execute("SELECT pg_advisory_lock(%s)", (key,))
        try:
            yield
        finally:
            try:
                self._connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
            except psycopg.errors.InFailedSqlTransaction:
                # A failed statement inside the protected source transaction must
                # not strand a session-level lock on a pooled connection.
                self._connection.rollback()
                self._connection.execute("SELECT pg_advisory_unlock(%s)", (key,))

    @contextmanager
    def try_advisory_lock(self, identity: str) -> Iterator[bool]:
        """Try to hold a session-level advisory lock without waiting for its owner."""

        key = advisory_key(identity)
        row = self._connection.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (key,)).fetchone()
        acquired = bool(row and row["acquired"])
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    self._connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
                except psycopg.errors.InFailedSqlTransaction:
                    self._connection.rollback()
                    self._connection.execute("SELECT pg_advisory_unlock(%s)", (key,))

    def copy_rows(self, table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> int:
        """COPY a trusted internal row shape into a staging table."""

        if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
            raise ValueError("invalid COPY table")
        if not columns or any(not re.fullmatch(r"[a-z_][a-z0-9_]*", item) for item in columns):
            raise ValueError("invalid COPY columns")
        count = 0
        statement = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
        with self._connection.cursor().copy(statement) as copy:
            for row in rows:
                copy.write_row(row)
                count += 1
        return count


@dataclass(frozen=True, slots=True)
class DoctorReport:
    server_version: str
    database: str
    user: str
    extensions: dict[str, str]
    migration_count: int
    latest_migration: str | None
    wal_level: str
    archive_mode: str


_pools: dict[str, ConnectionPool] = {}
_pool_lock = threading.Lock()


def _configure_connection(connection: psycopg.Connection[Any]) -> None:
    connection.execute("SET TIME ZONE 'UTC'")
    connection.commit()
    try:
        register_vector(connection)
    except psycopg.Error:
        # `db migrate` must be able to create vector before registration succeeds.
        connection.rollback()


def pool(database_url: str) -> ConnectionPool:
    if not database_url:
        raise DatabaseError("CHATREVIEW_DATABASE_URL is required")
    with _pool_lock:
        existing = _pools.get(database_url)
        if existing is None:
            existing = ConnectionPool(
                conninfo=database_url,
                min_size=0,
                max_size=8,
                timeout=30,
                kwargs={"autocommit": False, "row_factory": dict_row},
                configure=_configure_connection,
                open=True,
            )
            _pools[database_url] = existing
        return existing


def close_pools() -> None:
    """Close all process pools; primarily useful for test-schema teardown."""

    with _pool_lock:
        values = list(_pools.values())
        _pools.clear()
    for value in values:
        value.close()


@contextmanager
def database(database_url: str, *, read_only: bool = False) -> Iterator[Session]:
    """Borrow one pooled PostgreSQL transaction.

    Write contexts commit on successful exit and roll back on failure. Read contexts
    are transactionally read-only and always roll back, which also clears local search
    tuning such as pgvector's `hnsw.ef_search`.
    """

    with pool(database_url).connection() as connection:
        try:
            if read_only:
                connection.execute("SET TRANSACTION READ ONLY")
            session = Session(connection)
            yield session
            if read_only:
                connection.rollback()
            else:
                connection.commit()
        except BaseException:
            connection.rollback()
            raise


def migrate(database_url: str) -> list[str]:
    """Apply ordered, checksum-guarded SQL migrations under an advisory lock."""

    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise DatabaseError(f"no SQL migrations found in {MIGRATIONS_DIR}")
    applied_now: list[str] = []
    with pool(database_url).connection() as connection:
        try:
            connection.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chatreview_schema_migrations (
                    version integer PRIMARY KEY,
                    name text NOT NULL UNIQUE,
                    checksum text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
                )
                """
            )
            connection.commit()
            for path in files:
                version = int(path.name.split("_", 1)[0])
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                row = connection.execute(
                    "SELECT name, checksum FROM chatreview_schema_migrations WHERE version=%s",
                    (version,),
                ).fetchone()
                if row is not None:
                    exact_match = row["name"] == path.name and row["checksum"] == checksum
                    legacy_match = _legacy_migration_is_compatible(
                        connection,
                        version=version,
                        name=str(row["name"]),
                        checksum=str(row["checksum"]),
                    )
                    if not exact_match and not legacy_match:
                        raise DatabaseError(f"migration {version} differs from the already-applied migration")
                    continue
                connection.execute(sql)
                connection.execute(
                    """
                    INSERT INTO chatreview_schema_migrations(version, name, checksum)
                    VALUES (%s, %s, %s)
                    """,
                    (version, path.name, checksum),
                )
                connection.commit()
                applied_now.append(path.name)
            connection.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
            connection.commit()
        except BaseException:
            connection.rollback()
            try:
                connection.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
                connection.commit()
            except psycopg.Error:
                connection.rollback()
            raise
    # Connections created before CREATE EXTENSION need pgvector adapters registered.
    close_pools()
    return applied_now


def _legacy_migration_is_compatible(
    connection: psycopg.Connection[dict[str, Any]],
    *,
    version: int,
    name: str,
    checksum: str,
) -> bool:
    """Accept only a known predecessor fingerprint with its expected relation shape."""

    accepted = LEGACY_MIGRATION_CHECKSUMS.get((version, name), frozenset())
    if checksum not in accepted:
        return False
    signature = connection.execute(
        """
        SELECT to_regclass('machines') IS NOT NULL AS machines,
               to_regclass('sessions') IS NOT NULL AS sessions,
               to_regclass('rd_activities') IS NOT NULL AS legacy_activities,
               activity.relkind AS activities_kind,
               CASE
                   WHEN activity.relkind='v' THEN pg_get_viewdef(activity.oid)
                   ELSE NULL
               END AS activities_definition
        FROM (VALUES (1)) AS sentinel(value)
        LEFT JOIN pg_class activity ON activity.oid=to_regclass('activities')
        """
    ).fetchone()
    activities_compatible = bool(
        signature
        and (
            signature["activities_kind"] is None
            or (
                signature["activities_kind"] == "v"
                and "rd_activities" in (signature["activities_definition"] or "")
            )
        )
    )
    return bool(
        signature
        and signature["machines"]
        and signature["sessions"]
        and signature["legacy_activities"]
        and activities_compatible
    )


def doctor(database_url: str) -> DoctorReport:
    """Return extension, migration, and backup-relevant server facts."""

    with database(database_url, read_only=True) as connection:
        server = connection.execute(
            """
            SELECT current_setting('server_version') AS server_version,
                   current_database() AS database,
                   current_user AS user,
                   current_setting('wal_level') AS wal_level,
                   current_setting('archive_mode') AS archive_mode
            """
        ).fetchone()
        extensions = {
            row["extname"]: row["extversion"]
            for row in connection.execute(
                "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')"
            )
        }
        table = connection.execute("SELECT to_regclass('chatreview_schema_migrations') AS name").fetchone()
        migration_count = 0
        latest = None
        if table and table["name"]:
            migrations = connection.execute(
                "SELECT COUNT(*) AS count, MAX(name) AS latest FROM chatreview_schema_migrations"
            ).fetchone()
            migration_count = int(migrations["count"])
            latest = migrations["latest"]
    assert server is not None
    return DoctorReport(
        server_version=server["server_version"],
        database=server["database"],
        user=server["user"],
        extensions=extensions,
        migration_count=migration_count,
        latest_migration=latest,
        wal_level=server["wal_level"],
        archive_mode=server["archive_mode"],
    )


def suspend_search_indexes(database_url: str) -> list[str]:
    """Drop reproducible search indexes before an initial corpus bulk load."""

    return _change_search_indexes(database_url, rebuild=False)


def rebuild_search_indexes(database_url: str) -> list[str]:
    """Build every lexical, trigram, and vector index without blocking writers."""

    return _change_search_indexes(database_url, rebuild=True)


def rebuild_lexical_indexes(database_url: str) -> list[str]:
    """Build generated-text and trigram indexes after raw/projection bulk loading."""

    return _change_search_indexes(
        database_url,
        rebuild=True,
        names=[name for name in SEARCH_INDEXES if name != VECTOR_INDEX],
    )


def ensure_vector_index(database_url: str) -> list[str]:
    """Build the cosine HNSW index after an embedding run has populated vectors."""

    return _change_search_indexes(database_url, rebuild=True, names=[VECTOR_INDEX])


def _change_search_indexes(
    database_url: str,
    *,
    rebuild: bool,
    names: Iterable[str] | None = None,
) -> list[str]:
    changed: list[str] = []
    selected = list(names) if names is not None else list(SEARCH_INDEXES)
    with pool(database_url).connection() as connection:
        connection.rollback()
        connection.autocommit = True
        try:
            schema = connection.execute("SELECT current_schema()").fetchone()["current_schema"]
            for name in selected:
                statement = SEARCH_INDEXES[name]
                if rebuild:
                    connection.execute(statement)
                else:
                    connection.execute(
                        SQL("DROP INDEX CONCURRENTLY IF EXISTS {}.{}").format(
                            Identifier(schema), Identifier(name)
                        )
                    )
                changed.append(name)
        finally:
            connection.autocommit = False
    return changed


def advisory_key(identity: str) -> int:
    raw = hashlib.sha256(identity.encode()).digest()[:8]
    return int.from_bytes(raw, "big", signed=True)


def _qmark_to_psycopg(query: str) -> str:
    """Convert positional markers without touching quoted SQL text."""

    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(query):
        char = query[index]
        if quote:
            result.append("%%" if char == "%" else char)
            if char == quote:
                if index + 1 < len(query) and query[index + 1] == quote:
                    result.append(query[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"'}:
            quote = char
            result.append(char)
        elif char == "?":
            result.append("%s")
        elif char == "%":
            # psycopg scans percent markers even inside SQL string literals. The
            # qmark-facing interface therefore escapes SQL LIKE/modulo percents.
            result.append("%%")
        else:
            result.append(char)
        index += 1
    return "".join(result)
