import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SetupConnection } from "./ConnectionGuide";
import SetupPage, { type EmbeddingModelStatus, type SetupEstimate, type SetupMachine } from "./SetupPage";

afterEach(() => cleanup());
beforeEach(() => window.localStorage.setItem("open-chat-reviewer.experience-mode", "advanced"));

const machine: SetupMachine = {
  id: "linux-box",
  name: "Linux box",
  status: "current",
  platform: "Linux",
  sourceRoots: [
    { provider: "codex", path: "/home/example/.codex", recordCount: 24 },
    { provider: "claude", path: "/home/example/.claude", recordCount: 8 },
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

const connection: SetupConnection = {
  centralMachine: { id: "linux-box", name: "Linux box", hostname: "linux-box" },
  web: { url: "http://linux-box.example.ts.net:8766", host: "0.0.0.0", port: 8766 },
  database: {
    localEndpoint: "127.0.0.1:54329",
    writerEndpoint: "linux-box.example.ts.net:54329",
    remoteReady: true,
  },
  tailscale: {
    connected: true,
    ipv4: "100.64.0.1",
    dnsName: "linux-box.example.ts.net",
  },
  networkScan: false,
  warnings: [],
};

const missingEmbeddingModel: EmbeddingModelStatus = {
  id: "qwen3-embedding-0.6b",
  label: "Balanced local (recommended)",
  description: "Qwen3 0.6B at 512 dimensions; private, multilingual semantic search.",
  model_name: "Qwen/Qwen3-Embedding-0.6B",
  revision: "pinned-revision",
  dimensions: 512,
  source_url: "https://huggingface.co/Qwen/Qwen3-Embedding-0.6B",
  status: "not_downloaded",
  message: "Not downloaded on this machine",
};

describe("archive setup page", () => {
  it("keeps specialist retention controls out of the basic three-step path", () => {
    window.localStorage.setItem("open-chat-reviewer.experience-mode", "basic");
    render(<SetupPage firstRun />);

    expect(screen.getByRole("heading", { name: "Set up your chat archive" })).toBeInTheDocument();
    expect(screen.getByText(/connect this computer, choose a date range, then build/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /storage & search/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /preserve encrypted raw reasoning/i })).not.toBeInTheDocument();
    expect(document.getElementById("setup-step-build")).toHaveTextContent("03Build");
  });

  it("defaults to seven days and offers only the intended history presets", () => {
    render(<SetupPage />);

    expect(screen.getByRole("button", { name: "Last 7 days" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Last 30 days" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Last 90 days" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All available" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Last year" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All available" }));
    expect(screen.getByLabelText("History start date")).toHaveValue("");
    expect(screen.getByLabelText("History end date")).toHaveValue("");
  });

  it("explains the machine, scope, and separate reasoning policies", () => {
    render(<SetupPage machines={[machine]} estimate={estimate} connection={connection} />);

    expect(screen.getByRole("heading", { name: /make every machine part/i })).toBeInTheDocument();
    expect(screen.getAllByText("Linux box")).toHaveLength(3);
    expect(screen.getByText("1.9 MiB")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /preserve encrypted raw reasoning/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /include readable reasoning in text search/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /include reasoning in the vector projection/i })).not.toBeChecked();
    expect(screen.getByText(/repositories, commits, paths—not file contents/i)).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /multi-machine architecture/i })).toHaveLength(2);
    expect(screen.getByText("linux-box.example.ts.net:54329")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Setup guide" })).toHaveAttribute("data-action-id", "setup.guide.open");
    expect(screen.getByRole("button", { name: "Preview build" })).toHaveAttribute("id", "setup-preview-build");
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

  it("offers a pinned Hugging Face download when the embedding model is not local", async () => {
    const onDownload = vi.fn().mockResolvedValue(undefined);
    const onStartBuild = vi.fn();
    render(
      <SetupPage
        embeddingModels={[missingEmbeddingModel]}
        onDownloadEmbeddingModel={onDownload}
        onStartBuild={onStartBuild}
      />,
    );

    expect(screen.getByLabelText("Embedding model preset")).toHaveValue("qwen3-embedding-0.6b");
    expect(screen.getByText("Download required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download model first" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Download from Hugging Face" }));

    await waitFor(() => expect(onDownload).toHaveBeenCalledWith("qwen3-embedding-0.6b"));
    expect(screen.getByRole("status")).toHaveTextContent(/model download started/i);
  });

  it("passes the selected range to a preview callback and renders the returned estimate", async () => {
    const onPreview = vi.fn().mockResolvedValue({ ...estimate, totalBytes: 3_000_000 });
    render(<SetupPage onPreview={onPreview} />);

    fireEvent.change(screen.getByLabelText("History start date"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("History end date"), { target: { value: "2026-08-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview build" }));

    await waitFor(() => expect(onPreview).toHaveBeenCalledWith(expect.objectContaining({ historyStart: "2026-01-01", historyEnd: "2026-08-30" })));
    expect(await screen.findByText("2.9 MiB")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/build estimate is ready/i);
  });

  it("explains machine registration and reports a shared-database check", async () => {
    const onRefreshMachines = vi.fn().mockResolvedValue(
      "Checked the shared archive: 2 registered machines. No network scan was performed.",
    );
    render(<SetupPage machines={[machine]} connection={connection} onRefreshMachines={onRefreshMachines} />);

    fireEvent.click(screen.getByRole("button", { name: "Add another machine" }));
    expect(screen.getByRole("heading", { name: /connect one other computer/i })).toBeInTheDocument();
    expect(screen.getByText(/performs the first resumable sync/i)).toBeInTheDocument();
    expect(screen.getByText(/scripts\/connect-computer.sh ~\/Downloads\/my-laptop.env/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Check shared archive" }));

    await waitFor(() => expect(onRefreshMachines).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("status")).toHaveTextContent(/2 registered machines/i);
    expect(screen.getByRole("button", { name: "Check shared archive" })).toHaveAttribute(
      "data-action-id",
      "setup.machine.refresh",
    );
  });

  it("exposes progress semantics and machine selection to the host", () => {
    const onSelectMachine = vi.fn();
    const onCancelBuild = vi.fn();
    render(<SetupPage machines={[machine]} onSelectMachine={onSelectMachine} onCancelBuild={onCancelBuild} progress={{ status: "embedding", phase: "Embedding", completed: 3, total: 10, estimatedSecondsRemaining: 20 }} />);

    fireEvent.click(screen.getByRole("button", { name: /linux box/i }));
    expect(onSelectMachine).toHaveBeenCalledWith("linux-box");
    expect(screen.getByRole("button", { name: /linux box/i })).toHaveAttribute(
      "data-action-id",
      "setup.machine.select",
    );
    expect(screen.getByRole("progressbar", { name: /archive build progress/i })).toHaveAttribute("aria-valuenow", "30");
    fireEvent.click(screen.getByRole("button", { name: "Stop build" }));
    expect(onCancelBuild).toHaveBeenCalledTimes(1);
  });

  it("gives every rendered button a stable browser id and semantic action id", () => {
    render(
      <SetupPage
        machines={[machine]}
        onPreview={vi.fn()}
        onStartBuild={vi.fn()}
        onCancelBuild={vi.fn()}
        onRefreshMachines={vi.fn()}
        onSelectMachine={vi.fn()}
        onOpenInstructions={vi.fn()}
        onOpenWriterInstructions={vi.fn()}
        progress={{ status: "syncing", completed: 1, total: 2 }}
      />,
    );

    for (const button of screen.getAllByRole("button")) {
      expect(button, button.textContent ?? "unnamed button").toHaveAttribute("id");
      expect(button, button.textContent ?? "unnamed button").toHaveAttribute("data-action-id");
    }
  });
});
