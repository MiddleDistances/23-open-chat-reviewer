import { useState } from "react";
import { Link } from "react-router-dom";
import { queryString, useApi } from "../api";
import { EmptyState, ErrorNotice, formatNumber, Loading, PageHeader } from "../components/Common";
import "./token-cost.css";

type CostRow = { model?: string; day?: string | null; session_id?: number | null; session?: string;
  project?: string; tokens: number; messages: number; priced_amount: string; unpriced_messages: number };
export type CostReport = {
  enabled: boolean; stale: boolean;
  snapshot: { id: number; generated_at: string; coverage_json: Record<string, number> } | null;
  coverage: Record<string, number>;
  price_book: { version: string; currency: string; source: string; confirmed_at: string | null } | null;
  active_price_book_version: string | null; price_warning: "unknown" | "stale" | null;
  price_age_days: number | null; timezone: string; priced_amount: string; tokens: number;
  messages: number; unpriced_messages: number; unpriced_models: string[];
  daily: CostRow[]; models: CostRow[]; sessions: CostRow[];
  projects: { id: number; name: string }[];
};

export default function TokenCostPage() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [model, setModel] = useState("");
  const [project, setProject] = useState("");
  const { data, loading, error } = useApi<CostReport>(
    `/api/token-costs/summary?${queryString({ from, to, model, project })}`,
  );
  const currency = data?.price_book?.currency ?? "";
  const amount = (value: string) => `${currency} ${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 4,
  })}`;
  const rowAmount = (row: CostRow) => row.messages === row.unpriced_messages ? "Not priced" : amount(row.priced_amount);
  return <>
    <PageHeader eyebrow="Archive usage estimates" title="Token costs" />
    <p>API-equivalent estimates from recorded usage. Per-message output counts can be provisional;
      subscription payments and invoices may differ.</p>
    <div className="filter-bar token-cost-filters">
      <label>From<input aria-label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
      <label>To<input aria-label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
      <label>Model<input aria-label="Model" value={model} placeholder="Exact model name"
        onChange={(e) => setModel(e.target.value)} /></label>
      <label>Project<select aria-label="Project" value={project} onChange={(e) => setProject(e.target.value)}>
        <option value="">All projects</option>
        {data?.projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
    </div>
    {loading && <Loading label="Loading token costs" />}
    {error && <ErrorNotice message={error} />}
    {!loading && !error && data && <>
      {!data.enabled && <EmptyState title="Token costing is not enabled">
        Ask your archive operator to import a price book and build the first cost report.
      </EmptyState>}
      {data.enabled && !data.snapshot && <EmptyState title="Waiting for the first cost report">
        Pricing is configured. The next archive refresh will prepare usage and estimates.
      </EmptyState>}
      {data.enabled && data.stale && data.snapshot && <p role="status" className="error-notice">
        This report is stale. Archive evidence, pricing, or timezone has changed; amounts remain from the
        displayed snapshot until the next refresh.
      </p>}
      {data.price_book && <section className="token-cost-provenance" aria-label="Pricing provenance">
        <strong>Price book {data.price_book.version} · {currency}</strong>
        <p>Source: {data.price_book.source}</p>
        <p>Confirmed: {data.price_book.confirmed_at ?? "Unknown"} · Timezone: {data.timezone}</p>
        {data.price_warning === "stale" && <p role="status">Prices are {data.price_age_days} days old.
          Confirm current rates before relying on these estimates.</p>}
        {data.price_warning === "unknown" && <p role="status">Price confirmation date is unknown.</p>}
        {data.active_price_book_version !== data.price_book.version &&
          <p>Next refresh will use price book {data.active_price_book_version}.</p>}
      </section>}
      {data.snapshot && <>
        <section className="token-cost-totals" aria-label="Cost totals">
          <div><span>Priced usage estimate</span><strong>
            {data.messages > 0 && data.messages === data.unpriced_messages ? "Not priced" : amount(data.priced_amount)}
          </strong></div>
          <div><span>Recorded tokens</span><strong>{formatNumber(data.tokens)}</strong></div>
          <div><span>Messages with usage</span><strong>{formatNumber(data.messages)}</strong></div>
        </section>
        {data.unpriced_messages > 0 && <p role="status" className="error-notice">
          {data.unpriced_messages} messages have no matching price or usable date and are excluded from the
          estimate. Models: {data.unpriced_models.join(", ")}.
        </p>}
        <p>Snapshot usage coverage: {data.snapshot.coverage_json.available} of {data.snapshot.coverage_json.total}
          {" "}canonical assistant messages. Missing, unavailable, pending, unsupported usage and repeated
          response blocks are excluded.</p>
        <p>Current archive coverage: {data.coverage.available} of {data.coverage.total} messages.
          {" "}Report generated {new Date(data.snapshot.generated_at).toLocaleString()}.</p>
        <h2>By model</h2>
        <div className="archive-table-wrap"><table className="token-cost-table"><thead><tr>
          <th>Model</th><th>Tokens</th><th>Priced estimate</th><th>Unpriced messages</th>
        </tr></thead><tbody>{data.models.map((row) => <tr key={row.model}>
          <td>{row.model}</td><td>{formatNumber(row.tokens)}</td><td>{rowAmount(row)}</td>
          <td>{row.unpriced_messages}</td>
        </tr>)}</tbody></table></div>
        <h2>By day</h2>
        <div className="archive-table-wrap"><table className="token-cost-table"><thead><tr>
          <th>Day</th><th>Tokens</th><th>Priced estimate</th><th>Unpriced messages</th>
        </tr></thead><tbody>{data.daily.map((row) => <tr key={row.day ?? "undated"}>
          <td>{row.day ?? "Undated"}</td><td>{formatNumber(row.tokens)}</td>
          <td>{rowAmount(row)}</td><td>{row.unpriced_messages}</td>
        </tr>)}</tbody></table></div>
        <h2>Sessions by estimated cost</h2>
        <p>Up to 50 sessions matching these filters.</p>
        <div className="archive-table-wrap"><table className="token-cost-table"><thead><tr>
          <th>Session</th><th>Project</th><th>Priced estimate</th><th>Unpriced messages</th>
        </tr></thead><tbody>{data.sessions.map((row) => <tr key={row.session_id ?? "unattributed"}>
          <td>{row.session_id ? <Link to={`/sessions/${row.session_id}`}>{row.session}</Link> : row.session}</td>
          <td>{row.project}</td><td>{rowAmount(row)}</td><td>{row.unpriced_messages}</td>
        </tr>)}</tbody></table></div>
        {data.messages === 0 && <EmptyState title="No recorded usage matches these filters">
          Try another date range or model. Missing usage is not counted as zero-cost activity.
        </EmptyState>}
      </>}
    </>}
  </>;
}
