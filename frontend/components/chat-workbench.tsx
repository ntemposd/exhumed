// ChatWorkbench is the composition root for the frontend. It connects durable
// client state, backend-facing hooks, view-model derivation, and presentational
// workbench surfaces.
"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { AppNavbar, DiscussionPanel, SpeakerSelectorModal, TelemetryPanel } from "./renderers";
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
const AGENTS_CACHE_TTL_MS = 5 * 60_000;
const SERVICES_CACHE_TTL_MS = 60_000;

export function ChatWorkbench() {
  // Session + workspace chrome state that belongs at the composition root.
  const [sessionId, setSessionId] = useState("");
  const [targetEntropy, setTargetEntropy] = useState(0.7);
  const [isSpeakerModalOpen, setIsSpeakerModalOpen] = useState(false);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const telemetrySidebarRef = useRef<HTMLElement | null>(null);
  const telemetrySidebarUserScrolledRef = useRef(false);
  const { topic, setTopic, topicEditorRef, hasHydratedTopic } = useTopicEditorState({
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

  function issueSessionId(nextSessionId = makeSessionId()) {
    setSessionId(nextSessionId);
    window.localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
    return nextSessionId;
  }

  const debateController = useDebateController({
    agents,
    selectedAgents,
    sessionId,
    topic,
    targetEntropy,
    issueSessionId,
    makeSessionId,
  });
  const {
    messages,
    discussionActive,
    debateEntropy,
    statusNote,
    controlError,
    isWipingSession,
    isDownloadingTranscript,
    hasMessages,
    startButtonLabel,
    wipeDebate,
    renewSession,
    downloadTranscript,
    startDebate,
    haltDebate,
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
      }
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(ENTROPY_STORAGE_KEY, String(targetEntropy));
  }, [targetEntropy]);

  useEffect(() => {
    if (!isSpeakerModalOpen) {
      return;
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsSpeakerModalOpen(false);
      }
    }

    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isSpeakerModalOpen]);

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

  const legendEntries = agents.map(getLegendDetails);
  const selectedCouncil = selectedAgents
    .map((agentId) => legendEntries.find((legend) => legend.agent_id === agentId))
    .filter((legend): legend is LegendDetails => Boolean(legend));
  const transcriptTokenEstimate = estimateTokenCount(
    messages.filter((message) => !message.isThinking).map((message) => message.message).join(" "),
  );
  const serviceRows = services?.services ?? [];
  const onlineServices = serviceRows.filter((service) => service.status?.toUpperCase() === "ONLINE").length;
  const roleBreakdown = getRoleBreakdown(messages);
  const sessionBurnUsd = calculateSessionBurnUsd(messages);
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
    debateEntropy,
  });

  function toggleCouncilMember(agentId: string) {
    // Council changes are blocked during a live round so the speaking order and
    // transcript semantics stay stable for the active session.
    if (discussionActive) {
      return;
    }

    setSelectedAgents((currentSelection) => {
      if (currentSelection.includes(agentId)) {
        return currentSelection.filter((selectedId) => selectedId !== agentId);
      }

      return [...currentSelection, agentId];
    });
  }

  function openSpeakerModal() {
    setIsSpeakerModalOpen(true);
  }

  function closeSpeakerModal() {
    setIsSpeakerModalOpen(false);
  }

  function handleStartDebate() {
    startDebate();
  }

  function handleRenewSession() {
    renewSession();
  }

  return (
    <main className="shell">
      <AppNavbar />

      <section className="workspace">
        <DiscussionPanel
          topic={topic}
          hasHydratedTopic={hasHydratedTopic}
          topicEditorRef={topicEditorRef}
          discussionActive={discussionActive}
          selectedCouncil={selectedCouncil}
          targetEntropy={targetEntropy}
          controlError={controlError}
          sessionId={sessionId}
          hasMessages={hasMessages}
          isWipingSession={isWipingSession}
          isDownloadingTranscript={isDownloadingTranscript}
          startButtonLabel={startButtonLabel}
          transcriptState={transcriptState}
          messages={messages}
          transcriptRef={transcriptRef}
          onTopicChange={setTopic}
          onOpenSpeakerModal={openSpeakerModal}
          onToggleCouncilMember={toggleCouncilMember}
          onTargetEntropyChange={setTargetEntropy}
          onStartDebate={handleStartDebate}
          onHaltDebate={haltDebate}
          onWipeDebate={wipeDebate}
          onDownloadTranscript={downloadTranscript}
          onRenewSession={handleRenewSession}
        />

        <TelemetryPanel viewModel={telemetryViewModel} containerRef={telemetrySidebarRef} />
      </section>

      <SpeakerSelectorModal
        isOpen={isSpeakerModalOpen}
        discussionActive={discussionActive}
        agents={agents}
        legendEntries={legendEntries}
        selectedAgents={selectedAgents}
        catalogState={legendCatalogState}
        onClose={closeSpeakerModal}
        onToggleCouncilMember={toggleCouncilMember}
      />

      <footer className="siteFooter">
        Built with ❤️ by <a className="siteFooterLink" href="https://ntemposd.me" target="_blank" rel="noreferrer">ntemposd</a>
      </footer>
    </main>
  );
}
