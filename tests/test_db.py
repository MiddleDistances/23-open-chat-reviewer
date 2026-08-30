from __future__ import annotations

from chatreview.db import database, rebuild_search_indexes, suspend_search_indexes


def test_reproducible_search_indexes_can_be_suspended_and_rebuilt(
    postgres_database_url: str,
) -> None:
    suspended = suspend_search_indexes(postgres_database_url)
    assert "contents_search_idx" in suspended
    with database(postgres_database_url, read_only=True) as connection:
        assert connection.execute(
            "SELECT to_regclass(current_schema() || '.contents_search_idx') AS name"
        ).fetchone()["name"] is None

    rebuilt = rebuild_search_indexes(postgres_database_url)
    assert set(rebuilt) == set(suspended)
    with database(postgres_database_url, read_only=True) as connection:
        assert connection.execute(
            "SELECT to_regclass(current_schema() || '.contents_search_idx') AS name"
        ).fetchone()["name"] is not None
