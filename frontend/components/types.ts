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
  vectorTurnCount: number;
  uniqueVectorSources: number;
  uniqueVectorSourceLabels: string[];
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

export type ControlSidebarViewModel = {
  chrome: {
    isSidebarOpen: boolean;
    isMobileViewport: boolean;
    showSidebarToggle: boolean;
  };
  session: {
    discussionActive: boolean;
    sessionId: string;
    selectedCouncil: LegendDetails[];
    targetEntropy: number;
    controlError: string;
    legendCatalogState: AsyncViewState;
    isWipingSession: boolean;
    isDownloadingTranscript: boolean;
    startButtonLabel: string;
  };
};

export type ControlSidebarActions = {
  onToggleSidebar: () => void;
  onOpenSpeakerModal: () => void;
  onToggleCouncilMember: (agentId: string) => void;
  onTargetEntropyChange: (value: number) => void;
  onStartDebate: () => void;
  onHaltDebate: () => void;
  onWipeDebate: () => void | Promise<void>;
  onDownloadTranscript: () => void | Promise<void>;
  onRenewSession: () => void;
};

export type DebateMessage = {
  id: string;
  agent_id: string;
  display_name: string;
  message: string;
  turn_number: number;
  created_at: string;
  isThinking?: boolean;
  thinkingStatus?: string;
  failed?: boolean;
  telemetry?: TurnTelemetry | null;
  execution_metrics?: ExecutionMetrics | null;
};