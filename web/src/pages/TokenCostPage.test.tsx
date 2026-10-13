import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import TokenCostPage, { costAmount, type CostReport } from "./TokenCostPage";

const fixture: CostReport = {
  enabled: true, stale: true,
  snapshot: { id: 1, generated_at: "2026-07-19T01:00:00Z", coverage_json: { available: 2, total: 3 } },
  coverage: { available: 2, total: 4 },
  price_book: { version: "fixture", currency: "EUR", source: "Operator test book", confirmed_at: "2026-01-01" },
  active_price_book_version: "fixture", price_warning: "stale", price_age_days: 100, timezone: "UTC",
  priced_amount: "2.4015", tokens: 100, messages: 2, unpriced_messages: 1, unpriced_models: ["unknown"],
  models: [{ model: "synthetic", tokens: 100, messages: 2, priced_amount: "2.4015", unpriced_messages: 1 }],
  daily: [], sessions: [], projects: [{ id: 0, name: "Unattributed" }],
};

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function show(data: CostReport) {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => data });
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter><TokenCostPage /></MemoryRouter>);
  return fetcher;
}

it("renders the chosen currency, price source, coverage and stale/unpriced warnings", async () => {
  show(fixture);
  expect(await screen.findByText("Source: Operator test book")).toBeInTheDocument();
  expect(screen.getAllByText(/EUR 2\.4015/).length).toBeGreaterThan(0);
  expect(screen.queryByText(/AUD/)).not.toBeInTheDocument();
  expect(screen.getByText(/This report is stale/)).toBeInTheDocument();
  expect(screen.getByText(/Prices are 100 days old/)).toBeInTheDocument();
  expect(screen.getByText(/excluded from the estimate/)).toBeInTheDocument();
  expect(screen.getByText(/Snapshot usage coverage: 2 of 3/)).toBeInTheDocument();
});

it("sends date, model and project filters using GET requests", async () => {
  const fetcher = show(fixture);
  await screen.findByText("Source: Operator test book");
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-07-01" } });
  fireEvent.change(screen.getByLabelText("Model"), { target: { value: "synthetic" } });
  fireEvent.change(screen.getByLabelText("Project"), { target: { value: "0" } });
  await waitFor(() => expect(fetcher.mock.lastCall?.[0]).toContain("project=0"));
  expect(fetcher.mock.lastCall?.[0]).toContain("from=2026-07-01");
  expect(fetcher.mock.lastCall?.[0]).toContain("model=synthetic");
  expect(fetcher.mock.lastCall?.[1]?.method).toBeUndefined();
});

it("explains disabled costing without displaying a fabricated zero estimate", async () => {
  show({ ...fixture, enabled: false, snapshot: null, price_book: null });
  expect(await screen.findByText("Token costing is not enabled")).toBeInTheDocument();
  expect(screen.queryByText("Priced usage estimate")).not.toBeInTheDocument();
});

it("reports an unknown confirmation date", async () => {
  show({ ...fixture, price_warning: "unknown", price_book: { ...fixture.price_book!, confirmed_at: null } });
  expect(await screen.findByText("Price confirmation date is unknown.")).toBeInTheDocument();
});

it("shows request errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Archive unavailable")));
  render(<MemoryRouter><TokenCostPage /></MemoryRouter>);
  expect(await screen.findByText("Archive unavailable")).toBeInTheDocument();
});

it("shows unpriced-only usage as not priced rather than a zero-cost estimate", async () => {
  show({ ...fixture, messages: 1, unpriced_messages: 1, priced_amount: "0", models: [
    { model: "unknown", messages: 1, tokens: 100, unpriced_messages: 1, priced_amount: "0" },
  ] });
  expect((await screen.findAllByText("Not priced")).length).toBe(2);
  expect(screen.queryByText("EUR 0.00")).not.toBeInTheDocument();
});

it("preserves large integer and sub-cent decimal amounts", () => {
  expect(costAmount("EUR", "9007199254740993.000000000001").replaceAll(",", ""))
    .toBe("EUR 9007199254740993.000000000001");
});
