// This hook centralizes coarse UI state derivation so the rest of the workbench
// consumes a uniform language for loading, refreshing, empty, and error states.
import { useMemo } from "react";

import type { Agent, ServiceStatus } from "@/lib/types";

import type { AsyncViewState, DebateMessage, TranscriptViewState } from "../types";

type UseWorkbenchViewStateOptions = {
  agents: Agent[];
  agentsError: string;
  isLoadingAgents: boolean;
  isRefreshingAgents: boolean;
  serviceRows: ServiceStatus[];
  servicesError: string;
  isLoadingServices: boolean;
  isRefreshingServices: boolean;
  onlineServices: number;
  messages: DebateMessage[];
  discussionActive: boolean;
  controlError: string;
  statusNote: string;
};

export function useWorkbenchViewState({
  agents,
  agentsError,
  isLoadingAgents,
  isRefreshingAgents,
  serviceRows,
  servicesError,
  isLoadingServices,
  isRefreshingServices,
  onlineServices,
  messages,
  discussionActive,
  controlError,
  statusNote,
}: UseWorkbenchViewStateOptions) {
  const legendCatalogState = useMemo<AsyncViewState>(() => {
    if (agentsError && agents.length === 0) {
      return { phase: "error", summary: "Legend registry unavailable.", detail: agentsError };
    }
    if (isLoadingAgents && agents.length === 0) {
      return { phase: "loading", summary: "Recovering legend registry..." };
    }
    if (isRefreshingAgents && agents.length > 0) {
      return { phase: "refreshing", summary: "Refreshing registered legends..." };
    }
    if (agents.length === 0) {
      return { phase: "empty", summary: "No legends available." };
    }
    return { phase: "ready", summary: `${agents.length} legends available.` };
  }, [agents, agentsError, isLoadingAgents, isRefreshingAgents]);

  const servicesState = useMemo<AsyncViewState>(() => {
    if (servicesError && serviceRows.length === 0) {
      return { phase: "error", summary: "Service checks unavailable.", detail: servicesError };
    }
    if (isLoadingServices && serviceRows.length === 0) {
      return { phase: "loading", summary: "Checking services..." };
    }
    if (isRefreshingServices && serviceRows.length > 0) {
      return { phase: "refreshing", summary: `Services (${onlineServices}/${serviceRows.length})`, detail: "Refreshing live checks..." };
    }
    if (serviceRows.length === 0) {
      return { phase: "empty", summary: "Open services to run live checks." };
    }
    return { phase: "ready", summary: `Services (${onlineServices}/${serviceRows.length})` };
  }, [serviceRows, servicesError, isLoadingServices, isRefreshingServices, onlineServices]);

  const transcriptState = useMemo<TranscriptViewState>(() => {
    if (controlError && messages.length === 0) {
      return {
        phase: "error",
        statusLabel: controlError,
        emptyMessage: "The chamber stalled before the first response. Adjust the council or topic and try again.",
      };
    }
    if (discussionActive || messages.some((message) => message.isThinking)) {
      return {
        phase: "running",
        statusLabel: statusNote,
        emptyMessage: "The chamber is assembling. First responses will appear here as the round begins.",
      };
    }
    if (messages.length === 0) {
      return { phase: "idle", statusLabel: statusNote, emptyMessage: "Draft the council, set the theme, and start a convo." };
    }
    return { phase: "ready", statusLabel: statusNote, emptyMessage: "" };
  }, [controlError, discussionActive, messages, statusNote]);

  return { legendCatalogState, servicesState, transcriptState };
}