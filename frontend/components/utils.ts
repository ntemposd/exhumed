// Utility helpers in this file are intentionally stateless so hooks and
// presentational components can share formatting and lightweight derivation.
import legendCatalog from "@/lib/legends";
import type { Agent } from "@/lib/types";

import type { DebateMessage, LegendDetails } from "./types";

const DEFAULT_COUNCIL_AGENT_IDS = ["agt_001", "agt_002", "agt_003", "agt_004"];
const INPUT_USD_PER_MILLION = 0.05;
const OUTPUT_USD_PER_MILLION = 0.08;
const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function createUuidV4Fallback() {
  const template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx";
  return template.replace(/[xy]/g, (character) => {
    const randomNibble = Math.floor(Math.random() * 16);
    const nextValue = character === "x" ? randomNibble : (randomNibble & 0x3) | 0x8;
    return nextValue.toString(16);
  });
}

export function makeSessionId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return createUuidV4Fallback();
}

export function isValidSessionId(value: string) {
  return UUID_V4_PATTERN.test(value.trim());
}

export function clampNumber(value: number, minValue: number, maxValue: number) {
  return Math.min(Math.max(value, minValue), maxValue);
}

export function avatarUrlForAgent(agentId: string) {
  return `/avatars/${agentId}.png`;
}

export function getStyleIndex(agentId: string) {
  try {
    return Math.abs(Number.parseInt(String(agentId).split("_").at(-1) ?? "0", 10)) % 5;
  } catch {
    return Math.abs(agentId.split("").reduce((sum, character) => sum + character.charCodeAt(0), 0)) % 5;
  }
}

export function logoUrl() {
  return "/logo.png";
}

export function sanitizeDebateMessageText(text: string, displayName?: string) {
  let cleaned = text.trim();

  if (!cleaned) {
    return cleaned;
  }

  const escapedDisplayName = displayName
    ? displayName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    : null;

  const patterns = [
    escapedDisplayName ? new RegExp(`^\\s*Turn\\s+\\d+\\s*,\\s*${escapedDisplayName}\\s*:\\s*`, "i") : null,
    /^\s*Turn\s+\d+\s*:\s*/i,
    escapedDisplayName ? new RegExp(`^\\s*${escapedDisplayName}\\s*:\\s*`, "i") : null,
  ].filter((pattern): pattern is RegExp => Boolean(pattern));

  for (const pattern of patterns) {
    cleaned = cleaned.replace(pattern, "").trim();
  }

  return cleaned;
}

export function formatMetricNumber(value?: number | null, suffix = "") {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }

  return `${Math.round(value).toLocaleString()}${suffix}`;
}

export function formatFloat(value?: number | null, digits = 2, suffix = "") {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }

  return `${value.toFixed(digits)}${suffix}`;
}

export function formatUsd(value: number) {
  return `$${value.toFixed(value < 0.01 ? 4 : 2)}`;
}

export function estimateTokenCount(text: string) {
  const trimmed = text.trim();
  if (!trimmed) {
    return 0;
  }

  return Math.ceil(trimmed.split(/\s+/).length / 0.75);
}

export function countWords(text: string) {
  const trimmed = text.trim();
  if (!trimmed) {
    return 0;
  }

  return trimmed.split(/\s+/).length;
}

export function getDefaultCouncilAgentIds(agents: Agent[]) {
  const availableIds = new Set(agents.map((agent) => agent.agent_id));
  const seededDefaults = DEFAULT_COUNCIL_AGENT_IDS.filter((agentId) => availableIds.has(agentId));

  if (seededDefaults.length > 0) {
    return seededDefaults;
  }

  return agents.slice(0, 4).map((agent) => agent.agent_id);
}

export function getRoleBreakdown(messages: DebateMessage[]) {
  const buckets = new Map<string, number>();

  for (const message of messages) {
    if (message.isThinking) {
      continue;
    }

    const current = buckets.get(message.display_name) ?? 0;
    buckets.set(message.display_name, current + countWords(sanitizeDebateMessageText(message.message, message.display_name)));
  }

  const totalWords = Array.from(buckets.values()).reduce((sum, value) => sum + value, 0);

  return Array.from(buckets.entries())
    .map(([label, words]) => ({
      label,
      words,
      share: totalWords > 0 ? (words / totalWords) * 100 : 0,
    }))
    .sort((left, right) => right.words - left.words);
}

export function calculateSessionBurnUsd(messages: DebateMessage[]) {
  let promptTokens = 0;
  let completionTokens = 0;
  let estimatedTokens = 0;

  for (const message of messages) {
    if (message.isThinking) {
      continue;
    }

    promptTokens += message.execution_metrics?.prompt_tokens ?? 0;
    completionTokens += message.execution_metrics?.completion_tokens ?? 0;
    estimatedTokens += estimateTokenCount(sanitizeDebateMessageText(message.message, message.display_name));
  }

  if (promptTokens > 0 || completionTokens > 0) {
    return (
      promptTokens * (INPUT_USD_PER_MILLION / 1_000_000) +
      completionTokens * (OUTPUT_USD_PER_MILLION / 1_000_000)
    );
  }

  const blendedRate = ((INPUT_USD_PER_MILLION + OUTPUT_USD_PER_MILLION) / 2) / 1_000_000;
  return estimatedTokens * blendedRate;
}

export function getLegendDetails(agent: Agent): LegendDetails {
  const registryMatch = legendCatalog.find((legend) => legend.agent_id === agent.agent_id);
  return {
    agent_id: agent.agent_id,
    display_name: registryMatch?.display_name ?? agent.display_name,
    archetype: registryMatch?.archetype ?? "Council Member",
  };
}