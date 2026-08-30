import { useEffect, useMemo, useState } from "react";
import { api, useApi } from "../api";
import SetupPage, {
  type EmbeddingModelStatus,
  type SetupConfig,
  type SetupEstimate,
  type SetupMachine,
  type SetupProgress,
} from "./SetupPage";
import type { SetupConnection } from "./ConnectionGuide";
import SummaryAgentPanel, {
  type SummaryAgentId,
  type SummaryAgentStatus,
} from "./SummaryAgentPanel";

interface SetupStatusResponse {
  generated_at: string;
  machine: { id: string; name: string; hostname: string };
  roots: Array<{
    provider: "codex" | "claude" | "gemini" | "git";
    path: string | null;
    exists: boolean;
    readable: boolean;
  }>;
  database: {
    available: boolean;
    ingestion_complete: number;
    ingestion_in_progress: number;
    ingestion_failed: number;
    error: string | null;
  };
}

interface SetupPreviewResponse {
  corpus: {
    database_size_bytes: number | null;
    sources: number;
  };
  reasoning: {
    encrypted_reasoning_bytes: number | null;
    readable_reasoning_bytes: number;
    semantic_windows_total: number;
  };
  scope_estimate: {
    events: number;
    sessions: number;
    raw_bytes: number;
    text_units: number;
    included_percent: number | null;
    error: string | null;
  };
  machines: Array<{
    machine_id: string;
    name: string;
    last_seen_at: string | null;
    source_count: number;
    event_count: number;
  }>;
  warnings: string[];
}

interface SetupMachinesResponse {
  generated_at: string;
  current_machine_id: string;
  available: boolean;
  method: "shared_database";
  network_scan: false;
  machines: Array<{
    machine_id: string;
    name: string;
    last_seen_at: string | null;
    source_count: number;
    session_count: number;
    event_count: number;
  }>;
  message: string;
  error: string | null;
}

interface SetupConnectionResponse {
  central_machine: { id: string; name: string; hostname: string };
  web: { url: string; host: string; port: number };
  database: {
    local_endpoint: string;
    writer_endpoint: string | null;
    remote_ready: boolean;
  };
  tailscale: {
    connected: boolean;
    ipv4: string | null;
    dns_name: string | null;
  };
  network_scan: false;
  warnings: string[];
}

function requestBody(config: SetupConfig) {
  return {
    history_start: config.historyStart || null,
    history_end: config.historyEnd || null,
    providers: config.providers,
    include_git_metadata: config.includeGitMetadata,
    preserve_encrypted_reasoning: config.preserveEncryptedReasoning,
    include_readable_reasoning_in_search: config.includeReadableReasoningInSearch,
    include_reasoning_in_projection: config.includeReasoningInProjection,
    embedding_preset: config.embeddingPreset,
  };
}

function estimateFromPreview(preview: SetupPreviewResponse): SetupEstimate {
  const scope = preview.scope_estimate;
  const reasoning = preview.reasoning;
  return {
    sourceCount: preview.corpus.sources,
    sessionCount: scope.sessions,
    eventCount: scope.events,
    rawBytes: scope.raw_bytes,
    totalBytes: preview.corpus.database_size_bytes ?? scope.raw_bytes,
    encryptedReasoningBytes: reasoning.encrypted_reasoning_bytes ?? undefined,
    readableReasoningBytes: reasoning.readable_reasoning_bytes,
    semanticWindowCount: reasoning.semantic_windows_total || Math.ceil(scope.text_units / 8),
    note: [
      scope.included_percent == null
        ? null
        : `${scope.included_percent.toFixed(1)}% of current timestamped events match this scope.`,
      scope.error,
      ...preview.warnings,
    ]
      .filter(Boolean)
      .join(" "),
  };
}

export default function SetupRoute() {
  const { data: setupStatus, refresh: refreshStatus } =
    useApi<SetupStatusResponse>("/api/setup/status");
  const { data: connectionResponse } =
    useApi<SetupConnectionResponse>("/api/setup/connection");
  const { data: progress, setData: setProgress } =
    useApi<SetupProgress>("/api/setup/build");
  const {
    data: embeddingModels,
    refresh: refreshEmbeddingModels,
  } = useApi<EmbeddingModelStatus[]>("/api/setup/embedding-models");
  const [preview, setPreview] = useState<SetupPreviewResponse | null>(null);
  const { data: machineRegistry, setData: setMachineRegistry } =
    useApi<SetupMachinesResponse>("/api/setup/machines");
  const {
    data: summaryAgent,
    loading: summaryAgentLoading,
    error: summaryAgentError,
    refresh: refreshSummaryAgent,
  } = useApi<SummaryAgentStatus>("/api/summary-agent");

  useEffect(() => {
    if (
      !progress ||
      ["idle", "complete", "failed", "cancelled", "interrupted"].includes(progress.status)
    ) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api<SetupProgress>("/api/setup/build");
        setProgress(next);
        refreshStatus();
      } catch {
        // The next poll may recover; action errors are surfaced by SetupPage callbacks.
      }
    }, 3_000);
    return () => window.clearInterval(timer);
  }, [progress?.status, refreshStatus]);

  useEffect(() => {
    if (!summaryAgent?.run.active) return;
    const timer = window.setInterval(refreshSummaryAgent, 3_000);
    return () => window.clearInterval(timer);
  }, [summaryAgent?.run.active, refreshSummaryAgent]);

  useEffect(() => {
    if (!embeddingModels?.some((model) => model.status === "queued" || model.status === "downloading")) return;
    const timer = window.setInterval(refreshEmbeddingModels, 2_000);
    return () => window.clearInterval(timer);
  }, [embeddingModels, refreshEmbeddingModels]);

  const machines = useMemo<SetupMachine[]>(() => {
    const registered = machineRegistry?.machines.length
      ? machineRegistry.machines
      : preview?.machines ?? [];
    if (registered.length) {
      return registered.map((machine) => {
        const isCurrent = machine.machine_id === setupStatus?.machine.id;
        const sessionCount = "session_count" in machine && typeof machine.session_count === "number"
          ? machine.session_count
          : null;
        return {
          id: machine.machine_id,
          name: machine.name,
          platform: isCurrent ? setupStatus?.machine.hostname : "Registered writer",
          status: isCurrent ? "current" : "connected",
          sourceRoots: isCurrent
            ? (setupStatus?.roots ?? [])
                .filter((root) => root.path)
                .map((root) => ({
                  provider: root.provider,
                  path: root.path as string,
                  discovered: root.exists && root.readable,
                }))
            : [],
          lastSeenAt: machine.last_seen_at,
          eventCount: machine.event_count,
          note: `${machine.source_count.toLocaleString()} sources${sessionCount == null ? "" : ` · ${sessionCount.toLocaleString()} sessions`}`,
        } satisfies SetupMachine;
      });
    }
    if (!setupStatus) return [];
    const syncing = Boolean(
      progress &&
        ["queued", "scanning", "syncing", "deriving", "refreshing", "embedding", "cancelling"].includes(
          progress.status,
        ),
    );
    return [
      {
        id: setupStatus.machine.id,
        name: setupStatus.machine.name,
        platform: setupStatus.machine.hostname,
        status: syncing ? "syncing" : setupStatus.database.available ? "current" : "needs-setup",
        sourceRoots: setupStatus.roots
          .filter((root) => root.path)
          .map((root) => ({
            provider: root.provider,
            path: root.path as string,
            discovered: root.exists && root.readable,
          })),
        lastSeenAt: setupStatus.generated_at,
        note: setupStatus.database.error,
      },
    ];
  }, [machineRegistry?.machines, preview?.machines, progress, setupStatus]);

  const connection = useMemo<SetupConnection | null>(() => {
    if (!connectionResponse) return null;
    return {
      centralMachine: connectionResponse.central_machine,
      web: connectionResponse.web,
      database: {
        localEndpoint: connectionResponse.database.local_endpoint,
        writerEndpoint: connectionResponse.database.writer_endpoint,
        remoteReady: connectionResponse.database.remote_ready,
      },
      tailscale: {
        connected: connectionResponse.tailscale.connected,
        ipv4: connectionResponse.tailscale.ipv4,
        dnsName: connectionResponse.tailscale.dns_name,
      },
      networkScan: connectionResponse.network_scan,
      warnings: connectionResponse.warnings,
    };
  }, [connectionResponse]);

  async function previewBuild(config: SetupConfig) {
    const result = await api<SetupPreviewResponse>("/api/setup/preview", {
      method: "POST",
      body: JSON.stringify(requestBody(config)),
    });
    setPreview(result);
    return estimateFromPreview(result);
  }

  async function startBuild(config: SetupConfig) {
    const next = await api<SetupProgress>("/api/setup/build", {
      method: "POST",
      body: JSON.stringify(requestBody(config)),
    });
    setProgress(next);
  }

  async function cancelBuild() {
    const next = await api<SetupProgress>("/api/setup/build", { method: "DELETE" });
    setProgress(next);
  }

  async function downloadEmbeddingModel(presetId: string) {
    await api<EmbeddingModelStatus>(`/api/setup/embedding-models/${encodeURIComponent(presetId)}/download`, {
      method: "POST",
    });
    refreshEmbeddingModels();
  }

  async function refreshMachines() {
    const result = await api<SetupMachinesResponse>("/api/setup/machines");
    setMachineRegistry(result);
    if (!result.available) throw new Error(result.error ?? result.message);
    return result.message;
  }

  async function runSummaries(provider: SummaryAgentId, days: number) {
    await api("/api/summary-agent", {
      method: "PUT",
      body: JSON.stringify({ provider }),
    });
    await api("/api/summary-agent/run", {
      method: "POST",
      body: JSON.stringify({ provider, days, limit: 40, per_project_limit: 3 }),
    });
    refreshSummaryAgent();
  }

  return (
    <SetupPage
      firstRun={Boolean(setupStatus && setupStatus.database.ingestion_complete === 0)}
      machines={machines}
      connection={connection}
      estimate={preview ? estimateFromPreview(preview) : null}
      progress={progress}
      embeddingModels={embeddingModels ?? []}
      onPreview={previewBuild}
      onStartBuild={startBuild}
      onCancelBuild={cancelBuild}
      onDownloadEmbeddingModel={downloadEmbeddingModel}
      onRefreshMachines={refreshMachines}
      onOpenInstructions={() =>
        window.open(
          "https://github.com/MiddleDistances/23-open-chat-reviewer/blob/main/docs/SETUP_AND_STORAGE.md",
          "_blank",
          "noopener,noreferrer",
        )
      }
      onOpenWriterInstructions={() =>
        window.open(
          "https://github.com/MiddleDistances/23-open-chat-reviewer/blob/main/docs/TAILSCALE_MULTI_MACHINE.md",
          "_blank",
          "noopener,noreferrer",
        )
      }
      summaryAgent={
        <SummaryAgentPanel
          status={summaryAgent}
          loading={summaryAgentLoading}
          error={summaryAgentError}
          onRun={runSummaries}
        />
      }
    />
  );
}
