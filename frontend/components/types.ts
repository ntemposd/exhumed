// Shared frontend-only view types live here so workbench components can stay
// focused on rendering instead of re-declaring the same contracts locally.
import type { ExecutionMetrics, TurnTelemetry } from "@/lib/types";
import type { ServiceStatus } from "@/lib/types";
import type { TelemetryTableRow, VectorUsageRow } from "./renderers/telemetry-tables";

export type LegendDetails = {
  agent_id: string;
  display_name: string;
  archetype: string;
};

export type AsyncViewState = {
  phase: "loading" | "refreshing" | "ready" | "empty" | "error";
  summary: string;
  detail?: string;
};

export type TranscriptViewState = {
  phase: "idle" | "running" | "ready" | "error";
  statusLabel: string;
  emptyMessage: string;
};

export type TelemetryPanelViewModel = {
  servicesState: AsyncViewState;
  onlineServices: number;
  serviceRows: ServiceStatus[];
  performanceRows: TelemetryTableRow[];
  totalVectorHits: number;
  uniqueVectorSources: number;
  vectorRows: VectorUsageRow[];
  displayedTotalTokens: number;
  requestCount: number;
  tokenTableRows: TelemetryTableRow[];
  sessionBurnUsd: number;
  observedRatio: number;
  diversityValue: string;
  diversityLabel: string;
  vocalShareRows: TelemetryTableRow[];
};

export type DebateMessage = {
  id: string;
  agent_id: string;
  display_name: string;
  message: string;
  round_number?: number;
  turn_number: number;
  created_at: string;
  isThinking?: boolean;
  thinkingStatus?: string;
  failed?: boolean;
  telemetry?: TurnTelemetry | null;
  execution_metrics?: ExecutionMetrics | null;
};