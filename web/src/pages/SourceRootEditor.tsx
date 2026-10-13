import { ChevronDown, FolderCog, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

export type SourceRootProvider = "codex" | "claude" | "gemini" | "git";

export interface SourceRootStatus {
  provider: SourceRootProvider;
  path: string | null;
  exists: boolean;
  readable: boolean;
  issue?: string | null;
}

export interface SourceRootValue {
  provider: SourceRootProvider;
  path: string;
}

export interface SourceRootEditorProps {
  /** The paths discovered on the current machine. They are never used for another machine. */
  roots: SourceRootStatus[];
  /** Browser-side saving is deliberately opt-in because paths are machine-local. */
  actionsEnabled?: boolean;
  actionsMessage?: string;
  onSave?: (roots: SourceRootValue[]) => void | Promise<void>;
}

interface ProviderDetails {
  id: SourceRootProvider;
  label: string;
  description: string;
  suggestion: string;
}

interface EditableRoot extends SourceRootValue {
  id: string;
  initialPath: string | null;
  initialStatus: SourceRootStatus | null;
}

const PROVIDERS: ProviderDetails[] = [
  {
    id: "codex",
    label: "Codex",
    description: "Conversation sessions",
    suggestion: "~/.codex",
  },
  {
    id: "claude",
    label: "Claude",
    description: "Conversation sessions",
    suggestion: "~/.claude",
  },
  {
    id: "gemini",
    label: "Gemini",
    description: "Conversation sessions",
    suggestion: "~/.gemini",
  },
  {
    id: "git",
    label: "Git metadata",
    description: "Repositories and commit metadata",
    suggestion: "Path to a repositories folder",
  },
];

function initialEntries(roots: SourceRootStatus[]): EditableRoot[] {
  const seen = new Set<string>();
  const entries: EditableRoot[] = [];

  roots.forEach((root, index) => {
    const path = root.path ?? "";
    const key = `${root.provider}\u0000${path}`;
    if (seen.has(key)) return;
    seen.add(key);
    entries.push({
      id: `${root.provider}-${index + 1}`,
      provider: root.provider,
      path,
      initialPath: path,
      initialStatus: path.trim() ? root : null,
    });
  });

  // Keep every source family visible, even on a new machine with no discovery yet.
  PROVIDERS.forEach(({ id }) => {
    if (entries.some((entry) => entry.provider === id)) return;
    entries.push({
      id: `${id}-default`,
      provider: id,
      path: "",
      initialPath: null,
      initialStatus: null,
    });
  });

  return entries;
}

function cleanRoots(entries: EditableRoot[]): SourceRootValue[] {
  const seen = new Set<string>();
  const cleaned: SourceRootValue[] = [];

  entries.forEach(({ provider, path }) => {
    const cleanPath = path.trim();
    if (!cleanPath) return;
    const key = `${provider}\u0000${cleanPath}`;
    if (seen.has(key)) return;
    seen.add(key);
    cleaned.push({ provider, path: cleanPath });
  });

  return cleaned;
}

function statusFor(entry: EditableRoot): "ready" | "missing" | null {
  if (!entry.initialStatus || entry.initialPath !== entry.path || !entry.path.trim()) return null;
  return entry.initialStatus.exists && entry.initialStatus.readable ? "ready" : "missing";
}

export default function SourceRootEditor({
  roots,
  actionsEnabled = true,
  actionsMessage,
  onSave,
}: SourceRootEditorProps) {
  const [expanded, setExpanded] = useState(false);
  const [entries, setEntries] = useState<EditableRoot[]>(() => initialEntries(roots));
  const [nextId, setNextId] = useState(1);
  const [saveState, setSaveState] = useState<"idle" | "pending" | "success" | "error">("idle");
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const canSave = actionsEnabled && Boolean(onSave);
  const configuredFolderCount = cleanRoots(entries).length;

  function addRoot(provider: SourceRootProvider) {
    if (!actionsEnabled) return;
    const id = `${provider}-custom-${nextId}`;
    setNextId((current) => current + 1);
    setEntries((current) => {
      const newEntry: EditableRoot = {
        id,
        provider,
        path: "",
        initialPath: null,
        initialStatus: null,
      };
      const lastProviderIndex = current.reduce(
        (lastIndex, entry, index) => (entry.provider === provider ? index : lastIndex),
        -1,
      );
      if (lastProviderIndex < 0) return [...current, newEntry];
      return [
        ...current.slice(0, lastProviderIndex + 1),
        newEntry,
        ...current.slice(lastProviderIndex + 1),
      ];
    });
  }

  function updatePath(id: string, path: string) {
    if (!actionsEnabled) return;
    setEntries((current) => current.map((entry) => (entry.id === id ? { ...entry, path } : entry)));
    setSaveState("idle");
    setSaveMessage(null);
  }

  function removeRoot(id: string) {
    if (!actionsEnabled) return;
    setEntries((current) => current.filter((entry) => entry.id !== id));
    setSaveState("idle");
    setSaveMessage(null);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSave || !onSave) return;

    setSaveState("pending");
    setSaveMessage("Saving source folders for this machine…");
    try {
      await onSave(cleanRoots(entries));
      setSaveState("success");
      setSaveMessage("Source folders saved. The next sync will use these paths.");
    } catch (reason) {
      setSaveState("error");
      setSaveMessage(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <section className="panel source-root-editor" aria-labelledby="source-root-editor-title">
      <div className="source-root-heading">
        <div className="source-root-title-wrap">
          <span className="source-root-icon"><FolderCog size={17} aria-hidden="true" /></span>
          <div>
            <h2 id="source-root-editor-title">Source folders</h2>
          </div>
          <span
            className="source-root-count"
          >
            {configuredFolderCount} configured
          </span>
        </div>
        <button
          className="button source-root-toggle"
          id="source-root-editor-toggle"
          data-action-id="setup.source-roots.toggle"
          type="button"
          aria-expanded={expanded}
          aria-controls="source-root-editor-form"
          onClick={() => setExpanded((current) => !current)}
        >
          <ChevronDown size={15} aria-hidden="true" />
          {expanded ? "Hide folders" : "Edit folders"}
        </button>
      </div>

      {expanded ? (
        <form className="source-root-form" id="source-root-editor-form" onSubmit={(event) => void save(event)}>
          <p className="source-root-intro">
            Paths apply only to this computer—add each folder that contains chats or repositories; removing one stops future syncs without deleting archived data.
          </p>
          <div className="source-root-groups">
            {PROVIDERS.map((provider) => {
              const providerEntries = entries.filter((entry) => entry.provider === provider.id);
              return (
                <fieldset className="source-root-provider" key={provider.id}>
                  <legend className="source-root-provider-heading">
                    <strong>{provider.label}</strong>
                    <small>{provider.description}</small>
                  </legend>
                  <div className="source-root-paths">
                    {providerEntries.map((entry, index) => {
                      const status = statusFor(entry);
                      const inputId = `source-root-path-${entry.id}`;
                      const statusId = `${inputId}-status`;
                      return (
                        <div className="source-root-path-row" key={entry.id}>
                          <label htmlFor={inputId}>{provider.label} folder {index + 1}</label>
                          <div className="source-root-path-input-wrap">
                            <input
                              id={inputId}
                              data-action-id={`setup.source-roots.${provider.id}.edit.${entry.id}`}
                              type="text"
                              value={entry.path}
                              placeholder={provider.suggestion}
                              autoComplete="off"
                              disabled={!actionsEnabled}
                              onChange={(event) => updatePath(entry.id, event.target.value)}
                              aria-describedby={status ? statusId : undefined}
                            />
                            {status ? (
                              <span
                                className={`source-root-status ${status}`}
                                id={statusId}
                                role="status"
                              >
                                {status === "ready" ? "Ready" : "Missing"}
                                {entry.initialStatus?.issue ? ` · ${entry.initialStatus.issue}` : ""}
                              </span>
                            ) : null}
                          </div>
                          <button
                            className="text-button source-root-remove"
                            id={`source-root-remove-${entry.id}`}
                            data-action-id={`setup.source-roots.${provider.id}.remove.${entry.id}`}
                            type="button"
                            disabled={!actionsEnabled}
                            aria-label={`Remove ${provider.label} folder ${index + 1}`}
                            onClick={() => removeRoot(entry.id)}
                          >
                            <Trash2 size={14} aria-hidden="true" />
                            Remove
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  <button
                    className="text-button source-root-add"
                    id={`source-root-add-${provider.id}`}
                    data-action-id={`setup.source-roots.${provider.id}.add`}
                    type="button"
                    disabled={!actionsEnabled}
                    onClick={() => addRoot(provider.id)}
                  >
                    <Plus size={14} aria-hidden="true" />
                    {provider.id === "git" ? "Add Git folder" : `Add ${provider.label} folder`}
                  </button>
                </fieldset>
              );
            })}
          </div>

          {!canSave ? (
            <p className="source-root-save-explanation">
              {actionsMessage ?? "Saving is available only from the machine that owns these folders."}
            </p>
          ) : null}

          <div className="source-root-actions">
            <button
              className="button button-primary source-root-save"
              id="source-root-save"
              data-action-id="setup.source-roots.save"
              type="submit"
              disabled={!canSave || saveState === "pending"}
            >
              {saveState === "pending" ? "Saving…" : "Save folders"}
            </button>
          </div>

          {saveMessage ? (
            <p className={`source-root-feedback ${saveState}`} role="status" aria-live="polite">
              {saveMessage}
            </p>
          ) : null}
        </form>
      ) : null}
    </section>
  );
}
