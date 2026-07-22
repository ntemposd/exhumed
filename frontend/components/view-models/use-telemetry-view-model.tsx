// This hook centralizes telemetry derivation so the telemetry column can remain
// a presentational renderer fed by a single, typed view model.
import { useMemo } from "react";

import type {
  AnswerEvalScores,
  AnswerJudgeTelemetry,
  ExecutionMetrics,
  ServiceStatus,
  VectorTelemetry,
} from "@/lib/types";

import type {
  AsyncViewState,
  DebateMessage,
  ScoreboardMetricView,
  TelemetryPanelViewModel,
  TelemetryTableRow,
  VectorUsageRow,
} from "../types";
import { formatSourceCitation } from "../source-titles";
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
  convoCostUsd: number;
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

function scoreBandLabel(average: number, highLabel: string, midLabel: string, lowLabel: string): string {
  if (average < 0.35) {
    return lowLabel;
  }
  if (average < 0.7) {
    return midLabel;
  }
  return highLabel;
}

function averageScore(
  messages: DebateMessage[],
  key: keyof AnswerEvalScores,
): number | null {
  const values = messages
    .map((message) => message.telemetry?.scores?.[key])
    .filter((value): value is number => typeof value === "number");
  if (values.length === 0) {
    return null;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function averageJudgeScore(
  messages: DebateMessage[],
  key: keyof Pick<AnswerJudgeTelemetry, "faithfulness" | "persona">,
): number | null {
  const values = messages
    .map((message) => message.telemetry?.judge?.[key])
    .filter((value): value is number => typeof value === "number");
  if (values.length === 0) {
    return null;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function buildScoreboardMetric(
  key: ScoreboardMetricView["key"],
  label: string,
  average: number | null,
  highLabel: string,
  midLabel: string,
  lowLabel: string,
  caption: string,
): ScoreboardMetricView {
  if (average === null) {
    return {
      key,
      label,
      value: "0%",
      statusLabel: "No Data",
      ratio: 0,
      caption,
    };
  }

  const ratio = Math.max(0, Math.min(1, average));
  return {
    key,
    label,
    value: `${Math.round(ratio * 100)}%`,
    statusLabel: scoreBandLabel(average, highLabel, midLabel, lowLabel),
    ratio,
    caption,
  };
}

export function useTelemetryViewModel({
  servicesState,
  convoCostUsd,
  transcriptTokenEstimate,
  messages,
  roleBreakdown,
  onlineServices,
  serviceRows,
}: UseTelemetryViewModelOptions): TelemetryPanelViewModel {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => {
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
      Metric: "Generation Time",
      "Convo avg.": averageGenerationMs !== null ? `${Math.round(averageGenerationMs)}ms` : "IDLE",
    },
    {
      Metric: "Queue Wait",
      "Convo avg.": averageQueueMs !== null ? `${Math.round(averageQueueMs)}ms` : "IDLE",
    },
    {
      Metric: "Prompt Processing",
      "Convo avg.": averagePromptMs !== null ? `${Math.round(averagePromptMs)}ms` : "IDLE",
    },
    {
      Metric: "Time to First Token",
      "Convo avg.": averageTtftMs !== null ? `${Math.round(averageTtftMs)}ms` : "IDLE",
    },
    {
      Metric: "Throughput (convo)",
      "Convo avg.": sessionTps !== null ? `${sessionTps.toFixed(2)} tok/s` : "IDLE",
    },
  ];

  const vocalShareRows: TelemetryTableRow[] = roleBreakdown.map((entry) => ({
    Speaker: entry.label,
    Words: String(entry.words),
    Share: `${Math.max(0, entry.share).toFixed(0)}%`,
  }));
  const totalVectorHits = vectorTurns.reduce((sum, entry) => sum + entry.vector.match_count, 0);
  const uniqueVectorSources = new Set(
    vectorTurns
      .flatMap((entry) => entry.vector.sources)
      .map((source) => formatSourceCitation(source))
      .filter(Boolean),
  ).size;
  const vectorRows: VectorUsageRow[] = vectorTurns.map(({ turn_number, display_name, vector, agent_id }) => {
    return {
      speaker: formatSpeakerTurnLabel(display_name, turn_number),
      hits: String(vector.match_count),
      top: typeof vector.top_score === "number" ? vector.top_score.toFixed(3) : "--",
      context: vector.context_chars.toLocaleString(),
      _tone: String(getStyleIndex(agent_id)),
    };
  });

  const scoreboardMetrics: ScoreboardMetricView[] = [
    buildScoreboardMetric(
      "grounding",
      "Source relevance",
      averageScore(messages, "grounding"),
      "On topic",
      "Mixed",
      "Loose",
      "Overlaps with the round’s Sim score, but normalized for this bar (60% Sim = 0%). Shows topic fit to that speaker’s sources.",
    ),
    buildScoreboardMetric(
      "persona",
      "Shared wording",
      averageScore(messages, "persona"),
      "High overlap",
      "Some overlap",
      "Low overlap",
      "How many of the same words appear in both the reply and the source passages. A low % means they rephrased ideas; it does not mean they ignored the sources.",
    ),
    buildScoreboardMetric(
      "debate",
      "Diversity",
      averageScore(messages, "debate"),
      "Very different",
      "Somewhat different",
      "Similar wording",
      "Convo average of how different each reply’s wording is from the previous speaker. High means different words—not a deeper clash of ideas.",
    ),
  ];

  const judgeFaithfulness = averageJudgeScore(messages, "faithfulness");
  const judgePersona = averageJudgeScore(messages, "persona");
  if (judgeFaithfulness !== null || judgePersona !== null) {
    scoreboardMetrics.push(
      buildScoreboardMetric(
        "judge_faithfulness",
        "Stays with the sources",
        judgeFaithfulness,
        "Well supported",
        "Partly supported",
        "Thinly supported",
        "An independent review of whether the reply sticks to what that speaker’s sources actually say.",
      ),
      buildScoreboardMetric(
        "judge_persona",
        "Sounds like them",
        judgePersona,
        "In character",
        "Somewhat in character",
        "Out of character",
        "An independent review of whether the reply feels like that historical figure—tone, values, and manner of arguing.",
      ),
    );
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
    convoCostUsd,
    scoreboardMetrics,
    vocalShareRows,
  };
  // deps: all inputs — recompute only when telemetry data actually changes
  }, [servicesState, convoCostUsd, transcriptTokenEstimate, messages, roleBreakdown, onlineServices, serviceRows]);
}