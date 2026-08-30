from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import orjson

from chatreview.types import Artifact, ParsedRecord, SourceSpec, TextFragment

PATH_PATTERN = re.compile(
    r"(?<![\w])(?:/[^\s\x00\"'<>|]+|(?:\.?\.?/)?[\w@.-]+(?:/[\w@. -]+)+)(?=$|[\s,;:)'\"])",
)
FENCE_PATTERN = re.compile(r"```(?P<label>[^\n`]*)\n(?P<code>.*?)```", re.DOTALL)
ERROR_PATTERN = re.compile(
    r"(?im)^(?:.*(?:error|exception|traceback|failed|failure|panic|fatal|segmentation fault).*)$"
)
ACTIONABLE_ERROR_PATTERNS = (
    re.compile(r"^traceback \(most recent call last\):", re.I),
    re.compile(r"^(?:fatal|panic|segmentation fault)\b", re.I),
    re.compile(r"^(?:failed|failure)\b(?:\s|:)", re.I),
    re.compile(r"^(?:npm\s+err!|error\b|exception\b)(?:\s|:)", re.I),
    re.compile(r"^[A-Za-z_][\w.]*?(?:Error|Exception):(?:\s|$)"),
    re.compile(r"^(?:assertionerror|keyboardinterrupt)(?::|$)", re.I),
    re.compile(r"^.+?\s+failed:(?:\s|$)", re.I),
    re.compile(r"\b(?:command|process) (?:exited|failed)(?: with)? (?:code|status) [1-9]\d*\b", re.I),
    re.compile(r"(?:^|:\s)error(?:\[[^]]+\])?(?:\s+[A-Z]+\d+)?\s*:", re.I),
    re.compile(r"^FAILED(?:\s|$)", re.I),
)
BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/=_-]+$")


def stable_hash(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(value).hexdigest()


def json_text(value: Any) -> str:
    try:
        return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
    except (TypeError, ValueError):
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def sanitize_text(value: str) -> tuple[str, Artifact | None]:
    text = value.replace("\x00", "\N{SYMBOL FOR NULL}").strip()
    compact = "".join(text.split())
    if len(compact) >= 1024 and BASE64_PATTERN.fullmatch(compact):
        descriptor = f"[opaque encoded payload: {len(text)} characters]"
        return descriptor, Artifact("opaque-payload", descriptor, "encoded content")
    return text, None


def add_fragment(
    fragments: list[TextFragment],
    artifacts: list[Artifact],
    *,
    kind: str,
    value: Any,
    label: str | None = None,
    is_error: bool = False,
) -> None:
    if value is None:
        return
    text = value if isinstance(value, str) else json_text(value)
    text, opaque = sanitize_text(text)
    if not text:
        return
    fragments.append(TextFragment(kind=kind, text=text, label=label, is_error=is_error))
    if opaque:
        artifacts.append(opaque)


def extract_common_artifacts(
    fragments: Iterable[TextFragment], existing: Iterable[Artifact] = ()
) -> list[Artifact]:
    artifacts = list(existing)
    seen = {(item.kind, item.value) for item in artifacts}

    def append(kind: str, value: str, label: str | None = None) -> None:
        clean = value.strip()
        if not clean:
            return
        key = (kind, clean)
        if key in seen:
            return
        seen.add(key)
        artifacts.append(Artifact(kind, clean[:100_000], label))

    for fragment in fragments:
        text = fragment.text
        for match in FENCE_PATTERN.finditer(text):
            append("code-block", match.group("code"), match.group("label").strip() or None)
        for match in PATH_PATTERN.finditer(text):
            append("path", match.group(0).rstrip("."))
        for match in ERROR_PATTERN.finditer(text):
            append("error-signature", normalize_error(match.group(0)))
    return artifacts


def normalize_error(value: str) -> str:
    normalized = re.sub(r"0x[0-9a-fA-F]+", "<address>", value.strip())
    normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+-Z]+\b", "<timestamp>", normalized)
    normalized = re.sub(r"\b\d{5,}\b", "<number>", normalized)
    return re.sub(r"\s+", " ", normalized)[:4096]


def is_actionable_error_signature(value: Any) -> bool:
    """Separate executable/runtime failure evidence from prose that mentions failure."""
    if not isinstance(value, str):
        return False
    line = " ".join(value.strip().split())
    if not line or line.lower().startswith(("except ", "raise ", "catch ", "//", "# ")):
        return False
    return any(pattern.search(line) for pattern in ACTIONABLE_ERROR_PATTERNS)


def is_reportable_error_signature(value: Any) -> bool:
    """Keep specific retrospective candidates while suppressing generic/code markers."""
    if not is_actionable_error_signature(value):
        return False
    line = " ".join(str(value).strip().split())
    lower = line.lower()
    if lower in {
        "traceback (most recent call last):",
        "error:",
        "error: null,",
        "failed",
        "failure",
    }:
        return False
    if lower.startswith("exception:") and any(
        phrase in lower for phrase in ("you may ", "if working ", "the exception is ")
    ):
        return False
    if any(phrase in lower for phrase in (" not failed", " no error", " not an error")):
        return False
    if re.match(r"^[a-z][A-Za-z0-9_]*Error:", line):
        return False
    if lower.startswith("error:") and (
        line.endswith((",", ";"))
        or any(token in lower for token in (" instanceof ", " ?? ", "=>", "string | null"))
    ):
        return False
    return True


def source_kind(path: Path, *, provider: str) -> str:
    parts = set(path.parts)
    if path.name == "history.jsonl":
        return "history"
    if "subagents" in parts:
        return "subagent"
    if path.name == "journal.jsonl":
        return "workflow-journal"
    return "session"


class ProviderAdapter(ABC):
    name: str
    parser_version: int = 1

    @abstractmethod
    def discover(self) -> list[SourceSpec]:
        raise NotImplementedError

    @abstractmethod
    def parse(self, data: dict[str, Any], source: SourceSpec) -> ParsedRecord:
        raise NotImplementedError

    def record_format(self, source: SourceSpec) -> Literal["jsonl", "json-document"]:
        """Describe how one source file is divided into archived raw records."""

        del source
        return "jsonl"

    def parse_many(self, data: Any, source: SourceSpec) -> list[ParsedRecord]:
        """Project one archived raw record into one or more searchable events."""

        if not isinstance(data, dict):
            raise ValueError("top-level JSON value is not an object")
        return [self.parse(data, source)]

    def normalize_project(self, value: str | None) -> str | None:
        """Return a human-readable project identifier for derived session views."""
        return value
