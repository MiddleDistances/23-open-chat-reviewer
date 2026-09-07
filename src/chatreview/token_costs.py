"""Versioned operator pricing and deterministic, read-only cost reporting.

Price books carry their own currency. Amounts are API-equivalent estimates, never
subscription invoices. Missing rates remain unpriced rather than becoming zero.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from chatreview.db import Session, advisory_key, database
from chatreview.providers.claude import TOKEN_USAGE_VERSION
from chatreview.timezones import local_zone
from chatreview.token_usage import backfill_usage

ALGORITHM_VERSION = 1
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_write_5m_tokens",
    "cache_write_1h_tokens",
    "cache_read_tokens",
)
Rate = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]


class TokenPrice(BaseModel):
    """An exact provider/model/tier rate, effective from a local calendar date."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    provider: str = Field(default="claude", min_length=1)
    model: str = Field(min_length=1)
    service_tier: str | None = None
    effective_from: date
    input_per_mtok: Rate
    output_per_mtok: Rate
    cache_write_5m_per_mtok: Rate
    cache_write_1h_per_mtok: Rate
    cache_read_per_mtok: Rate


class PriceBook(BaseModel):
    """Validated, immutable pricing identity imported explicitly by an operator."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: str = Field(min_length=1, max_length=120)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source: str = Field(min_length=1)
    confirmed_at: date | None = None
    prices: list[TokenPrice]

    @field_validator("confirmed_at")
    @classmethod
    def confirmed_not_future(cls, value: date | None) -> date | None:
        """A future date cannot truthfully represent completed price confirmation."""
        if value and value > datetime.now(local_zone()).date():
            raise ValueError("confirmed_at cannot be in the future")
        return value

    @model_validator(mode="after")
    def unique_rates(self) -> PriceBook:
        """Reject ambiguous prices for the same provider, model, tier and date."""
        keys = [(p.provider, p.model, p.service_tier, p.effective_from) for p in self.prices]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate effective price for provider/model/tier")
        return self


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def import_price_book(connection: Session, data: dict[str, Any]) -> dict[str, Any]:
    """Import and activate a price book; an existing version can never change content."""
    book = PriceBook.model_validate(data)
    normalized = book.model_dump(mode="json")
    normalized["prices"] = sorted(normalized["prices"], key=_json)
    digest = _hash(normalized)
    connection.execute("SELECT pg_advisory_xact_lock(?)", (advisory_key("token-price-import"),))
    existing = connection.execute(
        "SELECT * FROM token_price_books WHERE version=?", (book.version,)
    ).fetchone()
    if existing and existing["content_hash"] != digest:
        raise ValueError("price book version already exists with different content; use a new version")
    row = (
        existing
        or connection.execute(
            """INSERT INTO token_price_books(version,content_hash,book_json) VALUES (?,?,?::jsonb)
        RETURNING *""",
            (book.version, digest, _json(normalized)),
        ).fetchone()
    )
    connection.execute(
        """INSERT INTO token_cost_settings(id,price_book_id) VALUES (1,?)
        ON CONFLICT(id) DO UPDATE SET price_book_id=excluded.price_book_id""",
        (row["id"],),
    )
    return {"id": row["id"], "version": book.version, "content_hash": digest}


def _active_book(connection: Session) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT b.* FROM token_price_books b JOIN token_cost_settings s ON s.price_book_id=b.id
        WHERE s.id=1""",
    ).fetchone()
    return dict(row) if row else None


def _collect(connection: Session, zone: str) -> list[dict[str, Any]]:
    """Group canonical messages once, preserving missing usage and snapshot dimensions."""
    return [
        dict(row)
        for row in connection.execute(
            """SELECT src.provider, e.session_id, coalesce(s.title,s.external_id,'Unattributed') AS session,
        s.project_id, coalesce(p.name,s.project,'Unattributed') AS project,
        (e.timestamp AT TIME ZONE ?)::date AS day,
        u.usage_json->>'model' AS model, u.usage_json->>'service_tier' AS service_tier,
        CASE WHEN src.provider<>'claude' THEN 'unsupported'
             WHEN u.event_id IS NULL OR u.extraction_version<>? THEN 'pending'
             ELSE u.status END AS usage_status,
        count(*) AS messages,
        md5(string_agg(e.id::text || ':' || e.content_hash, ',' ORDER BY e.id)) AS evidence_hash,
        sum(coalesce((u.usage_json->>'input_tokens')::numeric,0)) AS input_tokens,
        sum(coalesce((u.usage_json->>'output_tokens')::numeric,0)) AS output_tokens,
        sum(coalesce((u.usage_json->>'cache_write_5m_tokens')::numeric,0)) AS cache_write_5m_tokens,
        sum(coalesce((u.usage_json->>'cache_write_1h_tokens')::numeric,0)) AS cache_write_1h_tokens,
        sum(coalesce((u.usage_json->>'cache_read_tokens')::numeric,0)) AS cache_read_tokens
        FROM events e JOIN sources src ON src.id=e.source_id
        LEFT JOIN sessions s ON s.id=e.session_id LEFT JOIN projects p ON p.id=s.project_id
        LEFT JOIN event_token_usage u ON u.event_id=e.id
        WHERE e.canonical_event_id IS NULL AND e.role='assistant'
        GROUP BY 1,2,3,4,5,6,7,8,9 ORDER BY 1,2,3,4,5,6,7,8,9""",
            (zone, TOKEN_USAGE_VERSION),
        ).fetchall()
    ]


def _coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    result = dict.fromkeys(("total", "available", "missing", "unavailable", "unsupported", "pending"), 0)
    for row in rows:
        result["total"] += row["messages"]
        result[row["usage_status"]] += row["messages"]
    return result


def _fingerprint(rows: list[dict[str, Any]]) -> str:
    return _hash(rows)


def _price(row: dict[str, Any], prices: list[TokenPrice]) -> str | None:
    if not row["day"] or row["usage_status"] != "available":
        return None
    candidates = [
        p
        for p in prices
        if (p.provider, p.model, p.service_tier) == (row["provider"], row["model"], row["service_tier"])
        and p.effective_from <= row["day"]
    ]
    if not candidates:
        return None
    price = max(candidates, key=lambda p: p.effective_from)
    return str(
        sum(
            Decimal(row[field]) * getattr(price, field.removesuffix("_tokens") + "_per_mtok")
            for field in TOKEN_FIELDS
        )
        / 1_000_000
    )


def build_token_costs(database_url: str, *, force: bool = False) -> dict[str, Any]:
    """Atomically publish or reuse a snapshot after an explicitly enabled price import."""
    with database(database_url, read_only=True) as connection:
        if not _active_book(connection):
            return {"enabled": False}
    backfill = backfill_usage(database_url, force=force)
    with database(database_url) as connection, connection.advisory_lock("token-cost-build"):
        # Acquire the lock before opening the consistent read snapshot.
        connection.commit()
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        active = _active_book(connection)
        book = PriceBook.model_validate(active["book_json"])
        zone = str(local_zone())
        rows = _collect(connection, zone)
        fingerprint = _fingerprint(rows)
        key = _hash([ALGORITHM_VERSION, TOKEN_USAGE_VERSION, fingerprint, active["content_hash"], zone])
        existing = connection.execute(
            "SELECT id FROM token_cost_snapshots WHERE snapshot_key=?", (key,)
        ).fetchone()
        if existing:
            return {"enabled": True, "snapshot_id": existing["id"], "reused": True, "backfill": backfill}
        snapshot = connection.execute(
            """INSERT INTO token_cost_snapshots(snapshot_key,corpus_fingerprint,price_book_id,
            algorithm_version,timezone,coverage_json) VALUES (?,?,?,?,?,?::jsonb) RETURNING id""",
            (key, fingerprint, active["id"], ALGORITHM_VERSION, zone, _json(_coverage(rows))),
        ).fetchone()
        available = [row for row in rows if row["usage_status"] == "available"]
        connection.executemany(
            "INSERT INTO token_cost_rows(snapshot_id,row_index,row_json) VALUES (?,?,?::jsonb)",
            [
                (snapshot["id"], i, _json({**row, "cost_amount": _price(row, book.prices)}))
                for i, row in enumerate(available)
            ],
        )
        connection.commit()
        return {"enabled": True, "snapshot_id": snapshot["id"], "reused": False, "backfill": backfill}


def _state(connection: Session) -> dict[str, Any]:
    """Read freshness without building, backfilling, or mutating archive state."""
    active = _active_book(connection)
    zone = str(local_zone())
    rows = _collect(connection, zone)
    fingerprint = _fingerprint(rows)
    expected = (
        _hash([ALGORITHM_VERSION, TOKEN_USAGE_VERSION, fingerprint, active["content_hash"], zone])
        if active
        else None
    )
    snapshot = connection.execute(
        """SELECT * FROM token_cost_snapshots WHERE snapshot_key=?
        OR id=(SELECT max(id) FROM token_cost_snapshots)
        ORDER BY (snapshot_key=?) DESC, id DESC LIMIT 1""",
        (expected, expected),
    ).fetchone()
    book_row = (
        connection.execute(
            "SELECT * FROM token_price_books WHERE id=?", (snapshot["price_book_id"],)
        ).fetchone()
        if snapshot
        else active
    )
    book = book_row["book_json"] if book_row else None
    confirmed = date.fromisoformat(book["confirmed_at"]) if book and book["confirmed_at"] else None
    age = (datetime.now(local_zone()).date() - confirmed).days if confirmed else None
    return {
        "enabled": active is not None,
        "snapshot": dict(snapshot) if snapshot else None,
        "stale": snapshot is None or snapshot["snapshot_key"] != expected,
        "coverage": _coverage(rows),
        "price_book": (
            {k: book[k] for k in ("version", "currency", "source", "confirmed_at")} if book else None
        ),
        "active_price_book_version": active["version"] if active else None,
        "price_age_days": age,
        "price_warning": "unknown" if age is None else "stale" if age > 90 else None,
        "timezone": snapshot["timezone"] if snapshot else zone,
    }


def token_cost_report(
    connection: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    project: int | None = None,
    model: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return filtered snapshot totals, daily rows and session costs in book currency."""
    if date_from and date_to and date_from > date_to:
        raise ValueError("from must be on or before to")
    state = _state(connection)
    snapshot = state["snapshot"]
    rows = (
        [
            row["row_json"]
            for row in connection.execute(
                "SELECT row_json FROM token_cost_rows WHERE snapshot_id=? ORDER BY row_index",
                (snapshot["id"],),
            ).fetchall()
        ]
        if snapshot
        else []
    )
    projects = sorted({(r["project_id"] or 0, r["project"]) for r in rows}, key=lambda p: (p[1], p[0]))
    rows = [
        r
        for r in rows
        if (project is None or (r["project_id"] or 0) == project)
        and (not model or r["model"] == model)
        and (not date_from or (r["day"] and r["day"] >= date_from.isoformat()))
        and (not date_to or (r["day"] and r["day"] <= date_to.isoformat()))
    ]

    def aggregate(key: str) -> list[dict[str, Any]]:
        grouped: dict[Any, dict[str, Any]] = {}
        for row in rows:
            value = row[key]
            group = grouped.setdefault(
                value,
                {key: value, "messages": 0, "tokens": 0, "priced_amount": Decimal(0), "unpriced_messages": 0},
            )
            group["messages"] += row["messages"]
            group["tokens"] += sum(int(row[field]) for field in TOKEN_FIELDS)
            if row["cost_amount"] is None:
                group["unpriced_messages"] += row["messages"]
            else:
                group["priced_amount"] += Decimal(row["cost_amount"])
            if key == "session_id":
                group.update(session=row["session"], project=row["project"])
        return [{**g, "priced_amount": str(g["priced_amount"])} for g in grouped.values()]

    unpriced = sorted({r["model"] for r in rows if r["cost_amount"] is None})
    sessions = sorted(aggregate("session_id"), key=lambda r: Decimal(r["priced_amount"]), reverse=True)
    return {
        **state,
        "priced_amount": str(
            sum((Decimal(r["cost_amount"]) for r in rows if r["cost_amount"] is not None), Decimal(0))
        ),
        "tokens": sum(sum(int(r[f]) for f in TOKEN_FIELDS) for r in rows),
        "messages": sum(r["messages"] for r in rows),
        "unpriced_messages": sum(r["messages"] for r in rows if r["cost_amount"] is None),
        "unpriced_models": unpriced,
        "daily": sorted(aggregate("day"), key=lambda r: r["day"] or ""),
        "models": aggregate("model"),
        "sessions": sessions[:limit],
        "projects": [{"id": identifier, "name": name} for identifier, name in projects],
    }


def group_days(rows: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    """Combine daily totals into calendar weeks or months without repricing them."""
    from datetime import timedelta

    if group_by == "day":
        return rows
    grouped: dict[str | None, dict[str, Any]] = {}
    for row in rows:
        day = date.fromisoformat(row["day"]) if row["day"] else None
        start = None
        if day:
            start = day - timedelta(days=day.weekday()) if group_by == "week" else day.replace(day=1)
        key = str(start) if start else None
        target = grouped.setdefault(
            key, {"day": key, "messages": 0, "tokens": 0, "unpriced_messages": 0, "priced_amount": Decimal(0)}
        )
        for field in ("messages", "tokens", "unpriced_messages"):
            target[field] += row[field]
        target["priced_amount"] += Decimal(row["priced_amount"])
    return [{**row, "priced_amount": str(row["priced_amount"])} for row in grouped.values()]
