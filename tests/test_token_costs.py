"""Synthetic evidence tests for extraction, rebuilds, immutable prices and read-only reports."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from chatreview.api import create_app
from chatreview.db import database, migrate
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter
from chatreview.providers.claude import extract_token_usage
from chatreview.token_costs import PriceBook, build_token_costs, import_price_book, token_cost_report
from chatreview.token_usage import backfill_usage


def message(identifier="cost-1", timestamp="2026-07-18T23:30:00Z", model="synthetic-model"):
    return {
        "type": "assistant",
        "uuid": identifier,
        "sessionId": "synthetic-cost-session",
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": identifier}],
            "usage": {
                "input_tokens": 1_000_000,
                "output_tokens": 100_000,
                "cache_creation_input_tokens": 300,
                "cache_creation": {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 200},
                "cache_read_input_tokens": 1000,
            },
        },
    }


def price_book():
    return {
        "version": "synthetic-v1",
        "currency": "EUR",
        "source": "Synthetic fixture, not vendor prices",
        "confirmed_at": "2026-01-01",
        "prices": [
            {
                "model": "synthetic-model",
                "effective_from": "2026-01-01",
                "input_per_mtok": "2",
                "output_per_mtok": "4",
                "cache_write_5m_per_mtok": "3",
                "cache_write_1h_per_mtok": "5",
                "cache_read_per_mtok": "0.2",
            },
            {
                "model": "synthetic-model",
                "effective_from": "2026-07-19",
                "input_per_mtok": "3",
                "output_per_mtok": "4",
                "cache_write_5m_per_mtok": "3",
                "cache_write_1h_per_mtok": "5",
                "cache_read_per_mtok": "0.2",
            },
        ],
    }


def ingest(corpus, records):
    settings, _, path = corpus
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    Ingestor(settings, [ClaudeAdapter(settings.claude_root)]).run()
    return settings


def activate(settings, book=None):
    with database(settings.database_url) as connection:
        return import_price_book(connection, book or price_book())


def report(settings, **kwargs):
    with database(settings.database_url, read_only=True) as connection:
        return token_cost_report(connection, **kwargs)


def test_adapter_cache_ttls_and_invalid_counts():
    record = message()
    usage = extract_token_usage(record)
    assert (usage.cache_write_5m_tokens, usage.cache_write_1h_tokens) == (100, 200)
    del record["message"]["usage"]["cache_creation"]
    assert extract_token_usage(record).cache_write_5m_tokens == 300
    record["message"]["usage"]["input_tokens"] = -1
    assert extract_token_usage(record) is None
    record["message"]["usage"]["input_tokens"] = True
    assert extract_token_usage(record) is None
    del record["message"]["usage"]
    assert extract_token_usage(record) is None


def test_ingest_usage_dedup_rebuild_and_backfill(corpus):
    settings = ingest(corpus, [message(), message()])
    with database(settings.database_url) as connection:
        assert connection.execute("SELECT count(*) AS n FROM event_token_usage").fetchone()["n"] == 2
        connection.execute("DELETE FROM event_token_usage")
    # Only retained archive bytes are needed: source files are absent during backfill.
    corpus[2].unlink()
    first = backfill_usage(settings.database_url, batch_size=1)
    assert first["available"] == 2
    assert backfill_usage(settings.database_url)["processed"] == 0
    activate(settings)
    result = build_token_costs(settings.database_url)
    assert result["reused"] is False
    assert report(settings)["messages"] == 1
    assert build_token_costs(settings.database_url)["snapshot_id"] == result["snapshot_id"]
    assert build_token_costs(settings.database_url, force=True)["reused"] is True


def test_cost_math_effective_dates_timezone_and_unpriced(corpus, monkeypatch):
    monkeypatch.setenv("CHATREVIEW_TIMEZONE", "UTC")
    settings = ingest(corpus, [message(), message("unpriced", model="unknown-model")])
    activate(settings)
    build_token_costs(settings.database_url)
    old = report(settings)
    assert Decimal(old["priced_amount"]) == Decimal("2.4015")
    assert old["price_book"]["currency"] == "EUR"
    assert old["price_warning"] == "stale"
    assert old["unpriced_messages"] == 1
    assert old["unpriced_models"] == ["unknown-model"]
    monkeypatch.setenv("CHATREVIEW_TIMEZONE", "Australia/Perth")
    assert report(settings)["stale"] is True
    build_token_costs(settings.database_url)
    current = report(settings)
    assert current["stale"] is False
    assert Decimal(current["priced_amount"]) == Decimal("3.4015")
    assert current["daily"][0]["day"] == "2026-07-19"
    assert report(settings, model="unknown-model")["priced_amount"] == "0"
    assert report(settings, date_from=date(2026, 8, 1))["messages"] == 0


def test_prices_immutable_validated_and_reactivation_reuses_snapshot(corpus):
    settings = ingest(corpus, [message()])
    activate(settings)
    first = build_token_costs(settings.database_url)
    activate(settings)
    changed = price_book()
    changed["prices"][0]["input_per_mtok"] = "9"
    with pytest.raises(ValueError, match="different content"):
        activate(settings, changed)
    changed["version"] = "synthetic-v2"
    activate(settings, changed)
    stale = report(settings)
    assert stale["stale"]
    assert stale["price_book"]["version"] == "synthetic-v1"
    assert stale["active_price_book_version"] == "synthetic-v2"
    build_token_costs(settings.database_url)
    activate(settings)
    assert build_token_costs(settings.database_url)["snapshot_id"] == first["snapshot_id"]
    assert report(settings)["stale"] is False


@pytest.mark.parametrize("bad", ["-1", "NaN", "Infinity"])
def test_invalid_rates_rejected(bad):
    book = price_book()
    book["prices"][0]["input_per_mtok"] = bad
    with pytest.raises(ValueError):
        PriceBook.model_validate(book)


def test_duplicate_prices_rejected():
    book = price_book()
    book["prices"].append(copy.deepcopy(book["prices"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        PriceBook.model_validate(book)


def test_missing_usage_and_undated_usage_are_visible(corpus):
    missing = message("missing")
    del missing["message"]["usage"]
    settings = ingest(corpus, [missing, message("undated", timestamp=None)])
    activate(settings)
    build_token_costs(settings.database_url)
    result = report(settings)
    assert result["coverage"]["missing"] == 1
    assert result["coverage"]["available"] == 1
    assert result["unpriced_messages"] == 1
    assert result["priced_amount"] == "0"


def test_canonical_change_and_usage_correction_invalidate(corpus):
    settings = ingest(corpus, [message(), message("second")])
    activate(settings)
    build_token_costs(settings.database_url)
    with database(settings.database_url) as connection:
        rows = connection.execute("SELECT id FROM events WHERE role='assistant' ORDER BY id").fetchall()
        connection.execute(
            "UPDATE events SET canonical_event_id=? WHERE id=?", (rows[0]["id"], rows[1]["id"])
        )
    assert report(settings)["stale"]
    build_token_costs(settings.database_url)
    assert report(settings)["messages"] == 1
    with database(settings.database_url) as connection:
        connection.execute(
            "UPDATE event_token_usage SET usage_json=jsonb_set(usage_json,'{input_tokens}', '0')"
        )
    assert report(settings)["stale"]
    build_token_costs(settings.database_url, force=True)
    assert report(settings)["stale"] is False


def test_read_only_api_no_backfill_and_empty_archive(corpus):
    settings, _, _ = corpus
    client = TestClient(create_app(settings))
    assert client.get("/api/token-costs/status").json()["enabled"] is False
    settings = ingest(corpus, [message()])
    activate(settings)
    with database(settings.database_url) as connection:
        connection.execute("DELETE FROM event_token_usage")
    for view in ("status", "summary", "daily", "sessions"):
        response = client.get(f"/api/token-costs/{view}")
        assert response.status_code == 200
        assert response.json()["coverage"]["pending"] == 1
        assert response.json()["snapshot"] is None
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT count(*) AS n FROM event_token_usage").fetchone()["n"] == 0
        assert connection.execute("SELECT count(*) AS n FROM token_cost_snapshots").fetchone()["n"] == 0
    build_token_costs(settings.database_url)
    response = client.get("/api/token-costs/summary")
    assert response.json()["price_book"]["source"].startswith("Synthetic")
    assert response.json()["stale"] is False
    assert client.get("/api/token-costs/daily?group_by=month").json()["daily"][0]["day"] == "2026-07-01"
    assert client.get("/api/token-costs/summary?from=2026-08-01&to=2026-07-01").status_code == 422
    assert migrate(settings.database_url) == []


def test_concurrent_builds_publish_one_snapshot(corpus):
    settings = ingest(corpus, [message()])
    activate(settings)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: build_token_costs(settings.database_url), range(2)))
    assert results[0]["snapshot_id"] == results[1]["snapshot_id"]
    assert sum(not row["reused"] for row in results) == 1


def test_failed_build_preserves_previous_snapshot(corpus, monkeypatch):
    settings = ingest(corpus, [message()])
    activate(settings)
    old = build_token_costs(settings.database_url)
    book = price_book()
    book["version"] = "failing-build"
    activate(settings, book)

    def fail(*_args):
        raise RuntimeError("synthetic calculation failure")

    monkeypatch.setattr("chatreview.token_costs._price", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        build_token_costs(settings.database_url)
    result = report(settings)
    assert result["snapshot"]["id"] == old["snapshot_id"]
    assert result["stale"] is True
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT count(*) AS n FROM token_cost_snapshots").fetchone()["n"] == 1


def test_unattributed_and_changed_project_invalidate_without_mutating_snapshot(corpus):
    settings = ingest(corpus, [message()])
    activate(settings)
    with database(settings.database_url) as connection:
        connection.execute("UPDATE sessions SET project_id=NULL, project=NULL")
    build_token_costs(settings.database_url)
    original = report(settings, project=0)
    assert original["messages"] == 1
    assert original["sessions"][0]["project"] == "Unattributed"
    with database(settings.database_url) as connection:
        connection.execute("UPDATE sessions SET project='New synthetic attribution'")
    assert report(settings)["stale"] is True
    assert report(settings)["sessions"][0]["project"] == "Unattributed"
    build_token_costs(settings.database_url)
    assert report(settings)["sessions"][0]["project"] == "New synthetic attribution"


def test_operator_cli_import_build_status(corpus, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from chatreview.cli import app

    settings = ingest(corpus, [message()])
    monkeypatch.setattr("chatreview.cli._settings", lambda *_args: settings)
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(price_book()))
    runner = CliRunner()
    imported = runner.invoke(app, ["token-costs", "import-prices", str(path)])
    assert imported.exit_code == 0, imported.output
    built = runner.invoke(app, ["token-costs", "build"])
    assert built.exit_code == 0, built.output
    status = runner.invoke(app, ["token-costs", "status"])
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["stale"] is False


def test_response_blocks_count_usage_once_without_deleting_transcript(corpus):
    first = message("block-a")
    second = message("block-b", timestamp="2026-07-18T23:31:00Z")
    first["message"]["id"] = second["message"]["id"] = "synthetic-response-id"
    second["message"]["usage"]["output_tokens"] = 200_000
    settings = ingest(corpus, [first, second])
    activate(settings)
    build_token_costs(settings.database_url)
    result = report(settings)
    assert result["messages"] == 1
    assert result["coverage"]["duplicate"] == 1
    assert Decimal(result["priced_amount"]) == Decimal("2.8015")
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM events WHERE role='assistant' AND canonical_event_id IS NULL"
        ).fetchone()["n"] == 2


@pytest.mark.parametrize("cache", [0, False, "", [], "invalid"])
def test_malformed_cache_shapes_are_not_priced(cache):
    record = message()
    record["message"]["usage"]["cache_creation"] = cache
    assert extract_token_usage(record) is None


def test_archive_rebuild_reuses_stable_cost_snapshot(corpus):
    settings = ingest(corpus, [message(), message("second")])
    activate(settings)
    original = build_token_costs(settings.database_url)
    corpus[2].unlink()
    Ingestor(settings, [ClaudeAdapter(settings.claude_root)]).rebuild_from_archive()
    rebuilt = build_token_costs(settings.database_url)
    assert rebuilt["snapshot_id"] == original["snapshot_id"]
    assert rebuilt["reused"] is True
