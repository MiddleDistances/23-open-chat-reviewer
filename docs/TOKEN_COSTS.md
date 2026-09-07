# Token-cost estimates

Token costing is optional. It reports API-equivalent estimates from recorded usage;
it does not reconstruct subscription payments or invoices. Claude usage is supported
first. Codex and Gemini assistant messages are explicitly reported as unsupported
coverage until their distinct usage semantics have adapter tests.

The design follows Oscar Love's proposal in [PR #9](https://github.com/MiddleDistances/23-open-chat-reviewer/pull/9#issuecomment-5535388133)
and [issue #24](https://github.com/MiddleDistances/23-open-chat-reviewer/issues/24):
provider extraction, versioned pricing, rebuildable reports, read-only API and native UI.

## Enable and operate

Run from the checkout with its repository environment and configured database. Source
roots remain read-only. Keep live operator configuration under ignored `.chatreview/`.

```bash
uv sync
uv run open-chat-reviewer db doctor
uv run open-chat-reviewer db migrate
cp config/token-pricing.example.json .chatreview/token-pricing.json
# Edit the copied file: currency, source, confirmation date, exact models and rates.
uv run open-chat-reviewer token-costs import-prices .chatreview/token-pricing.json
uv run open-chat-reviewer token-costs build
uv run open-chat-reviewer token-costs status
```

Importing a price book enables costing for the central worker and `refresh`. The
automation status exposes `refresh.needs_token_costs`; an unchanged snapshot skips
backfill and build work, while disabled costing skips its evidence scan too. The source
sync wrapper alone does not build cost snapshots. Without an imported price book these
downstream jobs skip costing. Usage extraction during ingestion remains available as
queryable evidence independently of pricing.

The example contains no vendor prices. Add entries using this shape; **these are
synthetic demonstration values, not current commercial rates**:

```json
{
  "provider": "claude",
  "model": "synthetic-example-model",
  "service_tier": null,
  "effective_from": "2026-01-01",
  "input_per_mtok": "2",
  "output_per_mtok": "4",
  "cache_write_5m_per_mtok": "3",
  "cache_write_1h_per_mtok": "5",
  "cache_read_per_mtok": "0.2"
}
```

Every rate is an amount **per million tokens in the price book's currency**. Provider,
model and service tier match exactly. An absent tier matches only an absent tier; there
is no fallback across tiers/models. For each local usage day, the newest effective date
on or before that day wins. `CHATREVIEW_TIMEZONE` defines that local day. There is no
exchange conversion and no network price lookup.

Change the book `version` whenever changing its content. Importing an existing identical
book reactivates it; changing content under an existing version is rejected. The stored
source and `confirmed_at` identify provenance. A null confirmation date is visibly
unknown; a date over 90 days old warns. Future confirmation dates are rejected.

## Existing archives and corrected extraction

```bash
uv run open-chat-reviewer token-costs backfill
# After correcting the extraction algorithm, re-extract retained archive evidence:
uv run open-chat-reviewer token-costs build --force
```

Backfill uses retained PostgreSQL payloads through the Claude adapter extraction helper;
it never rereads or changes source files. It commits bounded batches and resumes by
event identity and extraction version. Missing/malformed usage is distinguished from
available zero counts. Unavailable payloads remain explicitly unavailable. No event or
raw archive identity is changed. New ingestion and full archive rebuild both persist
usage through the same projection boundary.

Historical aggregate cache-write counts without TTL labels use Claude's default
five-minute TTL for the unlabelled remainder, preserving the prototype's interpretation.
Explicit one-hour counts remain separate. Invalid or contradictory counts are excluded
from coverage rather than silently coerced. Usage extraction changes must increment
`TOKEN_USAGE_VERSION` or be accompanied by a forced backfill.

## Snapshot and reader contract

Migration `0015` creates `event_token_usage`; `0016` adds immutable price books, an active
book selection and completed snapshots. Snapshots publish atomically with their rows.
A failed build leaves the previous snapshot available; a retry can reuse a completed
matching snapshot. There is no moving wall-clock cutoff in the key. The fingerprint
includes canonical evidence identity, usage, session/project attribution and local day,
combined with extraction/calculation versions, pricing content hash and timezone.
Canonical deduplication first uses the archive's existing `canonical_event_id IS NULL`
contract. Claude can emit different content blocks with the same nested response
`message.id`; the cost projection counts the latest recorded usage for each response
ID once, leaving all canonical transcript events unchanged. Repeated response blocks
are separately reported as duplicate coverage. Older records without a response ID
use event identity and therefore only receive the archive's canonical deduplication.

These are estimates of the recorded tokens, not complete request billing. Claude's
[cost-tracking documentation](https://code.claude.com/docs/en/agent-sdk/cost-tracking)
notes that per-message output counts can be provisional and repeated tool blocks share
response IDs. This feature does not sum cumulative result messages into per-message
counts. It does not infer regional premiums, request/tool fees, or missing final output.

The first implementation computes freshness from grouped canonical evidence on reads;
it performs no refresh writes, but this scan can be significant on very large archives.
Snapshot rows retain session/project labels and nullable identities, including
unattributed usage. Deleting or reassigning live records invalidates freshness without
mutating previously published amounts. Session links in historical snapshots can cease
to resolve if that session is later deleted.

GET endpoints are transactionally read-only and never create schema, import pricing,
extract usage or build snapshots:

- `/api/token-costs/status`
- `/api/token-costs/summary`
- `/api/token-costs/daily?group_by=day|week|month`
- `/api/token-costs/sessions?limit=50`

Filters: inclusive `from`/`to` local dates, exact `model`, and numeric `project` (zero
means unattributed). The session limit is 1–500. Amounts are serialized as decimal
strings. All returned aggregates use one snapshot. Missing prices/timestamps count as
unpriced messages and never contribute to the priced subtotal. Coverage includes all
canonical assistant messages, with available/missing/unavailable/pending/unsupported
counts, plus repeated response blocks; it is archive-wide rather than restricted to
the report's filters.

When stale, the report identifies its original price book/currency and separately names
the active book for the next build. The UI distinguishes snapshot coverage from current
archive coverage. A missing snapshot is an empty state, not a fabricated zero estimate.

## Validation

Use disposable PostgreSQL/pgvector for integration tests; never point test settings at
an archive runtime database. Tests cover extraction, cache TTLs, duplicate messages,
backfill/reuse, effective dates/timezones, unpriced usage, immutable books, invalid rates,
canonical corrections, read-only API behavior and rendered provenance/currency.

```bash
uv run ruff check src tests
uv run pytest -q
cd web
bun install --frozen-lockfile
bun run lint
bun run test
bun run build
```
