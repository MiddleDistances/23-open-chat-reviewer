import type { ReactNode } from "react";

export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
      </div>
      {children && <div className="header-actions">{children}</div>}
    </header>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-orbit" />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export function Loading({ label = "Loading corpus data" }: { label?: string }) {
  return <div className="loading"><span />{label}</div>;
}

export function ErrorNotice({ message }: { message: string }) {
  return <div className="error-notice">{message}</div>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export const CONVERSATION_PROVIDERS = [
  { value: "codex", label: "Codex" },
  { value: "claude", label: "Claude" },
  { value: "gemini", label: "Gemini" },
] as const;

export function ProviderOptions({ allLabel = "All providers" }: { allLabel?: string }) {
  return (
    <>
      <option value="">{allLabel}</option>
      {CONVERSATION_PROVIDERS.map((provider) => (
        <option value={provider.value} key={provider.value}>{provider.label}</option>
      ))}
    </>
  );
}

export function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat("en-AU", { notation: value && value > 999_999 ? "compact" : "standard" }).format(value ?? 0);
}

export function formatBytes(value: number | null | undefined) {
  const bytes = value ?? 0;
  if (!bytes) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function formatDate(value: string | null | undefined, includeTime = false) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-AU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

export function formatHours(seconds: number): string {
  const hours = seconds / 3600;
  return `${new Intl.NumberFormat("en-AU", {
    minimumFractionDigits: hours > 0 && hours < 10 ? 1 : 0,
    maximumFractionDigits: 1,
  }).format(hours)}h`;
}

export function projectName(value: string | null | undefined) {
  if (!value) return "Unknown project";
  const parts = value.split("/").filter(Boolean);
  return parts.at(-1) ?? value;
}

export function Highlight({ html }: { html: string }) {
  const pieces = html.split(/(<mark>.*?<\/mark>)/gi);
  return (
    <>
      {pieces.map((piece, index) =>
        piece.toLowerCase().startsWith("<mark>") ? (
          <mark key={index}>{piece.slice(6, -7)}</mark>
        ) : (
          <span key={index}>{piece}</span>
        ),
      )}
    </>
  );
}
