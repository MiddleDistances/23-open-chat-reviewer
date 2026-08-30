import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import MapPage, { mapPointPreview, mapPointTooltip, mapQuery, pointMatchesDate, type MapData, type MapPoint } from "./MapPage";

const point = (overrides: Partial<MapPoint> = {}): MapPoint => ({
  id: 7,
  window_key: "window-7",
  sequence_no: 3,
  cluster_id: 2,
  episode_id: null,
  x: 1,
  y: 2,
  session_id: 41,
  provider: "codex",
  project: "archive",
  preview: "The vectorized conversation text, not a generated headline.",
  timestamp: "2026-08-20T12:00:00Z",
  ...overrides,
});

const data: MapData = {
  run: {
    id: 3,
    run_key: "run-3",
    model_name: "test-model",
    model_revision: "test",
    dimensions: 2,
    chunk_count: 1,
    completed_at: "2026-08-30T00:00:00Z",
    status: "complete",
    error: null,
    profile: "conversation",
    freshness: "current",
  },
  total: 2,
  sample_stride: 1,
  points: [
    point(),
    point({ id: 8, window_key: "window-8", x: 4, y: 5, timestamp: "2026-08-25T12:00:00Z", preview: "A later vectorized text window." }),
  ],
  clusters: [{ cluster_id: 2, label: "Archive work", keywords_json: "[]", window_count: 2 }],
};

afterEach(() => cleanup());

describe("semantic map", () => {
  it("builds the date-aware API query", () => {
    expect(mapQuery({ runId: "3", provider: "codex", clusterId: "2", dateFrom: "2026-08-01", dateTo: "2026-08-30" })).toContain("date_from=2026-08-01");
    expect(mapQuery({ runId: "3", provider: "codex", clusterId: "2", dateFrom: "2026-08-01", dateTo: "2026-08-30" })).toContain("date_to=2026-08-30");
    expect(mapQuery({ runId: "", provider: "", clusterId: "", dateFrom: "", dateTo: "" })).toContain("limit=200000");
  });

  it("uses the vectorized text in previews and never the headline", () => {
    const item = point({ headline: "Repeated headline", preview: "Distinct text sent to the embedding model." });
    expect(mapPointPreview(item)).toBe("Distinct text sent to the embedding model.");
    expect(mapPointTooltip(item)).toContain("Distinct text sent to the embedding model.");
    expect(mapPointTooltip(item)).not.toContain("Repeated headline");
  });

  it("handles inclusive date bounds for local fallback filtering", () => {
    const item = point({ timestamp: "2026-08-20T12:00:00Z" });
    expect(pointMatchesDate(item, "2026-08-20", "2026-08-20")).toBe(true);
    expect(pointMatchesDate(item, "2026-08-21", "")).toBe(false);
    expect(pointMatchesDate(point({ timestamp: null }), "2026-08-01", "")).toBe(false);
  });

  it("shows date controls and an accessible vector preview on hover/focus", () => {
    render(<MemoryRouter><MapPage data={data} semanticRuns={[]} /></MemoryRouter>);
    expect(screen.getByLabelText("Date from")).toHaveAttribute("type", "date");
    expect(screen.getByLabelText("Date to")).toHaveAttribute("type", "date");

    const mapPoint = screen.getByRole("button", { name: /The vectorized conversation text/ });
    fireEvent.focus(mapPoint);
    expect(screen.getByRole("tooltip")).toHaveTextContent("The vectorized conversation text");
    fireEvent.keyDown(mapPoint, { key: "Enter" });
    expect(screen.getByTestId("selected-vector-preview")).toHaveTextContent("The vectorized conversation text");
  });

  it("renders an explicit setup state when no projection exists", () => {
    render(<MemoryRouter><MapPage data={{ ...data, run: null, points: [] }} semanticRuns={[]} /></MemoryRouter>);
    expect(screen.getByText("No semantic projection built")).toBeInTheDocument();
    expect(screen.getByText(/uv run chatreview derive/)).toBeInTheDocument();
  });

  it("lets a date change notify the parent and reset the selected point", () => {
    const onFiltersChange = vi.fn();
    render(<MemoryRouter><MapPage data={data} semanticRuns={[]} onFiltersChange={onFiltersChange} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Date from"), { target: { value: "2026-08-24" } });
    expect(onFiltersChange).toHaveBeenCalledWith(expect.objectContaining({ dateFrom: "2026-08-24" }));
    expect(screen.getByText("1 windows")).toBeInTheDocument();
  });
});
