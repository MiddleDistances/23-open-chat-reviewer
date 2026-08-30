from __future__ import annotations

import hashlib
import json

import pytest

from chatreview.retention import REDACTED_MARKER, RawRetentionPolicy


def _reasoning(content: str, summary: str = "A readable summary") -> dict[str, object]:
    return {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": summary}],
        "encrypted_content": content,
    }


def test_preview_reports_opaque_bytes_and_readable_summary_without_content() -> None:
    value = {
        "type": "response_item",
        "payload": _reasoning("sealed reasoning", "A readable summary"),
    }

    preview = RawRetentionPolicy().preview(value)

    assert preview.reasoning_records == 1
    assert preview.encrypted_records == 1
    assert preview.encoded_records == 1
    assert preview.encrypted_bytes == len(b"sealed reasoning")
    assert preview.potential_bytes_saved == preview.encrypted_bytes
    assert preview.readable_summary_records == 1
    assert preview.readable_summary_bytes == len(b"A readable summary")
    assert "sealed reasoning" not in repr(preview)
    assert "A readable summary" not in repr(preview)


def test_preview_many_aggregates_nested_jsonl_records() -> None:
    values = [
        _reasoning("one", "first"),
        {
            "items": [
                _reasoning("two", "second"),
                {"type": "message", "encrypted_content": "not reasoning"},
            ]
        },
    ]

    preview = RawRetentionPolicy().preview_many(values)

    assert preview.reasoning_records == 2
    assert preview.encrypted_records == 2
    assert preview.encrypted_bytes == len("one") + len("two")
    assert preview.readable_summary_records == 2
    assert preview.readable_summary_bytes == len("first") + len("second")


def test_preserve_is_default_and_returns_a_deep_copy() -> None:
    value = {"payload": _reasoning("keep this", "keep summary"), "nested": [{"ok": True}]}

    result = RawRetentionPolicy().apply(value)

    assert result.value == value
    assert result.value is not value
    assert result.value["payload"] is not value["payload"]
    assert result.value["nested"] is not value["nested"]
    assert result.redacted_records == 0
    assert result.redacted_bytes == 0

    result.value["payload"]["summary"][0]["text"] = "changed copy"
    assert value["payload"]["summary"][0]["text"] == "keep summary"


def test_redact_replaces_only_encrypted_content_and_keeps_summary() -> None:
    secret = "gAAAAA opaque reasoning payload"
    value = {"payload": _reasoning(secret, "A useful readable summary")}

    result = RawRetentionPolicy("redact").apply(value)
    transformed = result.value["payload"]

    assert transformed["encrypted_content"] == REDACTED_MARKER
    assert transformed["encrypted_content_sha256"] == hashlib.sha256(secret.encode()).hexdigest()
    assert transformed["encrypted_content_byte_count"] == len(secret.encode())
    assert transformed["encrypted_content_redacted"] is True
    assert transformed["summary"] == value["payload"]["summary"]
    assert secret not in json.dumps(transformed)
    assert value["payload"]["encrypted_content"] == secret
    assert result.preview.encrypted_records == 1
    assert result.redacted_records == 1
    assert result.redacted_bytes == len(secret.encode())


def test_redact_handles_nested_records_and_does_not_touch_other_types() -> None:
    first = "first payload"
    second = "second payload"
    value = {
        "events": [
            _reasoning(first),
            {"payload": {"TYPE": "reasoning", "encrypted_content": second}},
            {"type": "message", "encrypted_content": "leave this field alone"},
        ]
    }

    transformed = RawRetentionPolicy("redact").transform(value)

    assert transformed["events"][0]["encrypted_content"] == REDACTED_MARKER
    assert transformed["events"][1]["payload"]["encrypted_content"] == second
    assert transformed["events"][2]["encrypted_content"] == "leave this field alone"


def test_redact_hashes_non_string_json_values_deterministically() -> None:
    value = {"type": "reasoning", "encrypted_content": {"b": 2, "a": 1}, "summary": []}
    expected = json.dumps({"b": 2, "a": 1}, sort_keys=True, separators=(",", ":")).encode()

    result = RawRetentionPolicy("redact").apply(value)

    assert result.value["encrypted_content"] == REDACTED_MARKER
    assert result.value["encrypted_content_sha256"] == hashlib.sha256(expected).hexdigest()
    assert result.value["encrypted_content_byte_count"] == len(expected)


def test_encoded_summary_is_not_counted_as_readable_text() -> None:
    value = _reasoning("cipher", "A" * 192)

    preview = RawRetentionPolicy().preview(value)

    assert preview.readable_summary_records == 0
    assert preview.readable_summary_bytes == 0


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="preserve.*redact"):
        RawRetentionPolicy("drop")  # type: ignore[arg-type]
