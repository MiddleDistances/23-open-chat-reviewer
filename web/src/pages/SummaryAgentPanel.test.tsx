import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SummaryAgentPanel, { type SummaryAgentStatus } from "./SummaryAgentPanel";

afterEach(() => cleanup());

const status: SummaryAgentStatus = {
  selected: "qwen",
  providers: [
    { id: "qwen", label: "Local Qwen", installed: true, authenticated: null, detail: "Configured local model" },
    { id: "codex-cli", label: "Codex CLI", installed: true, authenticated: true, detail: "Uses this computer's existing login" },
    { id: "claude-cli", label: "Claude Code", installed: false, authenticated: null, detail: "Not installed" },
  ],
  run: { status: "idle", active: false },
  latest_run: null,
};

describe("summary agent setup", () => {
  it("selects a fixed installed CLI and runs a bounded history window", async () => {
    const onRun = vi.fn().mockResolvedValue(undefined);
    render(<SummaryAgentPanel status={status} onRun={onRun} />);

    fireEvent.click(screen.getByRole("radio", { name: /codex cli/i }));
    fireEvent.change(screen.getByRole("combobox", { name: /summary window/i }), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: /run summaries/i }));

    await waitFor(() => expect(onRun).toHaveBeenCalledWith("codex-cli", 7));
    expect(screen.getByText(/cli credentials stay with the cli/i)).toBeInTheDocument();
  });

  it("shows live summary progress and prevents changing providers", () => {
    render(
      <SummaryAgentPanel
        status={{
          ...status,
          run: {
            status: "running",
            active: true,
            provider: "qwen",
            message: "Selected 40 recent work threads",
          },
        }}
      />,
    );

    expect(screen.getByText("Selected 40 recent work threads")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /summaries are running/i })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /codex cli/i })).toBeDisabled();
  });

  it("exposes stable ids for every summary-agent action", () => {
    render(<SummaryAgentPanel status={status} onRun={vi.fn()} />);

    for (const button of screen.getAllByRole("button")) {
      expect(button, button.textContent ?? "unnamed button").toHaveAttribute("id");
      expect(button, button.textContent ?? "unnamed button").toHaveAttribute("data-action-id");
    }
    expect(screen.getByRole("combobox", { name: /summary window/i })).toHaveAttribute(
      "data-action-id",
      "summary.scope.days",
    );
  });

  it("shows an explicit provider loading state", () => {
    render(<SummaryAgentPanel status={null} loading />);

    expect(screen.getByRole("status")).toHaveTextContent("Checking available providers…");
    expect(screen.queryByText("No summary agents were detected.")).not.toBeInTheDocument();
  });

  it("opens the guided setup when unconfigured Qwen is clicked", () => {
    const onConfigure = vi.fn();
    render(
      <SummaryAgentPanel
        status={{
          ...status,
          selected: "codex-cli",
          providers: status.providers.map((provider) => provider.id === "qwen"
            ? { ...provider, installed: false, detail: "Configure an endpoint first" }
            : provider),
        }}
        onConfigure={onConfigure}
      />,
    );

    fireEvent.click(screen.getByRole("radio", { name: /local qwen/i }));
    expect(onConfigure).toHaveBeenCalledWith("qwen");
  });

  it("shows a newer database batch instead of stale local run state", () => {
    render(
      <SummaryAgentPanel
        status={{
          ...status,
          run: {
            status: "complete",
            active: false,
            provider: "codex-cli",
            finished_at: "2026-08-30T13:34:30Z",
            message: "Old Codex batch",
          },
          latest_run: {
            status: "complete",
            completed_at: "2026-08-30T15:59:39Z",
            model_name: "qwen3.8-27b",
            generated_count: 6,
            reused_count: 5,
          },
        }}
      />,
    );

    expect(screen.getByText(/last batch · qwen3\.8-27b: 6 generated, 5 unchanged/i)).toBeInTheDocument();
    expect(screen.queryByText("Old Codex batch")).not.toBeInTheDocument();
  });
});
