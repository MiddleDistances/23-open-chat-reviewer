import { CalendarDays, Crosshair, Info, RotateCcw, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { queryString, useApi } from "../api";
import AnnotationPanel from "../components/AnnotationPanel";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  Loading,
  PageHeader,
  ProviderOptions,
  formatDate,
  formatNumber,
  projectName,
} from "../components/Common";
import type { SemanticRun } from "../types";

const MAP_LIMIT = 200_000;
const MAX_RENDERED_POINTS = 20_000;

/** The filters understood by the semantic map endpoint. */
export interface MapFilters {
  runId: string;
  provider: string;
  clusterId: string;
  dateFrom: string;
  dateTo: string;
}

/** A map point returned by the semantic projection API. */
export interface MapPoint {
  id: number;
  window_key: string;
  sequence_no: number;
  cluster_id: number;
  episode_id: number | null;
  episode_key?: string | null;
  x: number;
  y: number;
  session_id: number;
  provider: string;
  project: string | null;
  /** The text sent to the embedding model, or a faithful preview of it. */
  preview?: string | null;
  /** Compatibility names for API revisions during the semantic-map rollout. */
  vector_preview?: string | null;
  vector_text?: string | null;
  embedding_text?: string | null;
  text?: string | null;
  headline?: string | null;
  timestamp?: string | null;
  first_timestamp?: string | null;
  last_timestamp?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface MapCluster {
  cluster_id: number;
  label: string;
  keywords_json: string;
  window_count: number;
}

/** Response shape for GET /api/map. Kept local so the page can land independently of shared type wiring. */
export interface MapData {
  run: SemanticRun | null;
  total: number;
  sample_stride: number;
  points: MapPoint[];
  clusters: MapCluster[];
}

export interface MapPageProps {
  /** Optional dependency injection for tests or a parent-owned data loader. */
  data?: MapData | null;
  semanticRuns?: SemanticRun[];
  loading?: boolean;
  error?: string | null;
  initialFilters?: Partial<MapFilters>;
  onFiltersChange?: (filters: MapFilters) => void;
  onPointSelect?: (point: MapPoint | null) => void;
}

const DEFAULT_FILTERS: MapFilters = {
  runId: "",
  provider: "",
  clusterId: "",
  dateFrom: "",
  dateTo: "",
};

/** Build the stable query contract shared by the UI and the API. */
export function mapQuery(filters: MapFilters): string {
  return queryString({
    run_id: filters.runId,
    provider: filters.provider,
    cluster_id: filters.clusterId,
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    limit: MAP_LIMIT,
  });
}

/** Return the actual text represented by a vector point, never its headline/title. */
export function mapPointPreview(point: MapPoint): string {
  const value = point.vector_preview ?? point.vector_text ?? point.embedding_text ?? point.preview ?? point.text;
  return value?.trim() || "No vectorized text was retained for this window.";
}

export function mapPointDate(point: MapPoint): string | null {
  return point.first_timestamp ?? point.started_at ?? point.timestamp ?? point.last_timestamp ?? point.ended_at ?? null;
}

export function mapPointTooltip(point: MapPoint): string {
  return `${projectName(point.project)}\nCluster ${point.cluster_id}\n${truncate(mapPointPreview(point), 240)}`;
}

/** Apply date filters locally as a safe fallback for injected/stale API responses. */
export function pointMatchesDate(point: MapPoint, dateFrom: string, dateTo: string): boolean {
  const value = mapPointDate(point)?.slice(0, 10);
  if (!value) return !dateFrom && !dateTo;
  return (!dateFrom || value >= dateFrom) && (!dateTo || value <= dateTo);
}

export default function MapPage({
  data: injectedData,
  semanticRuns: injectedRuns,
  loading: injectedLoading,
  error: injectedError,
  initialFilters,
  onFiltersChange,
  onPointSelect,
}: MapPageProps) {
  const [filters, setFilters] = useState<MapFilters>({ ...DEFAULT_FILTERS, ...initialFilters });
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const [hovered, setHovered] = useState<MapPoint | null>(null);
  const path = `/api/map?${mapQuery(filters)}`;
  const remoteRuns = useApi<SemanticRun[]>(injectedRuns === undefined ? "/api/semantic-runs" : null);
  const remoteMap = useApi<MapData>(injectedData === undefined ? path : null);
  const data = injectedData === undefined ? remoteMap.data : injectedData;
  const semanticRuns = injectedRuns === undefined ? remoteRuns.data : injectedRuns;
  const loading = injectedLoading ?? (injectedData === undefined && remoteMap.loading);
  const error = injectedError ?? (injectedData === undefined ? remoteMap.error : null);

  const visiblePoints = useMemo(() => {
    if (!data) return [];
    return data.points.filter((point) => pointMatchesDate(point, filters.dateFrom, filters.dateTo));
  }, [data, filters.dateFrom, filters.dateTo]);
  const pointsToRender = visiblePoints.slice(0, MAX_RENDERED_POINTS);

  useEffect(() => {
    if (selected && !visiblePoints.some((point) => point.id === selected.id)) {
      setSelected(null);
      onPointSelect?.(null);
    }
  }, [onPointSelect, selected, visiblePoints]);

  function updateFilters(change: Partial<MapFilters>) {
    const next = { ...filters, ...change };
    setFilters(next);
    setSelected(null);
    setHovered(null);
    onFiltersChange?.(next);
  }

  function selectPoint(point: MapPoint | null) {
    setSelected(point);
    setHovered(point);
    onPointSelect?.(point);
  }

  const completeRuns = useMemo(() => {
    const runs = semanticRuns?.filter((run) => run.status === "complete") ?? [];
    if (data?.run && !runs.some((run) => run.id === data.run?.id)) return [data.run, ...runs];
    return runs;
  }, [data?.run, semanticRuns]);

  const isFiltered = Object.values(filters).some(Boolean);
  const displayedTotal = data ? visiblePoints.length : 0;

  return (
    <>
      <PageHeader eyebrow="Derived view" title="The semantic shape of the corpus">
        <div className="map-count" aria-live="polite">
          <Crosshair size={15} />
          {formatNumber(data ? (isFiltered ? displayedTotal : data.total) : 0)} windows
        </div>
      </PageHeader>

      <div className="map-toolbar" aria-label="Semantic map filters">
        <SlidersHorizontal size={15} aria-hidden="true" />
        <label>
          <span className="sr-only">Semantic run</span>
          <select
            aria-label="Semantic run"
            value={filters.runId}
            onChange={(event) => updateFilters({ runId: event.target.value, clusterId: "" })}
          >
            <option value="">Conversation run (default)</option>
            {completeRuns.map((run) => (
              <option key={run.id} value={run.id}>{run.profile} · {run.chunk_count.toLocaleString()} · {run.freshness}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Provider</span>
          <select aria-label="Provider" value={filters.provider} onChange={(event) => updateFilters({ provider: event.target.value })}>
            <ProviderOptions />
          </select>
        </label>
        <label>
          <span className="sr-only">Cluster</span>
          <select aria-label="Cluster" value={filters.clusterId} onChange={(event) => updateFilters({ clusterId: event.target.value })}>
            <option value="">All clusters</option>
            {data?.clusters.map((cluster) => (
              <option key={cluster.cluster_id} value={cluster.cluster_id}>{cluster.label} ({cluster.window_count.toLocaleString()})</option>
            ))}
          </select>
        </label>
        <label className="map-date-filter">
          <CalendarDays size={14} aria-hidden="true" />
          <span className="sr-only">Date from</span>
          <input aria-label="Date from" type="date" value={filters.dateFrom} max={filters.dateTo || undefined} onChange={(event) => updateFilters({ dateFrom: event.target.value })} />
        </label>
        <span aria-hidden="true" className="map-date-separator">to</span>
        <label className="map-date-filter">
          <span className="sr-only">Date to</span>
          <input aria-label="Date to" type="date" value={filters.dateTo} min={filters.dateFrom || undefined} onChange={(event) => updateFilters({ dateTo: event.target.value })} />
        </label>
        {isFiltered && <button type="button" className="text-button" onClick={() => updateFilters(DEFAULT_FILTERS)}><RotateCcw size={13} />Reset</button>}
        {data?.run && <span className={`freshness freshness-${data.run.freshness}`}>{data.run.profile} snapshot · {data.run.freshness}</span>}
        {data?.sample_stride && data.sample_stride > 1 && <span>Showing 1 in {data.sample_stride} points</span>}
      </div>

      {loading && <Loading label="Loading vector projection" />}
      {error && <ErrorNotice message={error} />}
      {!loading && !error && data && !data.run && (
        <EmptyState title="No semantic projection built">
          <span>Set the date and reasoning policy in Setup, then run <code>uv run chatreview derive</code>. Exact search and transcripts remain available now.</span>
        </EmptyState>
      )}
      {!loading && !error && data?.run && visiblePoints.length === 0 && (
        <EmptyState title="No points match these filters">
          <span>Widen the date range or clear the provider and cluster filters to see the available projection.</span>
        </EmptyState>
      )}
      {!loading && !error && data?.run && visiblePoints.length > 0 && (
        <div className="map-workspace">
          <div className="deck-container map-plot-container">
            <AccessiblePointMap points={pointsToRender} selected={selected} hovered={hovered} onHover={setHovered} onSelect={selectPoint} />
            {hovered && <div className="map-tooltip" role="tooltip">{mapPointTooltip(hovered)}</div>}
            {visiblePoints.length > pointsToRender.length && <p className="map-sample-note">Showing {formatNumber(pointsToRender.length)} of {formatNumber(visiblePoints.length)} points for responsive rendering.</p>}
          </div>
          <MapInspector point={selected} />
        </div>
      )}
    </>
  );
}

function AccessiblePointMap({
  points,
  selected,
  hovered,
  onHover,
  onSelect,
}: {
  points: MapPoint[];
  selected: MapPoint | null;
  hovered: MapPoint | null;
  onHover: (point: MapPoint | null) => void;
  onSelect: (point: MapPoint) => void;
}) {
  const bounds = useMemo(() => pointBounds(points), [points]);
  return (
    <div className="map-plot" role="group" aria-label="Semantic projection points">
      <svg viewBox="0 0 1000 640" role="img" aria-label={`${points.length.toLocaleString()} semantic windows plotted by similarity`} preserveAspectRatio="none">
        <rect x="0" y="0" width="1000" height="640" fill="transparent" aria-hidden="true" />
        {points.map((point) => {
          const [cx, cy] = projectPoint(point, bounds);
          const isSelected = point.id === selected?.id;
          const isHovered = point.id === hovered?.id;
          return (
            <circle
              key={point.id}
              cx={cx}
              cy={cy}
              r={isSelected ? 7 : isHovered ? 6 : 4}
              className={`map-point ${isSelected ? "is-selected" : ""}`}
              fill={`hsl(${clusterHue(point.cluster_id)} 65% 58%)`}
              fillOpacity={isSelected || isHovered ? 1 : 0.76}
              stroke={isSelected ? "#ffffff" : "transparent"}
              strokeWidth={isSelected ? 2 : 0}
              role="button"
              tabIndex={0}
              aria-label={mapPointTooltip(point)}
              onClick={() => onSelect(point)}
              onFocus={() => onHover(point)}
              onBlur={() => onHover(null)}
              onMouseEnter={() => onHover(point)}
              onMouseLeave={() => onHover(null)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(point);
                }
              }}
            >
              <title>{mapPointTooltip(point)}</title>
            </circle>
          );
        })}
      </svg>
    </div>
  );
}

function MapInspector({ point }: { point: MapPoint | null }) {
  if (!point) {
    return (
      <aside className="map-inspector" aria-label="Semantic point details">
        <div className="map-instruction">
          <Crosshair size={24} />
          <h3>Select a point</h3>
          <p>Each point represents a semantic window. Hover or focus a point to preview the text that was vectorized; nearby points indicate similar language, not a shared cause.</p>
        </div>
      </aside>
    );
  }
  const contextPath = point.episode_id ? `/episodes/${point.episode_id}` : `/sessions/${point.session_id}?event=${point.id}`;
  const targetType = point.episode_id ? "episode" : "window";
  const targetKey = point.episode_key ?? point.window_key;
  return (
    <aside className="map-inspector" aria-label="Selected semantic point">
      <div className="section-heading"><Info size={16} /><h3>Selected {point.episode_id ? "episode" : "window"}</h3></div>
      <div className="map-selection-meta"><Badge tone={point.provider}>{point.provider}</Badge><span>Cluster {point.cluster_id}</span>{mapPointDate(point) && <time dateTime={mapPointDate(point) ?? undefined}>{formatDate(mapPointDate(point), true)}</time>}</div>
      <h2>{projectName(point.project)}</h2>
      <pre data-testid="selected-vector-preview">{mapPointPreview(point)}</pre>
      <Link className="button button-primary" to={contextPath}>Open evidence context</Link>
      <AnnotationPanel targetType={targetType} targetKey={targetKey} />
    </aside>
  );
}

function pointBounds(points: MapPoint[]) {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function projectPoint(point: MapPoint, bounds: ReturnType<typeof pointBounds>): [number, number] {
  const xSpan = bounds.maxX - bounds.minX || 1;
  const ySpan = bounds.maxY - bounds.minY || 1;
  return [40 + ((point.x - bounds.minX) / xSpan) * 920, 600 - ((point.y - bounds.minY) / ySpan) * 560];
}

function clusterHue(cluster: number): number {
  if (cluster < 0) return 210;
  return (cluster * 137.508 + 18) % 360;
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}
