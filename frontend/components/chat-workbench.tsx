// ChatWorkbench is the composition root for the frontend. It connects durable
// client state, backend-facing hooks, view-model derivation, and presentational
// workbench surfaces.
"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { AppNavbar, DiscussionPanel, TelemetryPanel } from "./renderers";
import type { LegendDetails } from "./types";
import { useAgentsCatalog, useDebateController, useServicesStatus, useTopicEditorState } from "./hooks";
import { useTelemetryViewModel, useWorkbenchViewState } from "./view-models";
import {
  calculateSessionBurnUsd,
  clampNumber,
  estimateTokenCount,
  getLegendDetails,
  getRoleBreakdown,
  isValidSessionId,
  makeSessionId,
} from "./utils";

const SESSION_STORAGE_KEY = "exhumed-front-session-id";
const COUNCIL_STORAGE_KEY = "exhumed-front-council-agent-ids";
const TOPIC_STORAGE_KEY = "exhumed-front-topic";
const ENTROPY_STORAGE_KEY = "exhumed-front-target-entropy";
const AGENTS_CACHE_KEY = "exhumed-front-agents-cache";
const SERVICES_CACHE_KEY = "exhumed-front-services-cache";
const DEFAULT_TOPIC = "The future of AI in society.";
const DEFAULT_TARGET_ENTROPY = 0;
const AGENTS_CACHE_TTL_MS = 5 * 60_000;
const SERVICES_CACHE_TTL_MS = 60_000;

export function ChatWorkbench() {
  // Session + workspace chrome state that belongs at the composition root.
  const [sessionId, setSessionId] = useState("");
  const [targetEntropy, setTargetEntropy] = useState(DEFAULT_TARGET_ENTROPY);
  const [isCouncilEditing, setIsCouncilEditing] = useState(false);
  const [draftSelectedAgents, setDraftSelectedAgents] = useState<string[]>([]);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const telemetrySidebarRef = useRef<HTMLElement | null>(null);
  const telemetrySidebarUserScrolledRef = useRef(false);
  const { topic, setTopic } = useTopicEditorState({
    storageKey: TOPIC_STORAGE_KEY,
    defaultTopic: DEFAULT_TOPIC,
  });
  const { agents, selectedAgents, setSelectedAgents, agentsError, isLoadingAgents, isRefreshingAgents } = useAgentsCatalog({
    councilStorageKey: COUNCIL_STORAGE_KEY,
    cacheKey: AGENTS_CACHE_KEY,
    cacheTtlMs: AGENTS_CACHE_TTL_MS,
  });
  const { services, servicesError, isLoadingServices, isRefreshingServices } = useServicesStatus({
    cacheKey: SERVICES_CACHE_KEY,
    cacheTtlMs: SERVICES_CACHE_TTL_MS,
  });
  const effectiveSelectedAgents = isCouncilEditing ? draftSelectedAgents : selectedAgents;

  function issueSessionId(nextSessionId = makeSessionId()) {
    setSessionId(nextSessionId);
    window.localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
    return nextSessionId;
  }

  const debateController = useDebateController({
    agents,
    selectedAgents: effectiveSelectedAgents,
    sessionId,
    topic,
    targetEntropy,
    issueSessionId,
    makeSessionId,
  });
  const {
    messages,
    discussionActive,
    statusNote,
    controlError,
    isWipingSession,
    isDownloadingTranscript,
    hasMessages,
    startButtonLabel,
    roundScrollKey,
    wipeDebate,
    downloadTranscript,
    startDebate,
    haltDebate,
    // renewSession intentionally omitted — no UI surface for it yet
  } = debateController;

  useLayoutEffect(() => {
    const storedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY);
    const storedEntropy = window.localStorage.getItem(ENTROPY_STORAGE_KEY);
    const nextSessionId = storedSessionId && isValidSessionId(storedSessionId) ? storedSessionId : makeSessionId();

    setSessionId(nextSessionId);
    window.localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);

    if (storedEntropy) {
      const parsedEntropy = Number(storedEntropy);
      if (!Number.isNaN(parsedEntropy)) {
        setTargetEntropy(clampNumber(parsedEntropy, 0, 1.5));
        return;
      }
    }

    setTargetEntropy(DEFAULT_TARGET_ENTROPY);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(ENTROPY_STORAGE_KEY, String(targetEntropy));
  }, [targetEntropy]);

  useEffect(() => {
    const element = telemetrySidebarRef.current;
    if (!element) {
      return;
    }

    const handleScroll = () => {
      telemetrySidebarUserScrolledRef.current = element.scrollTop > 4;
    };

    handleScroll();
    element.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      element.removeEventListener("scroll", handleScroll);
    };
  }, []);

  useLayoutEffect(() => {
    const element = telemetrySidebarRef.current;
    if (!element || telemetrySidebarUserScrolledRef.current || element.scrollTop <= 0) {
      return;
    }

    element.scrollTop = 0;
  }, [messages]);

  const legendEntries = useMemo(() => agents.map(getLegendDetails), [agents]);
  const selectedCouncil = useMemo(
    () =>
      effectiveSelectedAgents
        .map((agentId) => legendEntries.find((legend) => legend.agent_id === agentId))
        .filter((legend): legend is LegendDetails => Boolean(legend)),
    [effectiveSelectedAgents, legendEntries],
  );
  const serviceRows = services?.services ?? [];
  const onlineServices = serviceRows.filter((service) => service.status?.toUpperCase() === "ONLINE").length;
  const transcriptTokenEstimate = useMemo(
    () => estimateTokenCount(
      messages.filter((message) => !message.isThinking).map((message) => message.message).join(" "),
    ),
    [messages],
  );
  const roleBreakdown = useMemo(() => getRoleBreakdown(messages), [messages]);
  const sessionBurnUsd = useMemo(() => calculateSessionBurnUsd(messages), [messages]);
  const { legendCatalogState, servicesState, transcriptState } = useWorkbenchViewState({
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
  });
  const telemetryViewModel = useTelemetryViewModel({
    servicesState,
    sessionBurnUsd,
    transcriptTokenEstimate,
    messages,
    roleBreakdown,
    onlineServices,
    serviceRows,
  });

  function toggleCouncilMember(agentId: string) {
    // Council changes are blocked during a live round so the speaking order and
    // transcript semantics stay stable for the active session.
    if (discussionActive) {
      return;
    }

    if (isCouncilEditing) {
      setDraftSelectedAgents((currentSelection) => {
        if (currentSelection.includes(agentId)) {
          return currentSelection.filter((selectedId) => selectedId !== agentId);
        }

        return [...currentSelection, agentId];
      });
      return;
    }

    setSelectedAgents((currentSelection) => {
      if (currentSelection.includes(agentId)) {
        return currentSelection.filter((selectedId) => selectedId !== agentId);
      }

      return [...currentSelection, agentId];
    });
  }

  function toggleCouncilEdit() {
    if (discussionActive) {
      return;
    }

    setIsCouncilEditing((currentValue) => {
      if (!currentValue) {
        setDraftSelectedAgents(selectedAgents);
        return true;
      }

      setSelectedAgents(draftSelectedAgents);
      return false;
    });
  }

  function handleStartDebate() {
    if (isCouncilEditing) {
      setSelectedAgents(draftSelectedAgents);
      setIsCouncilEditing(false);
    }

    startDebate();
  }

  return (
    <main className="shell">
      <AppNavbar />

      <section className="workspace">
        <DiscussionPanel
          topic={topic}
          discussionActive={discussionActive}
          selectedCouncil={selectedCouncil}
          targetEntropy={targetEntropy}
          isCouncilEditing={isCouncilEditing}
          controlError={controlError}
          sessionId={sessionId}
          hasMessages={hasMessages}
          roundStartAgentId={effectiveSelectedAgents[0]}
          roundScrollKey={roundScrollKey}
          isWipingSession={isWipingSession}
          isDownloadingTranscript={isDownloadingTranscript}
          startButtonLabel={startButtonLabel}
          transcriptState={transcriptState}
          messages={messages}
          transcriptRef={transcriptRef}
          legendEntries={legendEntries}
          onTopicChange={setTopic}
          onToggleCouncilEdit={toggleCouncilEdit}
          onToggleCouncilMember={toggleCouncilMember}
          onTargetEntropyChange={setTargetEntropy}
          onStartDebate={handleStartDebate}
          onHaltDebate={haltDebate}
          onWipeDebate={wipeDebate}
          onDownloadTranscript={downloadTranscript}
        />

        <TelemetryPanel viewModel={telemetryViewModel} containerRef={telemetrySidebarRef} />
      </section>

      <footer className="siteFooter">
        Built with ❤️ by <a className="siteFooterLink" href="https://ntemposd.me" target="_blank" rel="noreferrer">ntemposd</a>
      </footer>
    </main>
  );
}
