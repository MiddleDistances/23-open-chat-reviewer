import { useState, type ReactNode } from "react";
import { Check, Clipboard, Database, ExternalLink, RefreshCw, Terminal, TriangleAlert, Wifi } from "lucide-react";
import { Badge } from "../components/Common";

export interface SetupConnection {
  centralMachine: { id: string; name: string; hostname: string };
  web: { url: string; host: string; port: number };
  database: {
    localEndpoint: string;
    writerEndpoint: string | null;
    remoteReady: boolean;
  };
  tailscale: {
    connected: boolean;
    ipv4: string | null;
    dnsName: string | null;
  };
  networkScan: false;
  warnings: string[];
}

export interface ConnectionMachine {
  id: string;
  name: string;
}

interface WriterSetupGuideProps {
  connection: SetupConnection | null;
  checking: boolean;
  guideAvailable: boolean;
  refreshAvailable: boolean;
  onOpenGuide: () => void;
  onRefresh: () => void;
}

type WriterPlatform = "linux" | "macos";

export function ConnectionOverview({
  connection,
  machines,
}: {
  connection: SetupConnection | null;
  machines: ConnectionMachine[];
}) {
  const centralName = connection?.centralMachine.name ?? "Central server";
  const writerMachines = machines.filter(
    (machine) => machine.id !== connection?.centralMachine.id,
  );
  const firstWriter = writerMachines[0]?.name ?? "Source computer";
  const secondWriter = writerMachines[1]?.name ?? "Another computer";
  const additionalWriters = Math.max(0, writerMachines.length - 2);
  const secondWriterLabel = additionalWriters
    ? `${secondWriter} +${additionalWriters} more`
    : secondWriter;

  return (
    <section className="panel setup-connection-overview" aria-labelledby="setup-connection-title">
      <div className="setup-connection-heading">
        <div>
          <span className="eyebrow">How it fits together</span>
          <h2 id="setup-connection-title">Every computer syncs into one private archive</h2>
          <p>
            Source files stay on their own computers. Small writer agents send records through
            Tailscale to PostgreSQL; the central GUI reads that combined database.
          </p>
        </div>
        <Badge tone={connection == null ? "neutral" : connection.database.remoteReady ? "success" : "partial"}>
          {connection == null ? "Checking connection" : connection.database.remoteReady ? "Ready for writers" : "Central setup needed"}
        </Badge>
      </div>

      <div className="setup-connection-layout">
        <figure className="setup-architecture-figure">
          <svg
            className="setup-architecture-desktop"
            viewBox="0 0 760 420"
            role="img"
            aria-labelledby="setup-architecture-title setup-architecture-description"
          >
            <title id="setup-architecture-title">Open Chat Reviewer multi-machine architecture</title>
            <desc id="setup-architecture-description">
              {firstWriter} and {secondWriterLabel} sync local Codex, Claude, Gemini, and Git
              evidence over Tailscale into PostgreSQL on {centralName}. The web GUI reads the
              shared database and serves it to a trusted browser.
            </desc>
            <defs>
              <marker id="setup-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
                <path d="M0,0 L0,6 L9,3 z" className="setup-svg-arrowhead" />
              </marker>
            </defs>

            <rect x="24" y="48" width="190" height="112" rx="12" className="setup-svg-node" />
            <text x="48" y="82" className="setup-svg-kicker">WRITER MACHINE</text>
            <text x="48" y="112" className="setup-svg-title" style={machineNameStyle(firstWriter)}>{firstWriter}</text>
            <text x="48" y="138" className="setup-svg-copy">Codex · Claude · Gemini · Git</text>

            <rect x="24" y="254" width="190" height="112" rx="12" className="setup-svg-node" />
            <text x="48" y="288" className="setup-svg-kicker">WRITER MACHINE</text>
            <text x="48" y="318" className="setup-svg-title" style={machineNameStyle(secondWriterLabel)}>{secondWriterLabel}</text>
            <text x="48" y="344" className="setup-svg-copy">Local read-only sources</text>

            <path d="M214 104 C270 104 270 164 318 180" className="setup-svg-flow" markerEnd="url(#setup-arrow)" />
            <path d="M214 310 C270 310 270 250 318 234" className="setup-svg-flow" markerEnd="url(#setup-arrow)" />
            <text x="228" y="202" className="setup-svg-flow-label">encrypted tailnet</text>

            <rect x="318" y="92" width="222" height="236" rx="16" className="setup-svg-central" />
            <text x="346" y="128" className="setup-svg-kicker">CENTRAL MACHINE</text>
            <text x="346" y="160" className="setup-svg-title" style={machineNameStyle(centralName)}>{centralName}</text>
            <rect x="346" y="184" width="166" height="58" rx="8" className="setup-svg-database" />
            <text x="368" y="211" className="setup-svg-title-small">PostgreSQL</text>
            <text x="368" y="231" className="setup-svg-copy">one shared archive</text>
            <rect x="346" y="254" width="166" height="46" rx="8" className="setup-svg-gui" />
            <text x="368" y="283" className="setup-svg-title-small">Worker + web GUI</text>

            <path d="M540 210 L608 210" className="setup-svg-flow" markerEnd="url(#setup-arrow)" />
            <rect x="608" y="146" width="128" height="128" rx="14" className="setup-svg-node" />
            <text x="632" y="182" className="setup-svg-kicker">TRUSTED</text>
            <text x="632" y="214" className="setup-svg-title">Browser</text>
            <text x="632" y="240" className="setup-svg-copy">Search · review</text>

            <text x="318" y="375" className="setup-svg-endpoint">Private Tailscale database</text>
          </svg>
          <svg
            className="setup-architecture-mobile"
            viewBox="0 0 320 560"
            role="img"
            aria-labelledby="setup-mobile-architecture-title setup-mobile-architecture-description"
          >
            <title id="setup-mobile-architecture-title">Open Chat Reviewer multi-machine architecture</title>
            <desc id="setup-mobile-architecture-description">
              {firstWriter} and {secondWriterLabel} send local chat and Git evidence through
              Tailscale into PostgreSQL on {centralName}. The central web GUI serves the combined
              archive to a trusted browser.
            </desc>
            <defs>
              <marker id="setup-mobile-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
                <path d="M0,0 L0,6 L9,3 z" className="setup-svg-arrowhead" />
              </marker>
            </defs>

            <rect x="30" y="18" width="260" height="94" rx="12" className="setup-svg-node" />
            <text x="52" y="48" className="setup-svg-kicker">WRITER COMPUTERS</text>
            <text x="52" y="76" className="setup-svg-title" style={machineNameStyle(`${firstWriter} · ${secondWriterLabel}`, 26)}>
              {firstWriter} · {secondWriterLabel}
            </text>
            <text x="52" y="98" className="setup-svg-copy">Local Codex · Claude · Gemini · Git</text>

            <path d="M160 112 L160 158" className="setup-svg-flow" markerEnd="url(#setup-mobile-arrow)" />
            <text x="174" y="140" className="setup-svg-flow-label">Tailscale</text>

            <rect x="30" y="166" width="260" height="218" rx="16" className="setup-svg-central" />
            <text x="52" y="198" className="setup-svg-kicker">CENTRAL MACHINE</text>
            <text x="52" y="228" className="setup-svg-title" style={machineNameStyle(centralName, 24)}>{centralName}</text>
            <rect x="52" y="248" width="216" height="58" rx="8" className="setup-svg-database" />
            <text x="70" y="273" className="setup-svg-title-small">PostgreSQL</text>
            <text x="70" y="294" className="setup-svg-copy">one shared archive</text>
            <rect x="52" y="318" width="216" height="44" rx="8" className="setup-svg-gui" />
            <text x="70" y="346" className="setup-svg-title-small">Worker + web GUI</text>

            <path d="M160 384 L160 430" className="setup-svg-flow" markerEnd="url(#setup-mobile-arrow)" />
            <rect x="30" y="438" width="260" height="86" rx="12" className="setup-svg-node" />
            <text x="52" y="468" className="setup-svg-kicker">TRUSTED BROWSER</text>
            <text x="52" y="498" className="setup-svg-title">Search · review · resume</text>
            <text x="30" y="548" className="setup-svg-endpoint">Private Tailscale database</text>
          </svg>
          <figcaption>
            {machines.length} registered machine{machines.length === 1 ? "" : "s"}; no chat folders are mounted or copied between computers.
          </figcaption>
        </figure>

        <div className="setup-address-panel" role="group" aria-label="Central connection addresses">
          <AddressRow
            icon={<Wifi size={17} aria-hidden="true" />}
            label="Tailscale"
            value={connection?.tailscale.connected ? connection.tailscale.dnsName ?? connection.tailscale.ipv4 ?? "Connected" : "Not connected"}
            ready={connection == null ? undefined : connection.tailscale.connected}
          />
          <AddressRow
            icon={<ExternalLink size={17} aria-hidden="true" />}
            label="Central GUI"
            value={connection?.web.url ?? "Checking address…"}
            copyId="setup-copy-web-address"
            actionId="setup.connection.copy-web"
          />
          <AddressRow
            icon={<Database size={17} aria-hidden="true" />}
            label="Writer database endpoint"
            value={connection?.database.writerEndpoint ?? connection?.database.localEndpoint ?? "Checking address…"}
            ready={connection == null ? undefined : connection.database.remoteReady}
            copyId={connection?.database.writerEndpoint ? "setup-copy-database-address" : undefined}
            actionId="setup.connection.copy-database"
          />
          {connection != null && !connection.database.remoteReady ? (
            <div className="setup-address-warning" role="status">
              <TriangleAlert size={16} aria-hidden="true" />
              <span>
                <strong>Writers cannot connect yet.</strong>
                <small>The database is bound only to this computer. The guide will stop before giving you a misleading address.</small>
              </span>
            </div>
          ) : null}
          <small className="setup-address-security">Addresses never include database usernames or passwords.</small>
        </div>
      </div>
    </section>
  );
}

export function WriterSetupGuide({
  connection,
  checking,
  guideAvailable,
  refreshAvailable,
  onOpenGuide,
  onRefresh,
}: WriterSetupGuideProps) {
  const [platform, setPlatform] = useState<WriterPlatform>("linux");
  const [machineName, setMachineName] = useState("my-laptop");
  const slug = machineSlug(machineName);
  const centralCommand = `scripts/create-writer-config.sh ${slug}`;
  const installLines = [
    `git clone https://github.com/MiddleDistances/23-open-chat-reviewer.git && cd 23-open-chat-reviewer && scripts/connect-computer.sh ~/Downloads/${slug}.env`,
  ];

  return (
    <div className="setup-writer-guide" role="group" aria-labelledby="setup-writer-guide-title">
      <div className="setup-machine-onboarding-header">
        <div>
          <span className="eyebrow">Beginner setup</span>
          <h3 id="setup-writer-guide-title">Connect one other computer</h3>
        </div>
        <Badge tone={connection == null ? "neutral" : connection.database.remoteReady ? "success" : "partial"}>
          {connection == null ? "Checking connection" : connection.database.remoteReady ? "Private endpoint ready" : "Central fix required"}
        </Badge>
      </div>

      <div className="setup-writer-options">
        <label htmlFor="setup-writer-name">
          <span>Name the new computer</span>
          <input
            id="setup-writer-name"
            value={machineName}
            onChange={(event) => setMachineName(event.target.value)}
            autoComplete="off"
          />
        </label>
        <div role="group" aria-label="Writer operating system">
          <button
            id="setup-writer-platform-linux"
            data-action-id="setup.writer.platform.linux"
            type="button"
            className={platform === "linux" ? "active" : ""}
            aria-pressed={platform === "linux"}
            onClick={() => setPlatform("linux")}
          >
            Linux
          </button>
          <button
            id="setup-writer-platform-macos"
            data-action-id="setup.writer.platform.macos"
            type="button"
            className={platform === "macos" ? "active" : ""}
            aria-pressed={platform === "macos"}
            onClick={() => setPlatform("macos")}
          >
            macOS
          </button>
        </div>
      </div>

      {connection != null && !connection.database.remoteReady ? (
        <>
          <div className="setup-writer-blocker" role="alert">
            <TriangleAlert size={17} aria-hidden="true" />
            <span>
              <strong>Prepare the central database first.</strong>
              <small>
                The GUI is reachable at {connection?.web.url ?? "this machine"}, but PostgreSQL is currently local-only.
                On the central computer, run the command below, restart this web service, and refresh Setup.
              </small>
            </span>
          </div>
          <CommandBlock
            id="setup-copy-prepare-writers"
            actionId="setup.writer.copy-prepare"
            lines={["uv run open-chat-reviewer network prepare-writers"]}
          />
        </>
      ) : null}

      <ol className="setup-writer-steps">
        <li>
          <div><strong>Install and sign in to Tailscale on both computers.</strong><span>Use the same private tailnet, then confirm the other computer can reach {connection?.tailscale.dnsName ?? "the central machine"}.</span></div>
          <a href="https://tailscale.com/download" target="_blank" rel="noreferrer">Get Tailscale <ExternalLink size={13} aria-hidden="true" /></a>
        </li>
        <li>
          <div><strong>Create a private writer file on the central machine.</strong><span>This creates a unique machine ID and database login without printing its password.</span></div>
          <CommandBlock id="setup-copy-create-writer" actionId="setup.writer.copy-create" lines={[centralCommand]} />
        </li>
        <li>
          <div><strong>Move the private file to the other computer.</strong><span>Transfer <code>.chatreview/writers/{slug}.env</code> securely. Do not email it, commit it, or paste it into chat.</span></div>
        </li>
        <li>
          <div><strong>Run one installation command on the other computer.</strong><span>It installs what is needed{platform === "macos" ? ", including flock through Homebrew when missing" : ""}, checks the database, performs the first resumable sync, and installs the three-hour schedule.</span></div>
          <CommandBlock id="setup-copy-install-writer" actionId="setup.writer.copy-install" lines={installLines} />
        </li>
        <li>
          <div><strong>Come back here and check the archive.</strong><span>The new machine appears after its first successful sync.</span></div>
        </li>
      </ol>

      <div className="setup-machine-onboarding-actions">
        <button className="button" id="setup-open-writer-guide" data-action-id="setup.guide.writer" type="button" disabled={!guideAvailable} onClick={onOpenGuide}>
          <Terminal size={15} aria-hidden="true" /> Full writer guide
        </button>
        <button className="button button-primary" id="setup-refresh-machines" data-action-id="setup.machine.refresh" type="button" disabled={!refreshAvailable || checking} onClick={onRefresh}>
          <RefreshCw className={checking ? "setup-spin" : ""} size={15} aria-hidden="true" />
          {checking ? "Checking shared archive…" : "Check shared archive"}
        </button>
      </div>
    </div>
  );
}

function AddressRow({
  icon,
  label,
  value,
  ready,
  copyId,
  actionId,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  ready?: boolean;
  copyId?: string;
  actionId?: string;
}) {
  return (
    <div className="setup-address-row">
      <span className="setup-address-icon">{icon}</span>
      <span><small>{label}</small><strong>{value}</strong></span>
      {ready != null ? <Badge tone={ready ? "success" : "partial"}>{ready ? "Ready" : "Local only"}</Badge> : null}
      {copyId && actionId ? <CopyButton id={copyId} actionId={actionId} value={value} /> : null}
    </div>
  );
}

function CommandBlock({ id, actionId, lines }: { id: string; actionId: string; lines: string[] }) {
  return (
    <div className="setup-command-block">
      <pre><code>{lines.join("\n")}</code></pre>
      <CopyButton id={id} actionId={actionId} value={lines.join("\n")} label="Copy commands" />
    </div>
  );
}

function CopyButton({ id, actionId, value, label = "Copy" }: { id: string; actionId: string; value: string; label?: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  async function copy() {
    try {
      await copyText(value);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
    window.setTimeout(() => setCopyState("idle"), 1800);
  }
  return (
    <button
      className="setup-copy-button"
      id={id}
      data-action-id={actionId}
      type="button"
      aria-live="polite"
      onClick={() => void copy()}
    >
      {copyState === "copied" ? <Check size={14} aria-hidden="true" /> : <Clipboard size={14} aria-hidden="true" />}
      {copyState === "copied" ? "Copied" : copyState === "error" ? "Select and copy" : label}
    </button>
  );
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.readOnly = true;
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) throw new Error("clipboard copy is unavailable");
}

function machineSlug(value: string): string {
  const normalized = value.toLowerCase().trim().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "");
  return normalized.slice(0, 31) || "my-laptop";
}

function machineNameStyle(name: string, comfortableLength = 17) {
  return name.length > comfortableLength ? { fontSize: 13 } : undefined;
}
