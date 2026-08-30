import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SetupPage, { type SetupEstimate, type SetupMachine } from "./SetupPage";

afterEach(() => cleanup());

const machine: SetupMachine = {
  id: "ubuntu-fast",
  name: "Ubuntu fast",
  status: "current",
  platform: "Linux",
  sourceRoots: [
    { provider: "codex", path: "/home/michael/.codex", recordCount: 24 },
    { provider: "claude", path: "/home/michael/.claude", recordCount: 8 },
  ],
  eventCount: 42,
  lastSeenAt: "2026-08-30T09:00:00Z",
};

const estimate: SetupEstimate = {
  sourceCount: 24,
  sessionCount: 6,
  eventCount: 42,
  rawBytes: 1_000_000,
  totalBytes: 2_000_000,
  encryptedReasoningBytes: 500_000,
  readableReasoningBytes: 20_000,
  semanticWindowCount: 12,
  estimatedSeconds: 75,
};

describe("archive setup page", () => {
  it("explains the machine, scope, and separate reasoning policies", () => {
    render(<SetupPage machines={[machine]} estimate={estimate} />);

    expect(screen.getByRole("heading", { name: /make every machine part/i })).toBeInTheDocument();
    expect(screen.getByText("Ubuntu fast")).toBeInTheDocument();
    expect(screen.getByText("1.9 MiB")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /preserve encrypted raw reasoning/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /include readable reasoning in text search/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /include reasoning in the vector projection/i })).not.toBeChecked();
    expect(screen.getByText(/repositories, commits, paths—not file contents/i)).toBeInTheDocument();
  });

  it("reports draft changes and keeps raw, search, and semantic controls distinct", () => {
    const onChange = vi.fn();
    render(<SetupPage onChange={onChange} />);

    fireEvent.click(screen.getByRole("checkbox", { name: /include reasoning in the vector projection/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /include readable reasoning in text search/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /preserve encrypted raw reasoning/i }));

    const last = onChange.mock.lastCall?.[0];
    expect(last).toMatchObject({
      preserveEncryptedReasoning: false,
      includeReadableReasoningInSearch: true,
      includeReasoningInProjection: true,
    });
    expect(screen.getByRole("checkbox", { name: /preserve encrypted raw reasoning/i })).not.toBeChecked();
  });

  it("passes the selected range to a preview callback and renders the returned estimate", async () => {
    const onPreview = vi.fn().mockResolvedValue({ ...estimate, totalBytes: 3_000_000 });
    render(<SetupPage onPreview={onPreview} />);

    fireEvent.change(screen.getByLabelText("History start date"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("History end date"), { target: { value: "2026-08-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview build" }));

    await waitFor(() => expect(onPreview).toHaveBeenCalledWith(expect.objectContaining({ historyStart: "2026-01-01", historyEnd: "2026-08-30" })));
    expect(await screen.findByText("2.9 MiB")).toBeInTheDocument();
  });

  it("exposes progress semantics and machine selection to the host", () => {
    const onSelectMachine = vi.fn();
    const onCancelBuild = vi.fn();
    render(<SetupPage machines={[machine]} onSelectMachine={onSelectMachine} onCancelBuild={onCancelBuild} progress={{ status: "embedding", phase: "Embedding", completed: 3, total: 10, estimatedSecondsRemaining: 20 }} />);

    fireEvent.click(screen.getByRole("button", { name: /ubuntu fast/i }));
    expect(onSelectMachine).toHaveBeenCalledWith("ubuntu-fast");
    expect(screen.getByRole("progressbar", { name: /archive build progress/i })).toHaveAttribute("aria-valuenow", "30");
    fireEvent.click(screen.getByRole("button", { name: "Stop build" }));
    expect(onCancelBuild).toHaveBeenCalledTimes(1);
  });
});
