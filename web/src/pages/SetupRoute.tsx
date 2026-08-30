import { useEffect, useMemo, useState } from "react";
import { api, useApi } from "../api";
import SetupPage, {
  type SetupConfig,
  type SetupEstimate,
  type SetupMachine,
  type SetupProgress,
} from "./SetupPage";

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

function requestBody(config: SetupConfig) {
  return {
    history_start: config.historyStart || null,
    history_end: config.historyEnd || null,
    providers: config.providers,
    include_git_metadata: config.includeGitMetadata,
    preserve_encrypted_reasoning: config.preserveEncryptedReasoning,
    include_readable_reasoning_in_search: config.includeReadableReasoningInSearch,
    include_reasoning_in_projection: config.includeReasoningInProjection,
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
  const { data: progress, setData: setProgress } =
    useApi<SetupProgress>("/api/setup/build");
  const [preview, setPreview] = useState<SetupPreviewResponse | null>(null);

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

  const machines = useMemo<SetupMachine[]>(() => {
    if (preview?.machines.length) {
      return preview.machines.map((machine) => ({
        id: machine.machine_id,
        name: machine.name,
        status: machine.machine_id === setupStatus?.machine.id ? "current" : "connected",
        sourceRoots: [],
        lastSeenAt: machine.last_seen_at,
        eventCount: machine.event_count,
        note: `${machine.source_count.toLocaleString()} sources`,
      }));
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
  }, [preview?.machines, progress, setupStatus]);

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

  return (
    <SetupPage
      machines={machines}
      estimate={preview ? estimateFromPreview(preview) : null}
      progress={progress}
      onPreview={previewBuild}
      onStartBuild={startBuild}
      onCancelBuild={cancelBuild}
      onDiscoverMachine={() => refreshStatus()}
      onOpenInstructions={() =>
        window.open(
          "https://github.com/MiddleDistances/23-open-chat-reviewer/blob/main/docs/SETUP_AND_STORAGE.md",
          "_blank",
          "noopener,noreferrer",
        )
      }
    />
  );
}
