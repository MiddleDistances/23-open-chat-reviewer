# Token cost panel

Adds a **Token cost** tab to the web application, showing what the archived
conversations would cost at Anthropic's published API prices, broken down by
day, week, month, model, project and session.

> **This is a personal build, not a proposed upstream feature.** It works, it is
> linted and it has been tested, but several choices below are hardcoded for one
> operator rather than made configurable. Read [Limitations](#limitations) before
> relying on it, and see [If this were to go upstream](#if-this-were-to-go-upstream)
> for what would have to change first.

## Why it exists

The archive already answers "what was I working on" and "how long did it take".
It cannot answer "what did that cost", because the ingestion pipeline does not
extract token counts: `providers/claude.py` keeps a fixed metadata whitelist and
`usage` is not on it.

The data is not lost, though. Raw provider payloads are preserved verbatim in
`raw_payloads`, and Claude Code writes a `usage` object on every assistant
message. In one real archive, 107,921 of 107,964 assistant messages carried
one, a coverage of 99.96%.

So the numbers were always there. Nothing was reading them.

## How it works

```text
raw_payloads (bytea, untouched)
      |  extracted once, then incrementally
      v
token_report.usage      <- a private schema, created on first use
      |  joined back to events + sessions at read time
      v
GET /token-report  ->  a self-contained HTML report
      |
      v
/token-cost  ->  the sidebar tab, which frames it
```

Three properties worth stating explicitly:

- **Upstream tables are read-only.** The only thing written is `token_report.usage`,
  in its own PostgreSQL schema so no upstream migration can ever collide with it.
- **Extraction happens once.** Decoding every payload per request would take a
  minute; instead a high-water mark on `event_id` means each request reads only
  events added since the last one. After the first build a refresh is milliseconds.
- **Duplicates are filtered on read, not on write.** `events.canonical_event_id`
  is only populated later, during `refresh`, so a row counted at ingestion may
  later prove to be a duplicate. Filtering at read time keeps totals correct as
  the archive re-canonicalises.

## Install

```bash
bash contrib/token-cost/install-token-tab.sh
```

It patches two files, rebuilds the interface, and restarts the web service if it
is running under systemd. Idempotent, so re-run it after any update that reverts
the patch. Then: **Work archive → Token cost**, or `/token-cost` directly.

### What the patch touches

| File | Change |
|---|---|
| `src/chatreview/token_panel.py` | New. All extraction and rendering. |
| `src/chatreview/api.py` | +7 lines: a `/token-report` route before the SPA catch-all. |
| `web/src/App.tsx` | +13 lines: an icon import, a sidebar entry, a route, and an iframe wrapper. |

Originals are kept as `.orig` alongside. To revert:

```bash
git checkout -- src/chatreview/api.py web/src/App.tsx
cd web && bun run build
```

## Without patching anything

`standalone/` holds the same report as a separate read-only HTTP service on
port 8766, leaving the upstream tree untouched entirely. Useful on a machine
where carrying a patch is not worth it.

```bash
bash contrib/token-cost/standalone/install-token-live.sh
```

## Command line

```bash
# what usage data does this archive actually hold?
uv run python contrib/token-cost/token-probe.py

# a one-off report plus per-day and per-session CSVs
uv run python contrib/token-cost/token-report.py
```

## Configuration

All of it currently lives at the top of `src/chatreview/token_panel.py`:

| Constant | Meaning |
|---|---|
| `PRICES` | USD per million tokens, per model. Input, output, 5-minute and 1-hour cache writes, cache reads. |
| `AUD_PER_USD` | Currency conversion applied to every figure. |
| `TZ` | IANA zone used to bucket days. |

Cache writes are priced by their actual TTL, read from
`usage.cache_creation.ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`,
because the 1-hour multiplier is meaningfully higher.

## Limitations

- **Prices are hardcoded and will go stale.** They are correct as at the commit
  date and nothing warns you when they drift. A model with no `PRICES` entry has
  its tokens counted but costs nothing, and the report says so in a banner.
- **The currency is fixed to AUD at a constant rate.** No live FX, no other currency.
- **The timezone is a constant**, rather than reading the project's existing
  `CHATREVIEW_TIMEZONE` setting, which it should.
- **The tab is an iframe.** The report is a complete styled document, so embedding
  it avoided a much larger patch and any CSS collision with the app. It is not a
  React page in the application's own idiom.
- **No tests.** The project has a substantial suite; this adds nothing to it.
- **Figures are usually not money you paid.** Under a Claude subscription, tokens
  are not billed per unit. Read the totals as replacement cost, what the same work
  would have cost at list price. That is arguably the more useful number for
  attributing tooling value to a client, but it is not an invoice.

## If this were to go upstream

In rough order of importance: move `PRICES`, the currency and the rate into
`Settings` and the environment file, with the price table shipped as data rather
than code so it can be updated without a release; read `settings.timezone`
instead of `TZ`; replace the iframe with a React page fed by a JSON endpoint,
so the report participates in the app's theming and navigation; add tests in the
style of `tests/test_api.py` and `tests/test_reporting.py`, including the
duplicate-filtering and incremental-watermark behaviour; and document it under
`docs/`.

## License

Apache 2.0, same as the project it extends.
