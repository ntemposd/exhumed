// Utility helpers in this file are intentionally stateless so hooks and
// presentational components can share formatting and lightweight derivation.
import legendCatalog, { isAgentSelectable } from "@/lib/legends";
import type { Agent } from "@/lib/types";

import type { DebateMessage, LegendDetails } from "./types";

const DEFAULT_COUNCIL_AGENT_IDS = ["agt_001", "agt_002", "agt_003", "agt_004"];

export type AgentArchetype = "thinker" | "commander" | "creator" | "strategist";

// Maps each known agent to one of four visual archetype buckets.
// Thinkers: Socrates, Ada Lovelace, Marie Curie, Nietzsche, Tesla
// Commanders: Napoleon, Marcus Aurelius, Cleopatra
// Creators: Steve Jobs, Da Vinci, Marie Antoinette, Frida Kahlo, Dalí
// Strategists: Sun Tzu, Borges, Trotsky
const AGENT_ARCHETYPE_MAP: Record<string, AgentArchetype> = {
  agt_001: "thinker",
  agt_002: "creator",
  agt_003: "strategist",
  agt_004: "commander",
  agt_005: "commander",
  agt_006: "commander",
  agt_007: "creator",
  agt_008: "thinker",
  agt_009: "thinker",
  agt_010: "strategist",
  agt_011: "strategist",
  agt_012: "thinker",
  agt_013: "thinker",
  agt_014: "creator",
  agt_015: "creator",
  agt_016: "creator",
};

export function getAgentArchetype(agentId: string): AgentArchetype {
  return AGENT_ARCHETYPE_MAP[agentId] ?? "thinker";
}

// Tone presets map UI labels to LLM temperature values — shared by the
// debate controller (API payload) and the discussion panel (Tone selector).
export const TONE_PROFILES = [
  { label: "Steady", value: 0 },
  { label: "Balanced", value: 0.75 },
  { label: "Unbound", value: 1.5 },
] as const;

export type ToneProfile = (typeof TONE_PROFILES)[number];

export const DEFAULT_TONE_TEMPERATURE: number = TONE_PROFILES[1].value;

export function resolveToneProfile(temperature: number): ToneProfile {
  return TONE_PROFILES.reduce((closest, profile) => {
    return Math.abs(profile.value - temperature) < Math.abs(closest.value - temperature) ? profile : closest;
  }, TONE_PROFILES[0]);
}

export function resolveToneTemperature(temperature: number): number {
  return resolveToneProfile(temperature).value;
}

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
    return Math.abs(Number.parseInt(String(agentId).split("_").at(-1) ?? "0", 10)) % 16;
  } catch {
    return Math.abs(agentId.split("").reduce((sum, character) => sum + character.charCodeAt(0), 0)) % 16;
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
  const availableIds = new Set(
    agents.filter((agent) => isAgentSelectable(agent.agent_id)).map((agent) => agent.agent_id),
  );
  const seededDefaults = DEFAULT_COUNCIL_AGENT_IDS.filter((agentId) => availableIds.has(agentId));

  if (seededDefaults.length > 0) {
    return seededDefaults;
  }

  return agents
    .filter((agent) => isAgentSelectable(agent.agent_id))
    .slice(0, 4)
    .map((agent) => agent.agent_id);
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

export function calculateConvoCostUsd(messages: DebateMessage[]) {
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

export function formatConvoCostUsd(amount: number): string {
  if (amount <= 0) {
    return "$0.000000";
  }

  if (amount < 1) {
    return `$${amount.toFixed(6)}`;
  }

  return `$${amount.toFixed(2)}`;
}

export function getLegendDetails(agent: Agent): LegendDetails {
  const registryMatch = legendCatalog.find((legend) => legend.agent_id === agent.agent_id);
  const selectable = isAgentSelectable(agent.agent_id);
  return {
    agent_id: agent.agent_id,
    display_name: registryMatch?.display_name ?? agent.display_name,
    archetype: registryMatch?.archetype ?? "Council Member",
    selectable,
  };
}