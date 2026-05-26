// This hook centralizes telemetry derivation so the telemetry column can remain
// a presentational renderer fed by a single, typed view model.
import type { ExecutionMetrics, ServiceStatus, VectorTelemetry } from "@/lib/types";

import type { AsyncViewState, DebateMessage, TelemetryPanelViewModel } from "../types";
import type { TelemetryTableRow, VectorUsageRow } from "../renderers/telemetry-sidebar";
import { getStyleIndex } from "../utils";

type RoleBreakdownEntry = {
  label: string;
  words: number;
  share: number;
};

type VectorTurnEntry = {
  turn_number: number;
  display_name: string;
  agent_id: string;
  vector: VectorTelemetry;
};

type UseTelemetryViewModelOptions = {
  servicesState: AsyncViewState;
  sessionBurnUsd: number;
  transcriptTokenEstimate: number;
  messages: DebateMessage[];
  roleBreakdown: RoleBreakdownEntry[];
  onlineServices: number;
  serviceRows: ServiceStatus[];
};

function getSpeakerLastName(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "--";
  }

  return parts[parts.length - 1];
}

function formatSpeakerTurnLabel(displayName: string, turnNumber: number): string {
  return `T${String(turnNumber).padStart(2, "0")}-${getSpeakerLastName(displayName)}`;
}

export function useTelemetryViewModel({
  servicesState,
  sessionBurnUsd,
  transcriptTokenEstimate,
  messages,
  roleBreakdown,
  onlineServices,
  serviceRows,
}: UseTelemetryViewModelOptions): TelemetryPanelViewModel {
  const metricsHistory = messages
    .map((message) => message.execution_metrics)
    .filter((metrics): metrics is ExecutionMetrics => Boolean(metrics));
  const vectorTurns = messages
    .map((message) => ({
      turn_number: message.turn_number,
      display_name: message.display_name,
      agent_id: message.agent_id,
      vector: message.telemetry?.vector,
    }))
    .filter((entry): entry is VectorTurnEntry => Boolean(entry.vector));

  const requestRows = messages
    .filter((message): message is DebateMessage & { execution_metrics: ExecutionMetrics } => Boolean(message.execution_metrics))
    .map((message) => {
      const prompt = Number(message.execution_metrics.prompt_tokens ?? 0);
      const completion = Number(message.execution_metrics.completion_tokens ?? 0);
      const total = Number(message.execution_metrics.total_tokens ?? prompt + completion);

      return {
        Speaker: formatSpeakerTurnLabel(message.display_name, message.turn_number),
        Prompt: String(prompt),
        Comp: String(completion),
        Total: String(total),
        _tone: String(getStyleIndex(message.agent_id)),
      };
    });

  const promptTokens = metricsHistory.reduce((sum, metrics) => sum + Number(metrics.prompt_tokens ?? 0), 0);
  const completionTokens = metricsHistory.reduce((sum, metrics) => sum + Number(metrics.completion_tokens ?? 0), 0);
  const aggregateTokens = metricsHistory.reduce(
    (sum, metrics) => sum + Number(metrics.total_tokens ?? Number(metrics.prompt_tokens ?? 0) + Number(metrics.completion_tokens ?? 0)),
    0,
  );
  const requestCount = requestRows.length;
  const displayedTotalTokens = aggregateTokens || transcriptTokenEstimate;

  if (requestRows.length > 0) {
    requestRows.push({
      Speaker: "Total",
      Prompt: String(promptTokens),
      Comp: String(completionTokens),
      Total: String(displayedTotalTokens),
      _tone: "",
    });
  }

  const generationSamples = metricsHistory
    .map((metrics) => metrics.generation_duration_ms)
    .filter((value): value is number => typeof value === "number");
  const queueSamples = metricsHistory
    .map((metrics) => metrics.queue_time_ms)
    .filter((value): value is number => typeof value === "number");
  const promptSamples = metricsHistory
    .map((metrics) => metrics.prompt_time_ms)
    .filter((value): value is number => typeof value === "number");
  const ttftSamples = metricsHistory
    .map((metrics) => metrics.ttft_ms)
    .filter((value): value is number => typeof value === "number");

  const averageGenerationMs = generationSamples.length > 0
    ? generationSamples.reduce((sum, value) => sum + value, 0) / generationSamples.length
    : null;
  const averageQueueMs = queueSamples.length > 0
    ? queueSamples.reduce((sum, value) => sum + value, 0) / queueSamples.length
    : null;
  const averagePromptMs = promptSamples.length > 0
    ? promptSamples.reduce((sum, value) => sum + value, 0) / promptSamples.length
    : null;
  const averageTtftMs = ttftSamples.length > 0
    ? ttftSamples.reduce((sum, value) => sum + value, 0) / ttftSamples.length
    : null;
  const totalGenerationMs = generationSamples.reduce((sum, value) => sum + value, 0);
  const sessionTps = completionTokens > 0 && totalGenerationMs > 0
    ? completionTokens / (totalGenerationMs / 1000)
    : null;

  const performanceRows: TelemetryTableRow[] = [
    {
      Average: "GEN TIME",
      Value: averageGenerationMs !== null ? `${Math.round(averageGenerationMs)}ms` : "IDLE",
    },
    {
      Average: "QUEUE",
      Value: averageQueueMs !== null ? `${Math.round(averageQueueMs)}ms` : "N/A",
    },
    {
      Average: "PROMPT",
      Value: averagePromptMs !== null ? `${Math.round(averagePromptMs)}ms` : "N/A",
    },
    {
      Average: "TTFT",
      Value: averageTtftMs !== null ? `${Math.round(averageTtftMs)}ms` : "N/A",
    },
    {
      Average: "SESSION TPS",
      Value: sessionTps !== null ? `${sessionTps.toFixed(2)} TPS` : "N/A",
    },
  ];

  const vocalShareRows: TelemetryTableRow[] = roleBreakdown.map((entry) => ({
    Speaker: entry.label,
    Words: String(entry.words),
    Share: `${Math.max(0, entry.share).toFixed(0)}%`,
  }));
  const totalVectorHits = vectorTurns.reduce((sum, entry) => sum + entry.vector.match_count, 0);
  const uniqueVectorSources = new Set(
    vectorTurns.flatMap((entry) => entry.vector.sources).map((source) => source.trim()).filter(Boolean),
  ).size;
  const vectorRows: VectorUsageRow[] = vectorTurns.map(({ turn_number, display_name, vector, agent_id }) => {
    return {
      speaker: formatSpeakerTurnLabel(display_name, turn_number),
      hits: String(vector.match_count),
      top: typeof vector.top_score === "number" ? vector.top_score.toFixed(3) : "--",
      context: String(vector.context_chars),
      _tone: String(getStyleIndex(agent_id)),
    };
  });

  const entropyValues = messages
    .filter((message) => typeof message.telemetry?.entropy === "number")
    .map((message) => message.telemetry!.entropy as number);

  const averageEntropy = entropyValues.length > 0
    ? entropyValues.reduce((sum, value) => sum + value, 0) / entropyValues.length
    : null;

  const observedRatio = averageEntropy !== null ? Math.max(0, Math.min(1, averageEntropy)) : 0;
  let diversityLabel = "No Data";
  let diversityValue = "0%";

  if (averageEntropy !== null) {
    diversityValue = `${Math.round(observedRatio * 100)}%`;
    diversityLabel = "High Spread";
    if (averageEntropy < 0.7) {
      diversityLabel = "Moderate";
    }
    if (averageEntropy < 0.35) {
      diversityLabel = "Low Spread";
    }
  }

  return {
    servicesState,
    onlineServices,
    serviceRows,
    performanceRows,
    totalVectorHits,
    uniqueVectorSources,
    vectorRows,
    displayedTotalTokens,
    requestCount,
    tokenTableRows: requestRows,
    sessionBurnUsd,
    observedRatio,
    diversityValue,
    diversityLabel,
    vocalShareRows,
  };
}