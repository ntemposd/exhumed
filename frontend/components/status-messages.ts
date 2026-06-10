// Maps backend / technical status strings to EXHUMED-themed copy.
// Header (transcript status line): generic, static — no live retry countdown.
// Thinking bubbles: detailed copy with live countdown. See docs/ui-messages.md.
import type { ProcessTurnStreamStatus } from "@/lib/types";

const RETRY_COUNTDOWN_PATTERN = /(?:retrying in|wait for)\s+([\d.]+)\s*s/i;
const THEMED_RETRY_COUNTDOWN_PATTERN = /^The ether is congested\. (?:Retrying in|Wait for)\s+[\d.]+s$/i;
const THROTTLE_PATTERN = /rate limit|request throttled|\b429\b|llm rate limit|quota exhausted/i;

export const THROTTLE_STATUS_HEADER = "The ether is congested";
export const QUOTA_EXHAUSTED_STATUS_HEADER = "The ether is exhausted. The daily quota is spent.";

export function parseRetryCountdownSeconds(message: string): number | null {
  const match = message.match(RETRY_COUNTDOWN_PATTERN);
  if (!match) {
    return null;
  }

  const seconds = Number.parseFloat(match[1]);
  return Number.isFinite(seconds) ? seconds : null;
}

export function isRetryCountdownStatusMessage(message?: string | null): boolean {
  if (!message?.trim()) {
    return false;
  }

  return RETRY_COUNTDOWN_PATTERN.test(message) || THEMED_RETRY_COUNTDOWN_PATTERN.test(message.trim());
}

export function isThrottledStatusMessage(message?: string | null): boolean {
  if (!message?.trim()) {
    return false;
  }

  return THROTTLE_PATTERN.test(message) || RETRY_COUNTDOWN_PATTERN.test(message);
}

/** Live countdown — thinking bubbles only. */
export function themeRetryCountdownMessage(remainingSeconds: number): string {
  if (remainingSeconds <= 0.05) {
    return THROTTLE_STATUS_HEADER;
  }

  return `${THROTTLE_STATUS_HEADER}. Wait for ${remainingSeconds.toFixed(1)}s`;
}

/** Detailed stream status for the active speaker's thinking bubble. */
export function themeThinkingBubbleStatus(event: ProcessTurnStreamStatus): string {
  if (event.stage === "retrying") {
    const seconds = event.retry_after_seconds ?? parseRetryCountdownSeconds(event.message);
    if (seconds !== null && seconds !== undefined) {
      return themeRetryCountdownMessage(seconds);
    }

    return THROTTLE_STATUS_HEADER;
  }

  return themeHeaderStatusNote(event.message);
}

/** Static status for the transcript header — never includes a live retry countdown. */
export function themeHeaderStatusNote(message: string): string {
  const trimmed = message.trim();
  if (!trimmed) {
    return trimmed;
  }

  if (isRetryCountdownStatusMessage(trimmed) || isThrottledStatusMessage(trimmed)) {
    if (/quota exhausted|daily token quota/i.test(trimmed)) {
      return QUOTA_EXHAUSTED_STATUS_HEADER;
    }

    return THROTTLE_STATUS_HEADER;
  }

  if (/turn execution failed/i.test(trimmed)) {
    return "The séance was interrupted.";
  }

  if (/agent failed to produce a response/i.test(trimmed)) {
    return "The voice did not return.";
  }

  return trimmed;
}

/** Static header label derived from a stream status event. */
export function themeHeaderStatusForStream(event: ProcessTurnStreamStatus): string {
  if (event.stage === "retrying") {
    return THROTTLE_STATUS_HEADER;
  }

  if (event.stage === "error") {
    return themeHeaderStatusNote(event.message);
  }

  return themeHeaderStatusNote(event.message);
}

/** @deprecated Use themeThinkingBubbleStatus for stream events or themeHeaderStatusNote for header. */
export function themeStreamStatusMessage(event: ProcessTurnStreamStatus): string {
  return themeThinkingBubbleStatus(event);
}

/** Transcript header label for the current debate phase. */
export function resolveTranscriptStatusLabel(statusNote: string, phase: "idle" | "running" | "ready" | "error"): string {
  const themed = themeHeaderStatusNote(statusNote);

  // During an active turn the thinking bubble owns throttle detail — keep header generic or hidden.
  if (phase === "running" && (isRetryCountdownStatusMessage(themed) || themed === THROTTLE_STATUS_HEADER)) {
    return "";
  }

  if ((phase === "ready" || phase === "idle") && isRetryCountdownStatusMessage(themed)) {
    return "";
  }

  return themed;
}

export function themeStatusMessage(
  message: string,
  options?: { retryAfterSeconds?: number | null },
): string {
  void options;
  return themeHeaderStatusNote(message);
}
