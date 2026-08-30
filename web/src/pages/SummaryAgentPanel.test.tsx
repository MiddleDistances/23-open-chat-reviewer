import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SummaryAgentPanel, { type SummaryAgentStatus } from "./SummaryAgentPanel";

afterEach(() => cleanup());

const status: SummaryAgentStatus = {
  selected: "qwen",
  providers: [
    { id: "qwen", label: "Local Qwen", installed: true, authenticated: null, detail: "Configured local model" },
    { id: "codex-cli", label: "Codex CLI", installed: true, authenticated: true, detail: "Ready to use this machine's existing login" },
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
    fireEvent.change(screen.getByLabelText("Conversation history"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: /save and run summaries/i }));

    await waitFor(() => expect(onRun).toHaveBeenCalledWith("codex-cli", 7));
    expect(screen.getByText(/never reads or copies cli tokens/i)).toBeInTheDocument();
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
});
