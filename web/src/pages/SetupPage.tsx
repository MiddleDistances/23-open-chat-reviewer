import {
  BookOpen,
  CalendarDays,
  Check,
  ChevronRight,
  CloudCog,
  Database,
  Download,
  HardDrive,
  Info,
  LoaderCircle,
  Monitor,
  Play,
  Plus,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Badge,
  PageHeader,
  formatBytes,
  formatDate,
  formatDuration,
  formatNumber,
} from "../components/Common";
import {
  ConnectionOverview,
  WriterSetupGuide,
  type SetupConnection,
} from "./ConnectionGuide";
import AgentSetupGuide, { type AgentSetupGuideProps } from "./AgentSetupGuide";
import SourceRootEditor, { type SourceRootEditorProps } from "./SourceRootEditor";
import { useExperienceMode } from "../preferences";

export type SetupProvider = "codex" | "claude" | "gemini" | "opencode";

export interface SetupConfig {
  /** Inclusive lower bound. An empty value means the oldest available record. */
  historyStart: string;
  /** Inclusive upper bound. An empty value means the newest available record. */
  historyEnd: string;
  providers: SetupProvider[];
  includeGitMetadata: boolean;
  /** Keep exact encrypted provider payloads in the raw evidence archive. */
  preserveEncryptedReasoning: boolean;
  /** Make readable reasoning text eligible for lexical/full-text search. */
  includeReadableReasoningInSearch: boolean;
  /** Add readable reasoning text to the semantic/vector projection. */
  includeReasoningInProjection: boolean;
  /** Fixed server-reviewed embedding configuration used for the projection. */
  embeddingPreset: string;
}

export type EmbeddingModelState = "ready" | "not_downloaded" | "queued" | "downloading" | "failed" | "interrupted" | "unavailable";

export interface EmbeddingModelStatus {
  id: string;
  label: string;
  description: string;
  model_name: string;
  revision: string;
  dimensions: number;
  source_url: string;
  status: EmbeddingModelState;
  message: string;
  error?: string | null;
}

export interface SetupSourceRoot {
  provider: SetupProvider | "git";
  path: string;
  discovered?: boolean;
  recordCount?: number;
}

export type SetupMachineStatus = "current" | "connected" | "needs-setup" | "offline" | "syncing";

export interface SetupMachine {
  id: string;
  name: string;
  status: SetupMachineStatus;
  platform?: string | null;
  sourceRoots: SetupSourceRoot[];
  lastSeenAt?: string | null;
  eventCount?: number | null;
  note?: string | null;
}

export interface SetupEstimate {
  sourceCount?: number;
  sessionCount?: number;
  eventCount?: number;
  rawBytes?: number;
  encryptedReasoningBytes?: number;
  readableReasoningBytes?: number;
  semanticBytes?: number;
  semanticWindowCount?: number;
  totalBytes?: number;
  estimatedSeconds?: number | null;
  note?: string | null;
}

export type SetupProgressStatus =
  | "idle"
  | "queued"
  | "scanning"
  | "syncing"
  | "deriving"
  | "refreshing"
  | "embedding"
  | "cancelling"
  | "complete"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface SetupProgress {
  status: SetupProgressStatus;
  phase?: string | null;
  message?: string | null;
  completed?: number | null;
  total?: number | null;
  percent?: number | null;
  estimatedSecondsRemaining?: number | null;
  startedAt?: string | null;
  updatedAt?: string | null;
  error?: string | null;
}

export interface SetupPageProps {
  /** Initial values for the local setup form. Omitted values use the safe defaults below. */
  initialConfig?: Partial<SetupConfig>;
  machines?: SetupMachine[];
  connection?: SetupConnection | null;
  estimate?: SetupEstimate | null;
  progress?: SetupProgress | null;
  embeddingModels?: EmbeddingModelStatus[];
  /** Called whenever a form value changes, so the host can persist a draft. */
  onChange?: (config: SetupConfig) => void;
  /** May return an estimate so a host can remain endpoint-agnostic. */
  onPreview?: (config: SetupConfig) => SetupEstimate | void | Promise<SetupEstimate | void>;
  onStartBuild?: (config: SetupConfig) => void | Promise<void>;
  onCancelBuild?: () => void | Promise<void>;
  onDownloadEmbeddingModel?: (presetId: string) => void | Promise<void>;
  /** Re-read machines registered in the shared archive; this is never a network scan. */
  onRefreshMachines?: () => string | void | Promise<string | void>;
  onSelectMachine?: (machineId: string) => void;
  onOpenInstructions?: () => void;
  onOpenWriterInstructions?: () => void;
  /** Optional machine-local summary-agent controls owned by the API route. */
  summaryAgent?: ReactNode;
  /** Optional provider discovery/save/test seams owned by the API route. */
  agentSetup?: Omit<AgentSetupGuideProps, "currentMachineName">;
  /** Machine-local multi-folder configuration owned by the API route. */
  sourceRootSetup?: SourceRootEditorProps;
}

export const DEFAULT_SETUP_CONFIG: SetupConfig = {
  ...quickRangePatch("7d"),
  providers: ["codex", "claude", "gemini", "opencode"],
  includeGitMetadata: true,
  // Exact evidence is retained by default; the two derived search controls are opt-in.
  preserveEncryptedReasoning: true,
  includeReadableReasoningInSearch: false,
  includeReasoningInProjection: false,
  embeddingPreset: "qwen3-embedding-0.6b",
};

export const SETUP_ACTION_IDS = {
  openGuide: "setup.guide.open",
  openWriterGuide: "setup.guide.writer",
  addMachine: "setup.machine.add",
  refreshMachines: "setup.machine.refresh",
  previewBuild: "setup.build.preview",
  startBuild: "setup.build.start",
  cancelBuild: "setup.build.cancel",
  downloadEmbeddingModel: "setup.embedding.download",
} as const;

type SetupAction = "preview" | "start" | "cancel" | "refresh-machines" | "instructions" | "download-model";

interface ActionFeedback {
  actionId: string;
  status: "pending" | "success" | "error";
  message: string;
}

const PROVIDERS: Array<{ value: SetupProvider; label: string }> = [
  { value: "codex", label: "Codex" },
  { value: "claude", label: "Claude" },
  { value: "gemini", label: "Gemini" },
  { value: "opencode", label: "OpenCode" },
];

const QUICK_RANGES = [
  { label: "Last 7 days", value: "7d" },
  { label: "Last 30 days", value: "30d" },
  { label: "Last 90 days", value: "90d" },
  { label: "All available", value: "all" },
] as const;

export default function SetupPage({
  initialConfig,
  machines = [],
  connection = null,
  estimate = null,
  progress = null,
  embeddingModels = [],
  onChange,
  onPreview,
  onStartBuild,
  onCancelBuild,
  onDownloadEmbeddingModel,
  onRefreshMachines,
  onSelectMachine,
  onOpenInstructions,
  onOpenWriterInstructions,
  summaryAgent,
  agentSetup,
  sourceRootSetup,
}: SetupPageProps) {
  const [experienceMode] = useExperienceMode();
  const isAdvanced = experienceMode === "advanced";
  const [config, setConfig] = useState<SetupConfig>(() => ({
    ...DEFAULT_SETUP_CONFIG,
    ...initialConfig,
  }));
  const [previewEstimate, setPreviewEstimate] = useState<SetupEstimate | null>(null);
  const [action, setAction] = useState<SetupAction | null>(null);
  const [feedback, setFeedback] = useState<ActionFeedback | null>(null);
  const [showMachineSetup, setShowMachineSetup] = useState(false);

  const displayedEstimate = previewEstimate ?? estimate;
  const selectedEmbeddingModel = embeddingModels.find((model) => model.id === config.embeddingPreset) ?? embeddingModels[0];
  const embeddingDownloadActive = selectedEmbeddingModel?.status === "queued" || selectedEmbeddingModel?.status === "downloading";
  const embeddingBlocked = Boolean(selectedEmbeddingModel && selectedEmbeddingModel.status !== "ready");
  const isRunning = Boolean(
    progress &&
      ["queued", "scanning", "syncing", "deriving", "refreshing", "embedding", "cancelling"].includes(
        progress.status,
      ),
  );

  function updateConfig(patch: Partial<SetupConfig>) {
    const next = { ...config, ...patch };
    setConfig(next);
    setPreviewEstimate(null);
    onChange?.(next);
  }

  async function runAction(
    name: SetupAction,
    actionId: string,
    callback: (() => string | void | Promise<string | void>) | undefined,
    pendingMessage: string,
    successMessage: string,
  ) {
    if (!callback) return;
    setAction(name);
    setFeedback({ actionId, status: "pending", message: pendingMessage });
    try {
      const result = await callback();
      setFeedback({ actionId, status: "success", message: result || successMessage });
    } catch (reason) {
      setFeedback({
        actionId,
        status: "error",
        message: reason instanceof Error ? reason.message : String(reason),
      });
    } finally {
      setAction(null);
    }
  }

  async function preview() {
    if (!onPreview) return;
    setAction("preview");
    setFeedback({
      actionId: SETUP_ACTION_IDS.previewBuild,
      status: "pending",
      message: "Calculating the selected archive scope and storage estimate…",
    });
    try {
      const nextEstimate = await onPreview(config);
      if (nextEstimate) setPreviewEstimate(nextEstimate);
      setFeedback({
        actionId: SETUP_ACTION_IDS.previewBuild,
        status: "success",
        message: "Build estimate is ready. Review it below before starting.",
      });
    } catch (reason) {
      setFeedback({
        actionId: SETUP_ACTION_IDS.previewBuild,
        status: "error",
        message: reason instanceof Error ? reason.message : String(reason),
      });
    } finally {
      setAction(null);
    }
  }

  async function downloadEmbedding() {
    if (!selectedEmbeddingModel || !onDownloadEmbeddingModel) return;
    await runAction(
      "download-model",
      SETUP_ACTION_IDS.downloadEmbeddingModel,
      () => onDownloadEmbeddingModel(selectedEmbeddingModel.id),
      "Starting the model download…",
      "Model download started. You can leave this page while it completes.",
    );
  }

  return (
    <div className="setup-page">
      <PageHeader eyebrow="System" title="Archive setup">
        <button
          className="button"
          id="setup-open-guide"
          data-action-id={SETUP_ACTION_IDS.openGuide}
          type="button"
          disabled={!onOpenInstructions || action === "instructions"}
          onClick={() => void runAction(
            "instructions",
            SETUP_ACTION_IDS.openGuide,
            onOpenInstructions,
            "Opening the setup guide…",
            "Setup guide opened in a new tab.",
          )}
        >
          <BookOpen size={15} aria-hidden="true" /> Read setup guide
        </button>
      </PageHeader>

      {feedback ? <ActionNotice feedback={feedback} /> : null}

      <section className="panel setup-section setup-machines" id="setup-section-machines" aria-labelledby="setup-machines-title">
        <SectionHeading step="01" eyebrow="Source computers" title="Connect the machines that own the chats" id="setup-machines-title">
          Computers appear after their first sync. This page checks the shared archive; it does not scan your network.
        </SectionHeading>
        <div className="setup-machine-list" aria-live="polite">
          {machines.map((machine) => {
            const machineDetails = [
              machine.platform && machine.platform !== machine.name ? machine.platform : null,
              machine.note,
            ].filter(Boolean).join(" · ");
            const folderCount = machine.sourceRoots.length;
            const content = <>
              <span className="setup-machine-icon"><Monitor size={18} aria-hidden="true" /></span>
              <span className="setup-machine-copy">
                <strong>{machine.name}</strong>
                <small>{machineDetails || (machine.status === "current" ? "This computer" : "Other computer")}</small>
                <span className="setup-machine-roots">
                  {folderCount
                    ? `${folderCount} source folder${folderCount === 1 ? "" : "s"} configured`
                    : machine.status === "current" || machine.status === "needs-setup"
                      ? "No source folders configured on this computer"
                      : "Folders are managed on that computer"}
                </span>
              </span>
              <span className="setup-machine-meta">
                <Badge tone={machineTone(machine.status)}>{machineStatusLabel(machine.status)}</Badge>
                {machine.eventCount != null ? <small>{formatNumber(machine.eventCount)} events</small> : null}
                {machine.lastSeenAt ? <small>Seen {formatDate(machine.lastSeenAt, true)}</small> : null}
              </span>
              {onSelectMachine ? <ChevronRight size={16} aria-hidden="true" /> : null}
            </>;
            return onSelectMachine ? (
              <button
                className="setup-machine-card"
                id={`setup-machine-${machine.id}`}
                data-action-id="setup.machine.select"
                data-machine-id={machine.id}
                type="button"
                key={machine.id}
                onClick={() => onSelectMachine(machine.id)}
              >
                {content}
              </button>
            ) : (
              <div className="setup-machine-card" key={machine.id}>{content}</div>
            );
          })}
          {machines.length === 0 ? (
            <div className="setup-empty-card">
              <CloudCog size={21} aria-hidden="true" />
              <div><strong>Start with this computer</strong><p>Choose its source folders below, then run the first build.</p></div>
            </div>
          ) : null}
        </div>
        <div className="setup-section-actions">
          <button
            className="button button-primary"
            id="setup-add-machine"
            data-action-id={SETUP_ACTION_IDS.addMachine}
            type="button"
            aria-expanded={showMachineSetup}
            onClick={() => {
              const show = !showMachineSetup;
              setShowMachineSetup(show);
              setFeedback(show ? {
                actionId: SETUP_ACTION_IDS.addMachine,
                status: "success",
                message: "Connection steps opened. No network scan is running.",
              } : null);
            }}
          >
            {showMachineSetup ? <ChevronRight className="setup-disclosure-icon open" size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
            {showMachineSetup ? "Hide connection steps" : "Connect another machine"}
          </button>
        </div>
        {showMachineSetup ? (
          <WriterSetupGuide
            connection={connection}
            checking={action === "refresh-machines"}
            guideAvailable={Boolean(onOpenWriterInstructions)}
            refreshAvailable={Boolean(onRefreshMachines)}
            onOpenGuide={() => void runAction(
              "instructions",
              SETUP_ACTION_IDS.openWriterGuide,
              onOpenWriterInstructions,
              "Opening the writer setup guide…",
              "Writer setup guide opened in a new tab.",
            )}
            onRefresh={() => void runAction(
              "refresh-machines",
              SETUP_ACTION_IDS.refreshMachines,
              onRefreshMachines,
              "Checking machine registrations in the shared archive…",
              "Shared archive checked. New machines appear after their first writer sync.",
            )}
          />
        ) : null}
      </section>

      <details className="panel setup-disclosure">
        <summary id="setup-connection-details" data-action-id="setup.connection.toggle">
          <span><strong>How machines connect</strong><small>Diagram and private connection addresses</small></span>
          <ChevronRight className="setup-disclosure-icon" size={16} aria-hidden="true" />
        </summary>
        <ConnectionOverview connection={connection} machines={machines} />
      </details>

      <div className={isAdvanced ? "setup-two-column" : undefined}>
        <section className="panel setup-section" id="setup-section-history" aria-labelledby="setup-history-title">
          <SectionHeading step="02" eyebrow="History and sources" title="Choose what to process" id="setup-history-title">
            Start with a short range. You can process more history later.
          </SectionHeading>
          <div className="setup-quick-ranges" role="group" aria-label="History presets">
            {QUICK_RANGES.map((range) => {
              const selected = rangeSelected(range.value, config);
              return <button className={selected ? "active" : ""} id={`setup-range-${range.value}`} data-action-id={`setup.scope.range.${range.value}`} type="button" aria-pressed={selected} key={range.value} onClick={() => applyQuickRange(range.value, updateConfig)}>{range.label}</button>;
            })}
          </div>
          <div className="setup-date-grid">
            <label><span>From</span><input type="date" aria-label="History start date" value={config.historyStart} onChange={(event) => updateConfig({ historyStart: event.target.value })} /></label>
            <label><span>Through</span><input type="date" aria-label="History end date" value={config.historyEnd} onChange={(event) => updateConfig({ historyEnd: event.target.value })} /></label>
          </div>
          <p className="setup-field-help"><CalendarDays size={14} aria-hidden="true" /> Leave both dates empty to process all available history.</p>
          <fieldset className="setup-choice-fieldset">
            <legend>Sources on this computer</legend>
            <p className="setup-field-help">Choose which archives to include.</p>
            <div className="setup-provider-grid">
              {PROVIDERS.map((provider) => (
                <label className="setup-choice-card" key={provider.value}>
                  <input id={`setup-source-${provider.value}`} type="checkbox" checked={config.providers.includes(provider.value)} onChange={(event) => updateProviders(provider.value, event.target.checked, config, updateConfig)} />
                  <span><strong>{provider.label}</strong></span>
                </label>
              ))}
              <label className="setup-choice-card">
                <input id="setup-source-git" type="checkbox" checked={config.includeGitMetadata} onChange={(event) => updateConfig({ includeGitMetadata: event.target.checked })} />
                <span><strong>Git metadata</strong><small>No file contents</small></span>
              </label>
            </div>
          </fieldset>
          {sourceRootSetup ? (
            <SourceRootEditor
              key={sourceRootSetup.roots.map((root) => `${root.provider}:${root.path ?? ""}`).join("|")}
              {...sourceRootSetup}
            />
          ) : null}
        </section>

        {isAdvanced ? <section className="panel setup-section" id="setup-section-policy" aria-labelledby="setup-policy-title">
          <SectionHeading step="A" eyebrow="Optional" title="Reasoning settings" id="setup-policy-title">
            Choose whether readable reasoning can be searched or shown on the semantic map.
          </SectionHeading>
          <fieldset className="setup-policy-list">
            <legend className="sr-only">Reasoning retention and indexing policy</legend>
            <PolicyChoice
              checked={config.preserveEncryptedReasoning}
              onChange={(checked) => updateConfig({ preserveEncryptedReasoning: checked })}
              icon={<Database size={17} aria-hidden="true" />}
              title="Keep raw reasoning data"
              description="Retain provider payloads for audit and replay."
              badge="Stored"
            />
            <PolicyChoice
              checked={config.includeReadableReasoningInSearch}
              onChange={(checked) => updateConfig({ includeReadableReasoningInSearch: checked })}
              icon={<HardDrive size={17} aria-hidden="true" />}
              title="Search readable reasoning"
              description="Include readable reasoning summaries in text search."
              badge="Searchable"
            />
            <PolicyChoice
              checked={config.includeReasoningInProjection}
              onChange={(checked) => updateConfig({ includeReasoningInProjection: checked })}
              icon={<Sparkles size={17} aria-hidden="true" />}
              title="Map readable reasoning"
              description="Include readable reasoning summaries in the semantic map."
              badge="Mapped"
            />
          </fieldset>
          <div className="setup-policy-note"><ShieldCheck size={15} aria-hidden="true" /><span>Encrypted reasoning cannot be searched or embedded.</span></div>
        </section> : null}
      </div>

      {isAdvanced && embeddingModels.length > 0 ? (
        <div className="panel setup-embedding-model" role="group" aria-label="Semantic map model">
          <div className="setup-embedding-copy">
            <Sparkles size={18} aria-hidden="true" />
            <div>
              <strong>Semantic map model</strong>
              <span>Runs locally. Hugging Face is used only to download model files.</span>
            </div>
          </div>
          <label>
            <span className="sr-only">Embedding model preset</span>
            <select aria-label="Embedding model preset" value={config.embeddingPreset} onChange={(event) => updateConfig({ embeddingPreset: event.target.value })}>
              {embeddingModels.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
            </select>
          </label>
          {selectedEmbeddingModel && (
            <div className="setup-embedding-status">
              <div>
                <strong>{selectedEmbeddingModel.model_name}</strong>
                <small>{selectedEmbeddingModel.description}</small>
                <span className={`freshness freshness-${selectedEmbeddingModel.status === "ready" ? "fresh" : "stale"}`}>{embeddingModelStatusLabel(selectedEmbeddingModel.status)}</span>
                <small role={selectedEmbeddingModel.status === "failed" ? "alert" : undefined}>{selectedEmbeddingModel.error || selectedEmbeddingModel.message}</small>
              </div>
              {selectedEmbeddingModel.status !== "ready" && (
                <button
                  className="button"
                  id="setup-download-embedding-model"
                  data-action-id={SETUP_ACTION_IDS.downloadEmbeddingModel}
                  type="button"
                  onClick={() => void downloadEmbedding()}
                  disabled={!onDownloadEmbeddingModel || embeddingDownloadActive || selectedEmbeddingModel.status === "unavailable"}
                >
                  {embeddingDownloadActive ? <LoaderCircle className="setup-spin" size={15} aria-hidden="true" /> : <Download size={15} aria-hidden="true" />}
                  {embeddingDownloadActive ? "Downloading…" : "Download model"}
                </button>
              )}
              <a href={selectedEmbeddingModel.source_url} target="_blank" rel="noreferrer">View model card</a>
            </div>
          )}
        </div>
      ) : null}

      <section className="panel setup-section setup-build" id="setup-section-build" aria-labelledby="setup-build-title">
        {!isAdvanced && selectedEmbeddingModel && embeddingBlocked ? (
          <div className="setup-model-blocker" role="status">
            <span><strong>Semantic map model needed</strong><small>Download the local model before starting the first build.</small></span>
            <button
              className="button"
              id="setup-download-embedding-model"
              data-action-id={SETUP_ACTION_IDS.downloadEmbeddingModel}
              type="button"
              onClick={() => void downloadEmbedding()}
              disabled={!onDownloadEmbeddingModel || embeddingDownloadActive || selectedEmbeddingModel.status === "unavailable"}
            >
              {embeddingDownloadActive ? <LoaderCircle className="setup-spin" size={15} aria-hidden="true" /> : <Download size={15} aria-hidden="true" />}
              {embeddingDownloadActive ? "Downloading…" : "Download model"}
            </button>
          </div>
        ) : null}
        <div className="setup-build-header">
          <SectionHeading step="03" eyebrow="Archive build" title="Review and build" id="setup-build-title">
            Check the selected records and storage estimate before starting.
          </SectionHeading>
          <div className="setup-build-actions">
            <button className="button" id="setup-preview-build" data-action-id={SETUP_ACTION_IDS.previewBuild} type="button" onClick={() => void preview()} disabled={!onPreview || action === "preview" || isRunning}>
              {action === "preview" ? <LoaderCircle className="setup-spin" size={15} aria-hidden="true" /> : <HardDrive size={15} aria-hidden="true" />}
              {action === "preview" ? "Calculating…" : "Preview estimate"}
            </button>
            <button className="button button-primary" id="setup-start-build" data-action-id={SETUP_ACTION_IDS.startBuild} type="button" onClick={() => void runAction(
              "start",
              SETUP_ACTION_IDS.startBuild,
              onStartBuild ? () => onStartBuild(config) : undefined,
              "Starting the archive build…",
              "Archive build started. Live progress is shown below.",
            )} disabled={!onStartBuild || isRunning || config.providers.length === 0 || embeddingBlocked}>
              <Play size={15} aria-hidden="true" /> {isRunning ? "Build in progress" : "Start archive build"}
            </button>
          </div>
        </div>

        <EstimateSummary estimate={displayedEstimate} reasoningIncluded={config.includeReasoningInProjection} />
        <BuildProgress progress={progress} onCancel={onCancelBuild ? () => void runAction(
          "cancel",
          SETUP_ACTION_IDS.cancelBuild,
          onCancelBuild,
          "Requesting a safe stop…",
          "Stop requested. The current command will exit safely.",
        ) : undefined} cancelling={action === "cancel"} />
      </section>

      {summaryAgent}

      {agentSetup ? (
        <details className="panel setup-disclosure" id="setup-summary-provider-disclosure">
          <summary id="setup-summary-provider-details" data-action-id="setup.summary-provider.toggle">
            <span><strong>Configure a summary provider</strong><small>Use a CLI, local or network GPU, or API endpoint</small></span>
            <ChevronRight className="setup-disclosure-icon" size={16} aria-hidden="true" />
          </summary>
          <AgentSetupGuide currentMachineName={connection?.centralMachine.name} {...agentSetup} />
        </details>
      ) : null}

      {isAdvanced ? (
        <details className="panel setup-maintenance">
          <summary>Maintenance</summary>
          <p>Optional service and agent commands. Credentials remain in the ignored <code>.chatreview</code> directory.</p>
          <div className="setup-maintenance-grid">
            <div><strong>Back up</strong><code>scripts/backup.sh</code></div>
            <div><strong>Update</strong><code>scripts/update.sh</code></div>
            <div><strong>Remove services</strong><code>scripts/uninstall.sh</code></div>
            <div><strong>Read-only MCP</strong><code>uv sync --extra mcp</code></div>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function ActionNotice({ feedback }: { feedback: ActionFeedback }) {
  const Icon = feedback.status === "pending" ? LoaderCircle : feedback.status === "success" ? Check : TriangleAlert;
  return (
    <div
      className={`setup-action-notice ${feedback.status}`}
      role={feedback.status === "error" ? "alert" : "status"}
      aria-live="polite"
      data-action-id={feedback.actionId}
    >
      <Icon className={feedback.status === "pending" ? "setup-spin" : undefined} size={16} aria-hidden="true" />
      <span>{feedback.message}</span>
    </div>
  );
}

function SectionHeading({ step, eyebrow, title, id, children }: { step: string; eyebrow: string; title: string; id: string; children: ReactNode }) {
  return <div className="setup-section-heading"><div className="setup-section-number">{step}</div><div><span className="eyebrow">{eyebrow}</span><h2 id={id}>{title}</h2><p>{children}</p></div></div>;
}

function PolicyChoice({ checked, onChange, icon, title, description, badge }: { checked: boolean; onChange: (checked: boolean) => void; icon: ReactNode; title: string; description: string; badge: string }) {
  return <label className={`setup-policy-choice ${checked ? "selected" : ""}`}><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span className="setup-policy-icon">{icon}</span><span className="setup-policy-copy"><strong>{title}</strong><small>{description}</small></span><Badge tone={checked ? "success" : "neutral"}>{checked ? <><Check size={11} aria-hidden="true" /> {badge}</> : "Excluded"}</Badge></label>;
}

function EstimateSummary({ estimate, reasoningIncluded }: { estimate: SetupEstimate | null; reasoningIncluded: boolean }) {
  if (!estimate) return <div className="setup-estimate-empty"><HardDrive size={19} aria-hidden="true" /><div><strong>No estimate yet</strong><p>Select “Preview estimate” to check records, storage, and semantic windows.</p></div></div>;
  const total = estimate.totalBytes ?? estimate.rawBytes ?? 0;
  const reasoning = estimate.encryptedReasoningBytes ?? 0;
  const reasoningShare = total > 0 ? Math.round((reasoning / total) * 100) : 0;
  return <div className="setup-estimate" aria-label="Build estimate"><div className="setup-estimate-total"><span>Estimated storage</span><strong>{formatBytes(total)}</strong><small>{estimate.estimatedSeconds != null ? `about ${formatDuration(estimate.estimatedSeconds)}` : "duration will be measured during the build"}</small></div><div className="setup-estimate-metrics"><EstimateMetric label="Sources" value={estimate.sourceCount} /><EstimateMetric label="Sessions" value={estimate.sessionCount} /><EstimateMetric label="Events" value={estimate.eventCount} /><EstimateMetric label="Semantic windows" value={estimate.semanticWindowCount} /><EstimateMetric label="Encrypted reasoning" value={estimate.encryptedReasoningBytes} bytes /><EstimateMetric label="Readable reasoning" value={estimate.readableReasoningBytes} bytes /></div><div className="setup-estimate-breakdown"><div className="setup-estimate-bar" role="img" aria-label={`${reasoningShare}% of estimated storage is encrypted reasoning`}><span style={{ width: `${Math.min(100, reasoningShare)}%` }} /></div><span>{reasoningShare}% encrypted reasoning{reasoningIncluded ? "; semantic reasoning is included" : "; semantic reasoning is excluded"}</span></div>{estimate.note ? <p className="setup-field-help"><Info size={14} aria-hidden="true" /> {estimate.note}</p> : null}</div>;
}

function EstimateMetric({ label, value, suffix = "", bytes = false }: { label: string; value?: number; suffix?: string; bytes?: boolean }) {
  return <div><span>{label}</span><strong>{value == null ? "—" : bytes ? formatBytes(value) : `${formatNumber(value)}${suffix}`}</strong></div>;
}

function BuildProgress({ progress, onCancel, cancelling }: { progress: SetupProgress | null; onCancel?: () => void; cancelling: boolean }) {
  if (!progress || progress.status === "idle") return null;
  const percent = progressPercent(progress);
  const failed = progress.status === "failed" || progress.status === "interrupted";
  const complete = progress.status === "complete";
  const terminal = complete || failed || progress.status === "cancelled";
  return <div className={`setup-progress ${failed ? "failed" : complete ? "complete" : "active"}`} aria-labelledby="setup-progress-title"><div className="setup-progress-header"><div><span className="eyebrow">Build status</span><h3 id="setup-progress-title">{progressLabel(progress)}</h3></div><strong>{Math.round(percent)}%</strong></div><div className="setup-progress-track" role="progressbar" aria-label="Archive build progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{ width: `${percent}%` }} /></div><div className="setup-progress-meta"><span>{progress.message ?? progress.phase ?? (failed ? "The build stopped with an error." : complete ? "The archive and selected projections are current." : "Preparing the next phase…")}</span>{progress.estimatedSecondsRemaining != null && !terminal ? <span>{formatDuration(progress.estimatedSecondsRemaining)} remaining</span> : null}{onCancel && !terminal ? <button className="text-button" id="setup-cancel-build" data-action-id={SETUP_ACTION_IDS.cancelBuild} type="button" onClick={onCancel} disabled={cancelling}>{cancelling ? "Stopping…" : "Stop build"}</button> : null}</div>{failed && progress.error ? <p className="setup-progress-error"><TriangleAlert size={14} aria-hidden="true" /> {progress.error}</p> : null}{progress.startedAt ? <small className="setup-progress-time">Started {formatDate(progress.startedAt, true)}</small> : null}</div>;
}

function progressPercent(progress: SetupProgress): number {
  if (progress.percent != null) return clamp(progress.percent, 0, 100);
  if (progress.completed != null && progress.total) return clamp((progress.completed / progress.total) * 100, 0, 100);
  return progress.status === "complete" ? 100 : 0;
}

function progressLabel(progress: SetupProgress | null): string {
  if (!progress || progress.status === "idle") return "Ready to configure";
  if (progress.status === "complete") return "Archive current";
  if (progress.status === "failed" || progress.status === "interrupted") return "Build needs attention";
  if (progress.status === "cancelled") return "Build cancelled";
  if (progress.status === "queued") return "Queued";
  return progress.phase || progress.status.charAt(0).toUpperCase() + progress.status.slice(1);
}

function machineStatusLabel(status: SetupMachineStatus): string {
  return status === "needs-setup" ? "Needs setup" : status.charAt(0).toUpperCase() + status.slice(1);
}

function machineTone(status: SetupMachineStatus): string {
  if (status === "current" || status === "connected") return "success";
  if (status === "syncing") return "partial";
  if (status === "offline") return "danger";
  return "neutral";
}

function rangeSelected(value: (typeof QUICK_RANGES)[number]["value"], config: SetupConfig): boolean {
  if (value === "all") return !config.historyStart && !config.historyEnd;
  const expected = quickRangePatch(value);
  return config.historyStart === expected.historyStart && config.historyEnd === expected.historyEnd;
}

function applyQuickRange(value: (typeof QUICK_RANGES)[number]["value"], update: (patch: Partial<SetupConfig>) => void) {
  update(quickRangePatch(value));
}

function quickRangePatch(value: (typeof QUICK_RANGES)[number]["value"]): Pick<SetupConfig, "historyStart" | "historyEnd"> {
  if (value === "all") return { historyStart: "", historyEnd: "" };
  const start = new Date();
  if (value === "7d") start.setDate(start.getDate() - 7);
  if (value === "30d") start.setDate(start.getDate() - 30);
  if (value === "90d") start.setDate(start.getDate() - 90);
  return { historyStart: toInputDate(start), historyEnd: todayInputValue() };
}

function updateProviders(provider: SetupProvider, included: boolean, config: SetupConfig, update: (patch: Partial<SetupConfig>) => void) {
  const providers = included ? [...new Set([...config.providers, provider])] : config.providers.filter((item) => item !== provider);
  update({ providers });
}

function todayInputValue(): string {
  return toInputDate(new Date());
}

function toInputDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function embeddingModelStatusLabel(status: EmbeddingModelState): string {
  if (status === "ready") return "Ready on this machine";
  if (status === "not_downloaded") return "Download required";
  if (status === "queued") return "Download queued";
  if (status === "downloading") return "Downloading";
  if (status === "failed") return "Download failed";
  if (status === "interrupted") return "Download interrupted";
  return "Semantic dependencies required";
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}
