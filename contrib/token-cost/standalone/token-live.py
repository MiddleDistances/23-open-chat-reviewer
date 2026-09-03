#!/usr/bin/env python3
"""Live token cost report served over HTTP.

Extracts usage figures out of the raw payloads once into token_report.usage,
then keeps that table current incrementally. Each page load tops the table up
and re-aggregates, so refreshing shows genuinely current numbers.

The table lives in its own PostgreSQL schema, so nothing the upstream project
migrates can collide with it. Read-only against every upstream table.

    CHATREVIEW_DATABASE_URL=... python token-live.py [--port 8766]
"""
from __future__ import annotations

import argparse
import contextlib
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg


# token-report.py has a hyphen in its name, so it cannot be imported normally.
# Load it by path; it supplies the renderer, the price table and the timezone.
def _load_renderer():
    import importlib.util
    for candidate in (Path.home() / "token-report.py", Path(__file__).resolve().parent / "token-report.py"):
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("token_report", candidate)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    sys.exit("token-report.py not found in your home directory; it supplies the renderer.")


tr = _load_renderer()


CACHE_SECONDS = 15                     # collapses rapid refreshes; still effectively live

DDL = """
CREATE SCHEMA IF NOT EXISTS token_report;
CREATE TABLE IF NOT EXISTS token_report.usage (
    event_id  bigint PRIMARY KEY,
    model     text   NOT NULL,
    inp       bigint NOT NULL DEFAULT 0,
    out       bigint NOT NULL DEFAULT 0,
    cw5m      bigint NOT NULL DEFAULT 0,
    cw1h      bigint NOT NULL DEFAULT 0,
    cw_total  bigint NOT NULL DEFAULT 0,
    read      bigint NOT NULL DEFAULT 0
);
"""

# Pull only events newer than what we already hold. The first run backfills
# everything; every run after that is usually a handful of rows.
BACKFILL = """
INSERT INTO token_report.usage (event_id, model, inp, out, cw5m, cw1h, cw_total, read)
SELECT e.id,
       coalesce(j #>> '{message,model}', '(unknown)'),
       coalesce((j #>> '{message,usage,input_tokens}')::bigint, 0),
       coalesce((j #>> '{message,usage,output_tokens}')::bigint, 0),
       coalesce((j #>> '{message,usage,cache_creation,ephemeral_5m_input_tokens}')::bigint, 0),
       coalesce((j #>> '{message,usage,cache_creation,ephemeral_1h_input_tokens}')::bigint, 0),
       coalesce((j #>> '{message,usage,cache_creation_input_tokens}')::bigint, 0),
       coalesce((j #>> '{message,usage,cache_read_input_tokens}')::bigint, 0)
FROM (
    SELECT e.id, convert_from(rp.payload, 'UTF8')::jsonb AS j
    FROM events e
    JOIN raw_records  rr ON rr.id = e.raw_record_id
    JOIN raw_payloads rp ON rp.payload_hash = rr.payload_hash
    WHERE e.id > %s
      AND e.role = 'assistant'
      AND pg_input_is_valid(convert_from(rp.payload, 'UTF8'), 'jsonb')
) AS e
WHERE j #> '{message,usage}' IS NOT NULL
ON CONFLICT (event_id) DO NOTHING
"""

# canonical_event_id is only set later, during refresh, so duplicates are
# filtered here at read time rather than trusted at write time.
AGGREGATE = """
SELECT (ev.timestamp AT TIME ZONE %s)::date               AS day,
       u.model                                            AS model,
       coalesce(nullif(s.project, ''), '(unattributed)')   AS project,
       coalesce(s.external_id, '(none)')                   AS session_ext,
       count(*)        AS messages,
       sum(u.inp)      AS inp,
       sum(u.out)      AS out,
       sum(u.cw5m)     AS cw5m,
       sum(u.cw1h)     AS cw1h,
       sum(u.cw_total) AS cw_total,
       sum(u.read)     AS read
FROM token_report.usage u
JOIN events ev ON ev.id = u.event_id
LEFT JOIN sessions s ON s.id = ev.session_id
WHERE ev.canonical_event_id IS NULL
  AND ev.timestamp IS NOT NULL
GROUP BY 1, 2, 3, 4
ORDER BY 1
"""

_lock = threading.Lock()
_cache: dict[str, object] = {"at": 0.0, "html": None}


def refresh_html(url: str) -> str:
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("SELECT coalesce(max(event_id), 0) FROM token_report.usage")
        watermark = cur.fetchone()[0]
        cur.execute(BACKFILL, (watermark,))
        added = cur.rowcount
        conn.commit()
        cur.execute(AGGREGATE, (tr.TZ,))
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]
    print(f"[{time.strftime('%H:%M:%S')}] +{added} new events, {len(rows):,} aggregate rows", flush=True)
    return tr.build(rows)


def get_html(url: str) -> str:
    with _lock:
        age = time.time() - float(_cache["at"])
        if _cache["html"] is None or age > CACHE_SECONDS:
            _cache["html"] = refresh_html(url)
            _cache["at"] = time.time()
        return str(_cache["html"])


class Handler(BaseHTTPRequestHandler):
    server_version = "token-live"
    url = ""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] not in ("/", "/index.html", "/token-report.html"):
            self.send_error(404, "Nothing here. The report is at /")
            return
        try:
            body = get_html(self.url).encode("utf-8")
        except Exception:
            traceback.print_exc()
            msg = (
                b"<!doctype html><meta charset=utf-8><title>Report failed</title>"
                b"<body style='font:16px system-ui;padding:40px;max-width:60ch'>"
                b"<h1>The report could not be built</h1>"
                b"<p>The database may be starting up, or the archive may hold no usage data yet. "
                b"The exact error is in the service log:</p>"
                b"<pre>journalctl --user -u token-live -n 40</pre></body>"
            )
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # quieter than the default
        return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()

    url = os.environ.get("CHATREVIEW_DATABASE_URL")
    if not url:
        sys.exit("CHATREVIEW_DATABASE_URL is not set.")
    Handler.url = url

    print("Warming the cache (the first build backfills the table, so give it a minute)...", flush=True)
    try:
        get_html(url)
    except Exception:
        traceback.print_exc()
        print("Warm-up failed; the server will retry on the first request.", flush=True)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Live token report on http://{args.host}:{args.port}", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        srv.serve_forever()


if __name__ == "__main__":
    main()
