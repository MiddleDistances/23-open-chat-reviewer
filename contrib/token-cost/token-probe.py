#!/usr/bin/env python3
"""Probe the archive for token-usage data hiding in the raw payloads.

Run from the repo directory:
    cd ~/open-chat-reviewer
    set -a; source .chatreview/archive.env; set +a
    uv run python ~/token-probe.py

Read-only. Touches nothing.
"""
import os
import sys

try:
    import psycopg
except ImportError:
    sys.exit("psycopg not found. Run this with 'uv run python' from ~/open-chat-reviewer")

URL = os.environ.get("CHATREVIEW_DATABASE_URL")
if not URL:
    sys.exit("CHATREVIEW_DATABASE_URL is not set. Source .chatreview/archive.env first.")

# Only decode payloads that are actually valid JSON; git sources and any
# truncated line would otherwise abort the whole query.
BASE = """
WITH payloads AS (
    SELECT e.id            AS event_id,
           e.timestamp     AS ts,
           e.role          AS role,
           s.provider      AS provider,
           s.project       AS project,
           s.external_id   AS session_ext,
           convert_from(rp.payload, 'UTF8')::jsonb AS j
    FROM events e
    JOIN raw_records  rr ON rr.id = e.raw_record_id
    JOIN raw_payloads rp ON rp.payload_hash = rr.payload_hash
    LEFT JOIN sessions s ON s.id = e.session_id
    WHERE e.canonical_event_id IS NULL
      AND pg_input_is_valid(convert_from(rp.payload, 'UTF8'), 'jsonb')
)
"""

QUERIES = [
    ("1. Assistant events, and how many carry a usage object", f"""
    {BASE}
    SELECT count(*) AS assistant_events,
           count(*) FILTER (WHERE j #> '{{message,usage}}' IS NOT NULL) AS with_usage
    FROM payloads
    WHERE role = 'assistant';
    """),

    ("2. Field names found inside usage", f"""
    {BASE}
    SELECT k AS usage_field, count(*) AS occurrences
    FROM payloads, LATERAL jsonb_object_keys(j #> '{{message,usage}}') AS k
    WHERE j #> '{{message,usage}}' IS NOT NULL
    GROUP BY k ORDER BY occurrences DESC;
    """),

    ("3. Models seen, with raw token totals", f"""
    {BASE}
    SELECT coalesce(j #>> '{{message,model}}', '(none)') AS model,
           count(*) AS messages,
           sum((j #>> '{{message,usage,input_tokens}}')::bigint)               AS input_tokens,
           sum((j #>> '{{message,usage,output_tokens}}')::bigint)              AS output_tokens,
           sum((j #>> '{{message,usage,cache_creation_input_tokens}}')::bigint) AS cache_write,
           sum((j #>> '{{message,usage,cache_read_input_tokens}}')::bigint)     AS cache_read
    FROM payloads
    WHERE j #> '{{message,usage}}' IS NOT NULL
    GROUP BY 1 ORDER BY messages DESC;
    """),

    ("4. Coverage by month (Perth time)", f"""
    {BASE}
    SELECT to_char(ts AT TIME ZONE 'Australia/Perth', 'YYYY-MM') AS month,
           count(*) AS messages_with_usage,
           sum((j #>> '{{message,usage,output_tokens}}')::bigint) AS output_tokens
    FROM payloads
    WHERE j #> '{{message,usage}}' IS NOT NULL AND ts IS NOT NULL
    GROUP BY 1 ORDER BY 1;
    """),

    ("5. One raw usage object, verbatim", f"""
    {BASE}
    SELECT jsonb_pretty(j #> '{{message,usage}}') AS sample
    FROM payloads
    WHERE j #> '{{message,usage}}' IS NOT NULL
    LIMIT 1;
    """),
]


def main() -> None:
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        for title, sql in QUERIES:
            print("\n" + "=" * 68)
            print(title)
            print("=" * 68)
            try:
                cur.execute(sql)
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                print(f"  query failed: {type(exc).__name__}: {exc}")
                continue
            rows = cur.fetchall()
            if not rows:
                print("  (no rows)")
                continue
            headers = [d.name for d in cur.description]
            if len(headers) == 1 and headers[0] == "sample":
                print(rows[0][0])
                continue
            widths = [
                max(len(h), max((len(str(r[i])) for r in rows), default=0))
                for i, h in enumerate(headers)
            ]
            print("  " + " | ".join(h.ljust(w) for h, w in zip(headers, widths, strict=False)))
            print("  " + "-+-".join("-" * w for w in widths))
            for r in rows[:40]:
                print("  " + " | ".join(str(v).ljust(w) for v, w in zip(r, widths, strict=False)))
            if len(rows) > 40:
                print(f"  ... {len(rows) - 40} more rows")


if __name__ == "__main__":
    main()
