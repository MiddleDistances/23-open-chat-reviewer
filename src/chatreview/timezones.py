"""Shared timezone resolution for deterministic archive projections."""

import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def local_zone(value: str | None = None) -> ZoneInfo:
    """Resolve the configured IANA zone; reject invalid configuration explicitly."""
    name = (value or os.environ.get("CHATREVIEW_TIMEZONE") or os.environ.get("TZ") or "UTC").strip()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown CHATREVIEW_TIMEZONE: {name}") from exc
