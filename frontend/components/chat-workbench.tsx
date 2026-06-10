// ChatWorkbench is the composition root for the frontend. It connects durable
// client state, backend-facing hooks, view-model derivation, and presentational
// workbench surfaces.
"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { AppNavbar, DiscussionPanel, SiteFooter, TelemetryPanel } from "./renderers";
import type { LegendDetails } from "./types";
import { useAgentsCatalog, useDebateController, useServicesStatus, useTopicEditorState } from "./hooks";
import { useTelemetryViewModel, useWorkbenchViewState } from "./view-models";
import { isAgentSelectable } from "@/lib/legends";

import {
  calculateConvoCostUsd,
  clampNumber,
  DEFAULT_TONE_TEMPERATURE,
  estimateTokenCount,
  getLegendDetails,
  getRoleBreakdown,
  isValidSessionId,
  makeSessionId,
  resolveToneTemperature,
} from "./utils";

const SESSION_STORAGE_KEY = "exhumed-front-session-id";
const COUNCIL_STORAGE_KEY = "exhumed-front-council-agent-ids";
const TOPIC_STORAGE_KEY = "exhumed-front-topic";
const TEMPERATURE_STORAGE_KEY = "exhumed-front-target-temperature";
const AGENTS_CACHE_KEY = "exhumed-front-agents-cache";
const SERVICES_CACHE_KEY = "exhumed-front-services-cache";
const DEFAULT_TOPIC = "The future of AI in society.";
const AGENTS_CACHE_TTL_MS = 5 * 60_000;
const SERVICES_CACHE_TTL_MS = 60_000;

export function ChatWorkbench() {
  // Session + workspace chrome state that belongs at the composition root.
  const [sessionId, setSessionId] = useState("");
  const [targetTemperature, setTargetTemperature] = useState(DEFAULT_TONE_TEMPERATURE);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const telemetrySidebarRef = useRef<HTMLDivElement | null>(null);
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
  const effectiveSelectedAgents = selectedAgents;

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
    defaultTopic: DEFAULT_TOPIC,
    targetTemperature,
    issueSessionId,
    makeSessionId,
    onTopicChange: setTopic,
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
    pauseButtonLabel,
    isPausePending,
    roundScrollKey,
    wipeDebate,
    downloadTranscript,
    startDebate,
    haltDebate,
    // renewSession intentionally omitted — no UI surface for it yet
  } = debateController;

  useLayoutEffect(() => {
    const storedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY);
    const storedTemperature = window.localStorage.getItem(TEMPERATURE_STORAGE_KEY);
    const nextSessionId = storedSessionId && isValidSessionId(storedSessionId) ? storedSessionId : makeSessionId();

    setSessionId(nextSessionId);
    window.localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);

    if (storedTemperature) {
      const parsedTemperature = Number(storedTemperature);
      if (!Number.isNaN(parsedTemperature)) {
        setTargetTemperature(resolveToneTemperature(clampNumber(parsedTemperature, 0, 1.5)));
        return;
      }
    }

    setTargetTemperature(DEFAULT_TONE_TEMPERATURE);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(TEMPERATURE_STORAGE_KEY, String(targetTemperature));
  }, [targetTemperature]);

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
  const convoCostUsd = useMemo(() => calculateConvoCostUsd(messages), [messages]);
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
    convoCostUsd,
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

    if (!isAgentSelectable(agentId)) {
      return;
    }

    setSelectedAgents((currentSelection) => {
      if (currentSelection.includes(agentId)) {
        return currentSelection.filter((selectedId) => selectedId !== agentId);
      }

      return [...currentSelection, agentId];
    });
  }

  function handleStartDebate() {
    startDebate();
  }

  // Mirrors the panel's showTranscriptControls: a convo is "live" once it is
  // running or has produced at least one real (non-thinking) message.
  const isConvoActive = discussionActive || messages.some((message) => !message.isThinking);

  // On mobile, block document scroll while a convo is active so overscroll at
  // the transcript edges cannot chain into the telemetry stack below.
  useEffect(() => {
    const mobileQuery = window.matchMedia("(max-width: 767px)");
    const applyLock = () => {
      const locked = isConvoActive && mobileQuery.matches;
      document.documentElement.style.overflow = locked ? "hidden" : "";
      document.body.style.overflow = locked ? "hidden" : "";
      document.body.style.overscrollBehavior = locked ? "none" : "";
    };

    applyLock();
    mobileQuery.addEventListener("change", applyLock);
    return () => {
      mobileQuery.removeEventListener("change", applyLock);
      document.documentElement.style.overflow = "";
      document.body.style.overflow = "";
      document.body.style.overscrollBehavior = "";
    };
  }, [isConvoActive]);

  useEffect(() => {
    const mobileQuery = window.matchMedia("(max-width: 767px)");
    const syncViewport = () => setIsMobileViewport(mobileQuery.matches);
    syncViewport();
    mobileQuery.addEventListener("change", syncViewport);
    return () => mobileQuery.removeEventListener("change", syncViewport);
  }, []);

  useEffect(() => {
    if (!isConvoActive) {
      setIsSidebarOpen(false);
    }
  }, [isConvoActive]);

  const mobileConvoPane = isConvoActive && isMobileViewport;

  return (
    <main
      className="shell"
      data-convo-active={isConvoActive ? "true" : "false"}
      data-mobile-pane={mobileConvoPane && isSidebarOpen ? "telemetry" : "chat"}
    >
      <AppNavbar />

      <section className="workspace" data-sidebar={isSidebarOpen ? "open" : "closed"}>
        <DiscussionPanel
          topic={topic}
          defaultTopic={DEFAULT_TOPIC}
          discussionActive={discussionActive}
          selectedCouncil={selectedCouncil}
          targetTemperature={targetTemperature}
          controlError={controlError}
          sessionId={sessionId}
          hasMessages={hasMessages}
          roundStartAgentId={effectiveSelectedAgents[0]}
          roundScrollKey={roundScrollKey}
          isWipingSession={isWipingSession}
          isDownloadingTranscript={isDownloadingTranscript}
          startButtonLabel={startButtonLabel}
          pauseButtonLabel={pauseButtonLabel}
          isPausePending={isPausePending}
          transcriptState={transcriptState}
          messages={messages}
          transcriptRef={transcriptRef}
          legendEntries={legendEntries}
          legendCatalogState={legendCatalogState}
          onTopicChange={setTopic}
          onToggleCouncilMember={toggleCouncilMember}
          onTargetTemperatureChange={setTargetTemperature}
          onStartDebate={handleStartDebate}
          onHaltDebate={haltDebate}
          onWipeDebate={wipeDebate}
          onDownloadTranscript={downloadTranscript}
          onOpenTelemetry={() => setIsSidebarOpen(true)}
          showMobileTelemetryTrigger={mobileConvoPane}
        />

        <TelemetryPanel
            viewModel={telemetryViewModel}
            containerRef={telemetrySidebarRef}
            isSidebarOpen={isSidebarOpen}
            mobileConvoPane={mobileConvoPane}
            onToggleSidebar={() => setIsSidebarOpen((v) => !v)}
            onBackToChat={() => setIsSidebarOpen(false)}
          />
      </section>

      {!isConvoActive && (
        <SiteFooter />
      )}
    </main>
  );
}
