// Backend contract types are isolated here so fetch hooks and presentational
// components share one source of truth for API payloads.
export type Agent = {
  agent_id: string;
  display_name: string;
  system_prompt: string;
  temperature: number;
  max_tokens: number;
};

export type AgentsResponse = {
  agents: Agent[];
};

export type ServiceStatus = {
  name: string;
  status: string;
  latency_ms?: number | null;
  detail?: string | null;
};

export type ServicesStatusResponse = {
  status: string;
  services: ServiceStatus[];
  checked_at?: string;
};

export type ExecutionMetrics = {
  generation_duration_ms?: number | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  tokens_per_second?: number | null;
  queue_time_ms?: number | null;
  prompt_time_ms?: number | null;
  ttft_ms?: number | null;
  network_rtt_ms?: number | null;
  provider: string;
  updated_at: string;
};

export type TurnTelemetry = {
  entropy: number;
  latency_ms: number;
  word_count: number;
  vector?: VectorTelemetry | null;
};

export type VectorTelemetry = {
  used: boolean;
  match_count: number;
  top_score?: number | null;
  sources: string[];
  chunk_ids: string[];
  context_chars: number;
};

export type ProcessTurnResponse = {
  message_id: string;
  agent_id: string;
  display_name: string;
  message: string;
  turn_number: number;
  created_at: string;
  telemetry: TurnTelemetry;
  execution_metrics: ExecutionMetrics;
};

export type ProcessTurnStreamChunk = {
  type: "chunk";
  content: string;
};

export type ProcessTurnStreamStatus = {
  type: "status";
  stage: "retrying";
  message: string;
  retry_after_seconds: number;
  attempt_number: number;
};

export type ProcessTurnStreamFinal = {
  type: "final";
  message_id: string;
  agent_id: string;
  display_name: string;
  message: string;
  turn_number: number;
  created_at: string;
  telemetry: TurnTelemetry;
  execution_metrics: ExecutionMetrics;
};

export type ProcessTurnStreamEvent = ProcessTurnStreamChunk | ProcessTurnStreamStatus | ProcessTurnStreamFinal;

export type LatestTelemetryResponse = {
  status: string;
  metrics: ExecutionMetrics | null;
};