"""Raw-payload retention policies.

The ingestion pipeline normally keeps the source JSONL line byte-for-byte so
that the archive can prove where a projected event came from.  This module is
the deliberately small policy seam for installations that want to omit
Codex's opaque reasoning payloads from that stored representation.  It is
pure: callers provide a decoded JSON value and receive a new value; the
source object is never modified.

Only dictionaries whose ``type`` is ``reasoning`` and which contain
``encrypted_content`` are redacted.  Readable ``summary`` values are left
alone.  Redaction keeps a marker, a SHA-256 digest, and the original UTF-8
byte count beside the marker, which makes a later audit possible without
putting the opaque payload back into the database.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

type RetentionMode = Literal["preserve", "redact"]

REDACTED_MARKER = "[redacted encrypted reasoning]"
_BASE64ISH = re.compile(r"^[A-Za-z0-9+/=_-]+$")
_SUMMARY_METADATA_KEYS = frozenset(
    {"type", "id", "role", "kind", "label", "name", "status", "index"}
)

type JsonValue = Any


@dataclass(frozen=True, slots=True)
class RetentionPreview:
    """Aggregate footprint information for a decoded raw payload.

    The preview intentionally contains no source text or encrypted content.
    ``encrypted_bytes`` is the size of the encoded value as UTF-8 bytes, not
    the size of a decoded cipher/plaintext value.
    """

    reasoning_records: int = 0
    encrypted_records: int = 0
    encrypted_bytes: int = 0
    readable_summary_records: int = 0
    readable_summary_bytes: int = 0

    @property
    def encoded_records(self) -> int:
        """Return the number of reasoning records carrying opaque content."""

        return self.encrypted_records

    @property
    def potential_bytes_saved(self) -> int:
        """Return the encoded bytes omitted by redacting these records."""

        return self.encrypted_bytes

    def plus(self, other: RetentionPreview) -> RetentionPreview:
        """Combine previews without exposing any payload content."""

        return RetentionPreview(
            reasoning_records=self.reasoning_records + other.reasoning_records,
            encrypted_records=self.encrypted_records + other.encrypted_records,
            encrypted_bytes=self.encrypted_bytes + other.encrypted_bytes,
            readable_summary_records=(
                self.readable_summary_records + other.readable_summary_records
            ),
            readable_summary_bytes=self.readable_summary_bytes + other.readable_summary_bytes,
        )


@dataclass(frozen=True, slots=True)
class RetentionResult:
    """A transformed value and its content-free footprint report."""

    value: JsonValue
    preview: RetentionPreview
    redacted_records: int = 0
    redacted_bytes: int = 0


class RawRetentionPolicy:
    """Apply a safe raw-payload retention mode to decoded JSON data.

    ``preserve`` is the default and returns a deep copy of the input.  The
    ``redact`` mode replaces only ``encrypted_content`` under reasoning
    records with :data:`REDACTED_MARKER` and adds deterministic audit fields:
    ``encrypted_content_sha256``, ``encrypted_content_byte_count``, and
    ``encrypted_content_redacted``.

    The policy is intentionally independent of PostgreSQL and provider
    adapters.  It can therefore be previewed in a setup UI before a caller
    wires it into the raw-payload persistence seam.
    """

    def __init__(self, mode: RetentionMode = "preserve") -> None:
        if mode not in {"preserve", "redact"}:
            raise ValueError("retention mode must be 'preserve' or 'redact'")
        self.mode = mode

    def preview(self, value: JsonValue) -> RetentionPreview:
        """Measure reasoning and opaque-content footprint without emitting it."""

        return _preview(value)

    def preview_many(self, values: Iterable[JsonValue]) -> RetentionPreview:
        """Aggregate previews for JSONL records without retaining their content."""

        result = RetentionPreview()
        for value in values:
            result = result.plus(self.preview(value))
        return result

    def transform(self, value: JsonValue) -> JsonValue:
        """Return a policy-transformed deep copy of ``value``."""

        return self.apply(value).value

    def apply(self, value: JsonValue) -> RetentionResult:
        """Transform ``value`` and return it with a content-free report."""

        preview = self.preview(value)
        if self.mode == "preserve":
            return RetentionResult(_clone(value), preview)
        transformed, redacted_records, redacted_bytes = _redact(value)
        return RetentionResult(
            transformed,
            preview,
            redacted_records=redacted_records,
            redacted_bytes=redacted_bytes,
        )


def _preview(value: JsonValue) -> RetentionPreview:
    if isinstance(value, Mapping):
        current = _preview_reasoning(value)
        for key, child in value.items():
            if key == "encrypted_content" and _is_reasoning_record(value):
                continue
            current = current.plus(_preview(child))
        return current
    if isinstance(value, (list, tuple)):
        result = RetentionPreview()
        for child in value:
            result = result.plus(_preview(child))
        return result
    return RetentionPreview()


def _preview_reasoning(value: Mapping[Any, Any]) -> RetentionPreview:
    if not _is_reasoning_record(value):
        return RetentionPreview()

    encrypted = value.get("encrypted_content")
    encrypted_bytes = _content_bytes(encrypted) if "encrypted_content" in value else b""
    summary_bytes = _readable_summary_bytes(value.get("summary"))
    return RetentionPreview(
        reasoning_records=1,
        encrypted_records=int("encrypted_content" in value),
        encrypted_bytes=len(encrypted_bytes),
        readable_summary_records=int(summary_bytes > 0),
        readable_summary_bytes=summary_bytes,
    )


def _redact(value: JsonValue) -> tuple[JsonValue, int, int]:
    if isinstance(value, Mapping):
        if _is_reasoning_record(value) and "encrypted_content" in value:
            encrypted_bytes = _content_bytes(value["encrypted_content"])
            result: dict[Any, Any] = {}
            nested_records = 0
            nested_bytes = 0
            for key, child in value.items():
                if key == "encrypted_content":
                    result[key] = REDACTED_MARKER
                else:
                    transformed, child_records, child_bytes = _redact(child)
                    result[key] = transformed
                    nested_records += child_records
                    nested_bytes += child_bytes
            result["encrypted_content_sha256"] = hashlib.sha256(encrypted_bytes).hexdigest()
            result["encrypted_content_byte_count"] = len(encrypted_bytes)
            result["encrypted_content_redacted"] = True
            return result, 1 + nested_records, len(encrypted_bytes) + nested_bytes

        result = {}
        records = 0
        bytes_redacted = 0
        for key, child in value.items():
            transformed, child_records, child_bytes = _redact(child)
            result[key] = transformed
            records += child_records
            bytes_redacted += child_bytes
        return result, records, bytes_redacted

    if isinstance(value, list):
        transformed_items = []
        records = 0
        bytes_redacted = 0
        for child in value:
            transformed, child_records, child_bytes = _redact(child)
            transformed_items.append(transformed)
            records += child_records
            bytes_redacted += child_bytes
        return transformed_items, records, bytes_redacted

    if isinstance(value, tuple):
        transformed, records, bytes_redacted = _redact(list(value))
        return tuple(transformed), records, bytes_redacted

    return value, 0, 0


def _is_reasoning_record(value: Mapping[Any, Any]) -> bool:
    item_type = value.get("type")
    return isinstance(item_type, str) and item_type.casefold() == "reasoning"


def _clone(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _clone(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_clone(child) for child in value]
    if isinstance(value, tuple):
        return tuple(_clone(child) for child in value)
    if isinstance(value, bytearray):
        return bytearray(value)
    if isinstance(value, memoryview):
        return memoryview(bytes(value))
    return value


def _content_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8", errors="surrogatepass")
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8", errors="surrogatepass"
        )
    except (TypeError, ValueError):
        return repr(value).encode("utf-8", errors="surrogatepass")


def _readable_summary_bytes(value: Any) -> int:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or _looks_encoded(stripped):
            return 0
        return len(stripped.encode("utf-8", errors="surrogatepass"))
    if isinstance(value, Mapping):
        return sum(
            _readable_summary_bytes(child)
            for key, child in value.items()
            if key not in _SUMMARY_METADATA_KEYS
        )
    if isinstance(value, (list, tuple)):
        return sum(_readable_summary_bytes(child) for child in value)
    return 0


def _looks_encoded(value: str) -> bool:
    compact = "".join(value.split())
    if len(compact) < 128 or not _BASE64ISH.fullmatch(compact):
        return False
    try:
        base64.b64decode(compact, altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        return False
    return True
