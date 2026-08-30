export type ResumeState = "ready" | "decision" | "blocked" | "waiting" | "done" | "unclear";

export interface ResumeLocation {
  session_id: number;
  provider: string;
  cwd: string | null;
  active_at: string | null;
  machine_name: string | null;
  project_name: string | null;
  repository_url: string | null;
}

export interface ResumeSurface {
  id: number;
  root_session_id: number;
  concept: string;
  long_term_goal: string;
  summary: string;
  current_state: ResumeState;
  next_decision: string | null;
  next_moves: string[];
  research_directions: string[];
  open_loops: string[];
  confidence: "low" | "medium" | "high";
  last_activity_at: string;
  generated_at: string;
  project_name: string | null;
  repository_url: string | null;
  locations: ResumeLocation[];
  providers: string[];
}

export interface ResumeSurfaceResponse {
  surfaces: ResumeSurface[];
  total: number;
  states: Partial<Record<ResumeState, number>>;
  latest_run: {
    id: number;
    model_name: string;
    prompt_version: string;
    selected_count: number;
    generated_count: number;
    reused_count: number;
    skipped_count: number;
    failed_count: number;
    status: "running" | "complete" | "partial" | "failed";
    started_at: string;
    completed_at: string | null;
  } | null;
  method_note: string;
}

export interface Session {
  id: number;
  session_key: string;
  provider: string;
  external_id: string;
  project: string | null;
  cwd: string | null;
  started_at: string | null;
  ended_at: string | null;
  title: string | null;
  event_count: number;
  text_unit_count: number;
}

export interface ChatTrace {
  session: Session;
  summary: {
    occurrences: number;
    visible_occurrences: number;
    tool_calls: number;
    error_occurrences: number;
    corrections: number;
    discussion_occurrences: number;
    active_seconds: number;
    actions: Array<{ action: string; count: number }>;
  };
  occurrences: TraceOccurrence[];
  top_transitions: Array<{ from: string; to: string; count: number; occurrence_support: number }>;
  truncated: boolean;
  total_occurrences: number;
  method_note: string;
}

export interface TraceOccurrence {
  id: number;
  episode_key: string;
  sequence_no: number;
  started_at: string | null;
  ended_at: string | null;
  active_seconds: number;
  event_count: number;
  tool_call_count: number;
  derived_attempt_count: number;
  error_count: number;
  evidence_state: string;
  first_event_id: number;
  last_event_id: number;
  context: string | null;
  outcome: string | null;
  correction: boolean;
  signature: {
    key: string;
    title: string;
    basis: string;
    errors: string[];
    entities: string[];
    operations: string[];
    correction: boolean;
    provisional: boolean;
  };
  call_runs: TraceCallRun[];
  hidden_run_count: number;
  hidden_call_count: number;
}

export interface TraceCallRun {
  action: string;
  operation: string;
  outcome: "unknown" | "result" | "error";
  first_event_id: number;
  last_event_id: number;
  started_at: string | null;
  ended_at: string | null;
  count: number;
}

export interface EpisodeSummary {
  id: number;
  episode_key: string;
  sequence_no: number;
  started_at: string | null;
  ended_at: string | null;
  active_seconds: number;
  event_count: number;
  attempt_count: number;
  error_count: number;
  evidence_state: string;
  first_event_id: number;
  last_event_id: number;
  session_id: number;
  provider: string;
  project: string | null;
  goal: string | null;
  outcome: string | null;
  document: string;
  lexical_score?: number | null;
}

export interface EpisodeDetail extends EpisodeSummary {
  generation: string;
  segmentation_version: number;
  session_key: string;
  external_id: string;
  events: Array<{
    position: number;
    section: string;
    id: number;
    event_key: string;
    timestamp: string | null;
    event_type: string;
    subtype: string | null;
    role: string | null;
  }>;
  fingerprints: Array<{ kind: string; value: string; value_hash: string }>;
  annotations: Annotation[];
}

export interface EpisodeStats {
  episodes: number;
  sessions: number;
  error_episodes: number;
  attempts: number;
  active_seconds: number;
  generation: string | null;
  duplicate_events: number;
}

export interface TextUnit {
  unit_key: string;
  kind: string;
  label: string | null;
  is_error: number;
  text: string;
  char_count: number;
}

export interface EventRecord {
  id: number;
  event_key: string;
  timestamp: string | null;
  event_type: string;
  subtype: string | null;
  role: string | null;
  line_no: number;
  source_path: string;
  source_provenance?: Record<string, unknown>;
  parse_error: string | null;
  metadata: Record<string, unknown>;
  units: TextUnit[];
}

export interface LexicalResult {
  event_id: number;
  event_key: string;
  timestamp: string | null;
  event_type: string;
  subtype: string | null;
  role: string | null;
  kind: string;
  unit_key: string;
  label: string | null;
  text: string;
  snippet: string;
  session_id: number | null;
  session_external_id: string | null;
  provider: string | null;
  project: string | null;
  source_path: string;
  line_no: number;
}

export interface SemanticResult {
  window_id: number;
  window_key: string;
  sequence_no: number;
  cluster_id: number;
  episode_id: number | null;
  first_event_id: number;
  last_event_id: number;
  session_id: number;
  session_key: string;
  external_id: string;
  provider: string;
  project: string | null;
  semantic_score: number;
  semantic_run_key: string;
  semantic_profile: string;
  snippet: string;
}

export interface SearchResponse {
  query: string;
  mode: string;
  lexical: LexicalResult[];
  semantic: SemanticResult[];
  semantic_error: string | null;
  semantic_profile: string | null;
  semantic_run_key: string | null;
}

export interface SemanticRun {
  id: number;
  run_key: string;
  model_name: string;
  model_revision: string;
  dimensions: number;
  chunk_count: number;
  completed_at: string | null;
  status: string;
  error: string | null;
  profile: "conversation" | "attempts" | "blended" | "episodes" | "legacy";
  freshness: "current" | "stale" | "unknown";
}

export interface Annotation {
  id: number;
  target_type: string;
  target_key: string;
  label_id: number | null;
  label: string | null;
  color: string | null;
  note: string | null;
  review_state: string;
  created_at: string;
  updated_at: string;
}

export interface Label {
  id: number;
  name: string;
  color: string;
  description: string | null;
  annotation_count: number;
}
