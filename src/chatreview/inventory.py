from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from chatreview.config import Settings
from chatreview.db import database
from chatreview.providers.base import ProviderAdapter
from chatreview.types import SourceSpec


def build_inventory(
    settings: Settings,
    adapters: list[ProviderAdapter],
    *,
    deep: bool = False,
    sample_lines: int = 200,
) -> dict[str, Any]:
    discovered = [
        (adapter, source) for adapter in adapters for source in adapter.discover()
    ]
    by_provider: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"files": 0, "bytes": 0, "source_kinds": Counter(), "event_types": Counter()}
    )
    schema_shapes: Counter[str] = Counter()
    parse_errors: list[dict[str, Any]] = []
    min_mtime: float | None = None
    max_mtime: float | None = None
    for adapter, source in discovered:
        stat = source.path.stat()
        bucket = by_provider[source.provider]
        bucket["files"] += 1
        bucket["bytes"] += stat.st_size
        bucket["source_kinds"][source.source_kind] += 1
        min_mtime = stat.st_mtime if min_mtime is None else min(min_mtime, stat.st_mtime)
        max_mtime = stat.st_mtime if max_mtime is None else max(max_mtime, stat.st_mtime)
        _sample_source(
            adapter,
            source,
            bucket["event_types"],
            schema_shapes,
            parse_errors,
            limit=None if deep else sample_lines,
        )

    db_stats = _database_stats(settings.database_url)
    return {
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "mode": "deep" if deep else f"sampled-first-{sample_lines}-records-per-source",
        "total_files": len(discovered),
        "total_bytes": sum(item["bytes"] for item in by_provider.values()),
        "source_mtime_range": {
            "first": _iso_mtime(min_mtime),
            "last": _iso_mtime(max_mtime),
        },
        "providers": {
            provider: {
                "files": values["files"],
                "bytes": values["bytes"],
                "source_kinds": dict(values["source_kinds"].most_common()),
                "sampled_event_types": dict(values["event_types"].most_common()),
            }
            for provider, values in sorted(by_provider.items())
        },
        "sampled_schema_shapes": [
            {"shape": shape, "count": count} for shape, count in schema_shapes.most_common(100)
        ],
        "sample_parse_errors": parse_errors[:100],
        "database": db_stats,
    }


def write_inventory(settings: Settings, inventory: dict[str, Any]) -> tuple[Path, Path]:
    settings.ensure_output_dirs()
    json_path = settings.reports_dir / "corpus-inventory.json"
    markdown_path = settings.reports_dir / "corpus-inventory.md"
    json_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
    markdown_path.write_text(render_inventory_markdown(inventory))
    return json_path, markdown_path


def render_inventory_markdown(inventory: dict[str, Any]) -> str:
    lines = [
        "# Corpus Inventory",
        "",
        f"Generated: `{inventory['generated_at']}`  ",
        f"Mode: `{inventory['mode']}`",
        "",
        "## Sources",
        "",
        "| Provider | Files | Size | Kinds |",
        "|---|---:|---:|---|",
    ]
    for provider, values in inventory["providers"].items():
        kinds = ", ".join(f"{key}: {value}" for key, value in values["source_kinds"].items())
        lines.append(f"| {provider} | {values['files']:,} | {_human_bytes(values['bytes'])} | {kinds} |")
    lines.extend(
        [
            "",
            f"Total: **{inventory['total_files']:,} files**, **{_human_bytes(inventory['total_bytes'])}**.",
            "",
            "## Sampled event types",
            "",
        ]
    )
    for provider, values in inventory["providers"].items():
        lines.append(f"### {provider.title()}")
        lines.append("")
        for name, count in list(values["sampled_event_types"].items())[:30]:
            lines.append(f"- `{name}`: {count:,}")
        lines.append("")
    database = inventory.get("database")
    if database:
        lines.extend(["## Indexed database", ""])
        for key, value in database.items():
            lines.append(f"- `{key}`: {value:,}" if isinstance(value, int) else f"- `{key}`: {value}")
        lines.append("")
    errors = inventory.get("sample_parse_errors", [])
    lines.extend(["## Sample parse anomalies", ""])
    if errors:
        for item in errors[:20]:
            lines.append(f"- `{item['path']}:{item['line']}` — {item['error']}")
    else:
        lines.append("No parse anomalies were found in the inspected records.")
    lines.append("")
    return "\n".join(lines)


def _sample_source(
    adapter: ProviderAdapter,
    source: SourceSpec,
    event_types: Counter[str],
    schema_shapes: Counter[str],
    errors: list[dict[str, Any]],
    *,
    limit: int | None,
) -> None:
    if adapter.record_format(source) == "json-document":
        try:
            data = orjson.loads(source.path.read_bytes())
            parsed_records = adapter.parse_many(data, source)
            sampled_records = parsed_records if limit is None else parsed_records[:limit]
            for parsed in sampled_records:
                label = "/".join(
                    value
                    for value in (parsed.event_type, parsed.subtype or parsed.role)
                    if value
                )
                event_types[label] += 1
                fragment_kinds = ",".join(sorted({item.kind for item in parsed.fragments}))
                schema_shapes[f"{source.provider}:{parsed.event_type}:{fragment_kinds}"] += 1
        except Exception as exc:
            if len(errors) < 100:
                errors.append(
                    {
                        "path": str(source.path),
                        "line": 1,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        return
    with source.path.open("rb") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if limit is not None and line_no > limit:
                break
            try:
                data = orjson.loads(raw_line)
                if not isinstance(data, dict):
                    raise ValueError("top-level value is not an object")
                event_type = str(data.get("type") or "history-record")
                payload = data.get("payload")
                subtype = payload.get("type") if isinstance(payload, dict) else None
                message = data.get("message")
                message_role = message.get("role") if isinstance(message, dict) else None
                label = "/".join(str(value) for value in (event_type, subtype or message_role) if value)
                event_types[label] += 1
                shape = f"{source.provider}:{event_type}:" + ",".join(sorted(data.keys()))
                schema_shapes[shape] += 1
            except Exception as exc:
                if len(errors) < 100:
                    errors.append(
                        {
                            "path": str(source.path),
                            "line": line_no,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )


def _database_stats(database_url: str) -> dict[str, Any] | None:
    try:
        with database(database_url, read_only=True) as connection:
            stats = {
                "database_bytes": int(
                    connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
                )
            }
            for table in (
                "sources",
                "source_revisions",
                "raw_records",
                "sessions",
                "events",
                "contents",
                "text_units",
                "artifacts",
            ):
                stats[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            stats["parse_errors"] = int(
                connection.execute("SELECT COUNT(*) FROM events WHERE parse_error IS NOT NULL").fetchone()[0]
            )
            return stats
    except Exception as exc:
        return {"status": f"unavailable: {type(exc).__name__}: {exc}"}


def _iso_mtime(value: float | None) -> str | None:
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z") if value else None


def _human_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"
