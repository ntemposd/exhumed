// useDebateController owns the live debate lifecycle: turn streaming, pause /
// resume behavior, session reset flows, and transcript export actions.
import { useEffect, useRef, useState } from "react";

import { backendUrl } from "@/lib/config";

import { apiFetch, getRequestFailureMessage, getResponseErrorMessage } from "@/lib/http";
import type { Agent, ProcessTurnStreamEvent, ProcessTurnStreamFinal, ProcessTurnStreamStatus } from "@/lib/types";

import type { DebateMessage } from "../types";
import { ENTROPY_PROFILES, getStyleIndex } from "../utils";

const STREAM_REVEAL_CHARS_PER_FRAME = 4;

// Tone palette for PDF export — index-aligned with the CSS --tone-N variables
// so the same agent always gets the same color in both the UI and exported PDF.
const TONE_COLORS = [
  "#4A7A98", "#A07832", "#3A6A88", "#5E7830", "#9E4A40",
  "#8A3D36", "#B0605A", "#5488A8", "#B28A3E", "#906825",
  "#4E6826", "#6C8840", "#C49840", "#886020", "#306078", "#5C8EB4",
];

function agentToneColor(agentId: string): string {
  return TONE_COLORS[getStyleIndex(agentId)] ?? TONE_COLORS[0];
}

function esc(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildPdfHtml(topic: string, messages: DebateMessage[], sessionId: string): string {
  const date = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });

  // Group by round number
  const roundMap = new Map<number, DebateMessage[]>();
  for (const msg of messages) {
    const r = msg.round_number ?? 1;
    if (!roundMap.has(r)) roundMap.set(r, []);
    roundMap.get(r)!.push(msg);
  }

  const roundsHtml = [...roundMap.entries()].map(([roundNum, roundMessages]) => {
    const turns = roundMessages.map((msg) => {
      const color = agentToneColor(msg.agent_id);
      return `
        <article style="margin-bottom:12px;padding:12px 14px;border:1.5px solid rgba(20,17,15,0.22);border-left:4px solid ${color};background:#F4EEDA;page-break-inside:avoid;">
          <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px;">
            <span style="font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:${color};">${esc(msg.display_name)}</span>
            <span style="font-size:8px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#6b6560;">Turn ${msg.turn_number}</span>
          </div>
          <p style="margin:0;font-size:11px;line-height:1.65;color:#14110f;">${esc(msg.message)}</p>
        </article>`;
    }).join("");

    return `
      <section style="margin-bottom:24px;">
        <div style="font-size:9px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#6b6560;padding-bottom:6px;border-bottom:1px dashed rgba(20,17,15,0.28);margin-bottom:12px;">
          Round ${String(roundNum).padStart(2, "0")} &middot; ${roundMessages.length} ${roundMessages.length === 1 ? "turn" : "turns"}
        </div>
        ${turns}
      </section>`;
  }).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Exhumed — ${esc(topic)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'IBM Plex Mono', monospace;
      background: #E8DCBA;
      color: #14110f;
      padding: 48px 52px;
      font-size: 12px;
      line-height: 1.6;
    }
    @media print {
      body { background: #E8DCBA; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
  </style>
  <script>window.onload = function() { setTimeout(function() { window.print(); }, 600); };<\/script>
</head>
<body>
  <header style="margin-bottom:32px;padding-bottom:14px;border-bottom:3px solid #14110f;">
    <div style="font-size:18px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;">Exhumed</div>
    <div style="font-size:12px;color:#6b6560;margin-top:6px;letter-spacing:0.04em;">${esc(topic)}</div>
    <div style="font-size:9px;color:#6b6560;margin-top:4px;letter-spacing:0.1em;text-transform:uppercase;">${date} &middot; ${sessionId.slice(0, 8).toUpperCase()}</div>
  </header>
  ${roundsHtml}
</body>
</html>`;
}

// Vercel AI SDK data-stream lines have the form:  PREFIX:JSON\n
//   0:"token"      → text chunk
//   8:[{...}]      → message annotation (retry status)
//   2:[{...}]      → data annotation (final turn metadata)
//   d:{...}        → finish signal (ignored)
function parseDataStreamLine(line: string): ProcessTurnStreamEvent | null {
  const colon = line.indexOf(":");
  if (colon === -1) return null;
  const prefix = line.slice(0, colon);
  try {
    const value = JSON.parse(line.slice(colon + 1)) as unknown;
    if (prefix === "0") {
      return { type: "chunk", content: value as string };
    }
    if (prefix === "8" && Array.isArray(value) && value.length > 0) {
      return value[0] as ProcessTurnStreamStatus;
    }
    if (prefix === "2" && Array.isArray(value) && value.length > 0) {
      return value[0] as ProcessTurnStreamFinal;
    }
  } catch {
    // malformed line — skip
  }
  return null;
}

type ResetDebateStateOptions = {
  nextSessionId?: string;
  nextStatusNote?: string;
  nextControlError?: string;
};

type UseDebateControllerOptions = {
  agents: Agent[];
  selectedAgents: string[];
  sessionId: string;
  topic: string;
  defaultTopic: string;
  targetEntropy: number;
  issueSessionId: (nextSessionId?: string) => string;
  makeSessionId: () => string;
  onTopicChange: (topic: string) => void;
};

export function useDebateController({
  agents,
  selectedAgents,
  sessionId,
  topic,
  defaultTopic,
  targetEntropy,
  issueSessionId,
  makeSessionId,
  onTopicChange,
}: UseDebateControllerOptions) {
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [discussionActive, setDiscussionActive] = useState(false);
  const [turnCount, setTurnCount] = useState(0);
  const [currentAgentIndex, setCurrentAgentIndex] = useState(0);
  const [statusNote, setStatusNote] = useState("Standby.");
  const [controlError, setControlError] = useState("");
  const [isWipingSession, setIsWipingSession] = useState(false);
  const [isDownloadingTranscript, setIsDownloadingTranscript] = useState(false);
  const [isDebatePaused, setIsDebatePaused] = useState(false);
  const [roundScrollKey, setRoundScrollKey] = useState(0);

  const turnInFlightRef = useRef(false);
  const resetSequenceRef = useRef(0);
  const currentTurnAbortControllerRef = useRef<AbortController | null>(null);
  const lastStartedTopicRef = useRef("");
  const pauseAfterCurrentTurnRef = useRef(false);
  const activeRoundNumberRef = useRef(0);
  const streamRevealQueuesRef = useRef<Record<string, string>>({});
  const streamRevealFrameRef = useRef<number | null>(null);

  const hasMessages = messages.some((message) => !message.isThinking);
  const startButtonLabel = isDebatePaused ? "▶ Resume" : hasMessages ? "▶ Play" : "▶ Play";

  function clearStreamRevealQueue(messageId?: string) {
    // The streaming renderer buffers partial chunks and reveals them on the
    // animation frame loop below. Clearing removes stale buffered text.
    if (messageId) {
      delete streamRevealQueuesRef.current[messageId];
    } else {
      streamRevealQueuesRef.current = {};
    }

    if (Object.keys(streamRevealQueuesRef.current).length === 0 && streamRevealFrameRef.current !== null) {
      cancelAnimationFrame(streamRevealFrameRef.current);
      streamRevealFrameRef.current = null;
    }
  }

  function scheduleStreamReveal() {
    if (streamRevealFrameRef.current !== null) {
      return;
    }

    const step = () => {
      const queueEntries = Object.entries(streamRevealQueuesRef.current).filter(([, queuedText]) => queuedText.length > 0);
      if (queueEntries.length === 0) {
        streamRevealFrameRef.current = null;
        return;
      }

      const revealBatch = new Map<string, string>();

      for (const [messageId, queuedText] of queueEntries) {
        const revealedText = queuedText.slice(0, STREAM_REVEAL_CHARS_PER_FRAME);
        const remainingText = queuedText.slice(STREAM_REVEAL_CHARS_PER_FRAME);
        revealBatch.set(messageId, revealedText);

        if (remainingText) {
          streamRevealQueuesRef.current[messageId] = remainingText;
        } else {
          delete streamRevealQueuesRef.current[messageId];
        }
      }

      setMessages((currentMessages) =>
        currentMessages.map((message) => {
          const revealedText = revealBatch.get(message.id);
          if (!revealedText) {
            return message;
          }

          return {
            ...message,
            message: `${message.message}${revealedText}`,
          };
        }),
      );

      streamRevealFrameRef.current = requestAnimationFrame(step);
    };

    streamRevealFrameRef.current = requestAnimationFrame(step);
  }

  function resetDebateState(options?: ResetDebateStateOptions) {
    // A reset is the hard boundary between debate sessions, topic pivots, and
    // destructive actions like wipe / renew.
    clearStreamRevealQueue();
    resetSequenceRef.current += 1;
    currentTurnAbortControllerRef.current?.abort();
    currentTurnAbortControllerRef.current = null;
    turnInFlightRef.current = false;
    pauseAfterCurrentTurnRef.current = false;

    if (options?.nextSessionId) {
      issueSessionId(options.nextSessionId);
    }

    setMessages([]);
    setTurnCount(0);
    setCurrentAgentIndex(0);
    setDiscussionActive(false);
    setRoundScrollKey(0);
    activeRoundNumberRef.current = 0;
    lastStartedTopicRef.current = "";
    setIsDebatePaused(false);

    if (options?.nextStatusNote !== undefined) {
      setStatusNote(options.nextStatusNote);
    }

    if (options?.nextControlError !== undefined) {
      setControlError(options.nextControlError);
    }
  }

  async function wipeDebate() {
    if (!sessionId) {
      return;
    }

    setIsWipingSession(true);
    resetDebateState();

    try {
      const response = await apiFetch(`${backendUrl}/sessions/${sessionId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error(await getResponseErrorMessage(response, "Backend cleanup failed"));
      }

      setStatusNote("Debate cleared.");
      setControlError("");
    } catch (clearError) {
      const message = getRequestFailureMessage(clearError, "Debate cleared locally, but backend cleanup failed.");
      setStatusNote(message);
      setControlError(message);
    } finally {
      setIsWipingSession(false);
    }
  }

  function renewSession() {
    resetDebateState({
      nextSessionId: makeSessionId(),
      nextStatusNote: "New session armed.",
      nextControlError: "",
    });
  }

  function downloadTranscript() {
    if (!messages.some((message) => !message.isThinking)) {
      setControlError("No messages to export.");
      setStatusNote("No messages to export.");
      return;
    }

    // Open window synchronously (before any async work) to avoid popup blockers.
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      setControlError("Popup blocked — allow popups and try again.");
      setStatusNote("Popup blocked.");
      return;
    }

    setIsDownloadingTranscript(true);
    setControlError("");
    setStatusNote("Preparing PDF...");

    try {
      const visibleMessages = messages.filter((m) => !m.isThinking);
      const exportTopic = topic.trim() || "Roundtable Session";
      const html = buildPdfHtml(exportTopic, visibleMessages, sessionId);
      printWindow.document.write(html);
      printWindow.document.close();
      setStatusNote("Print dialog opened.");
    } catch (exportError) {
      printWindow.close();
      const message = getRequestFailureMessage(exportError, "Export failed");
      setControlError(message);
      setStatusNote(message);
    } finally {
      setIsDownloadingTranscript(false);
    }
  }

  function startDebate() {
    let normalizedTopic = topic.trim();

    if (!normalizedTopic) {
      normalizedTopic = defaultTopic;
      onTopicChange(defaultTopic);
    }

    if (normalizedTopic.length > 255) {
      setControlError(`Topic is too long (${normalizedTopic.length}/255 characters).`);
      setStatusNote("Topic exceeds the 255 character limit.");
      return false;
    }

    if (selectedAgents.length === 0) {
      setControlError("Draft at least one legend.");
      setStatusNote("Draft at least one legend.");
      return false;
    }

    const topicChanged =
      messages.some((message) => !message.isThinking)
      && Boolean(lastStartedTopicRef.current)
      && lastStartedTopicRef.current !== normalizedTopic;

    if (topicChanged) {
      resetDebateState({
        nextSessionId: makeSessionId(),
        nextStatusNote: "Topic changed. Started a fresh session.",
      });
    }

    const canResumeQueuedSpeaker =
      !topicChanged
      && currentAgentIndex >= 0
      && currentAgentIndex < selectedAgents.length
      && (isDebatePaused || currentAgentIndex > 0);
    const shouldAnchorUpcomingRound = !canResumeQueuedSpeaker || currentAgentIndex === 0;

    setControlError("");
    pauseAfterCurrentTurnRef.current = false;
    setIsDebatePaused(false);

    if (!canResumeQueuedSpeaker) {
      setCurrentAgentIndex(0);
    }

    if (shouldAnchorUpcomingRound) {
      activeRoundNumberRef.current += 1;
      setRoundScrollKey((currentValue) => currentValue + 1);
    }

    setDiscussionActive(true);
    lastStartedTopicRef.current = normalizedTopic;
    setStatusNote(canResumeQueuedSpeaker ? "Round resumed." : "Round armed.");
    return true;
  }

  function haltDebate() {
    setControlError("");

    if (turnInFlightRef.current) {
      pauseAfterCurrentTurnRef.current = true;
      setStatusNote("Pausing after current speaker.");
      return;
    }

    pauseAfterCurrentTurnRef.current = false;
    setDiscussionActive(false);
    setIsDebatePaused(true);
    setStatusNote("Debate paused.");
  }

  useEffect(() => {
    return () => {
      if (streamRevealFrameRef.current !== null) {
        cancelAnimationFrame(streamRevealFrameRef.current);
      }
    };
  }, []);

  useEffect(() => {
    // This effect is the turn runner. It advances exactly one speaker at a time
    // and only re-arms once the previous stream has completed.
    if (!discussionActive || !sessionId || !topic.trim() || selectedAgents.length === 0) {
      return;
    }

    if (currentAgentIndex >= selectedAgents.length) {
      setDiscussionActive(false);
      setCurrentAgentIndex(0);
      setStatusNote("Round complete.");
      return;
    }

    if (turnInFlightRef.current) {
      return;
    }

    const currentAgentId = selectedAgents[currentAgentIndex];
    const currentAgent = agents.find((agent) => agent.agent_id === currentAgentId);
    const currentTurnNumber = turnCount + 1;
    const currentRoundNumber = Math.max(activeRoundNumberRef.current, 1);
    const thinkingId = `thinking-${currentAgentId}-${currentTurnNumber}`;
    const displayName = currentAgent?.display_name ?? currentAgentId;
    const requestResetSequence = resetSequenceRef.current;
    const abortController = new AbortController();
    const slowTurnTimer = window.setTimeout(() => {
      if (requestResetSequence === resetSequenceRef.current && turnInFlightRef.current) {
        setStatusNote(`${displayName} is taking longer than usual. Waiting on the backend...`);
      }
    }, 12000);

    turnInFlightRef.current = true;
    currentTurnAbortControllerRef.current = abortController;
    setControlError("");
    setStatusNote(`Running ${displayName}...`);
    setMessages((currentMessages) => [
      ...currentMessages,
      {
        id: thinkingId,
        agent_id: currentAgentId,
        display_name: displayName,
        message: "",
        round_number: currentRoundNumber,
        turn_number: currentTurnNumber,
        created_at: new Date().toISOString(),
        isThinking: true,
      },
    ]);

    void (async () => {
      try {
        const response = await apiFetch(`${backendUrl}/process-turn/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          signal: abortController.signal,
          body: JSON.stringify({
            session_id: sessionId,
            topic: topic.trim(),
            agent_id: currentAgentId,
            temperature: targetEntropy,
            entropy_profile: ENTROPY_PROFILES.find((p) => p.value === targetEntropy)?.label ?? "Balanced Debate",
            turn_number: currentTurnNumber,
          }),
        });

        if (requestResetSequence !== resetSequenceRef.current) {
          return;
        }

        if (!response.ok) {
          throw new Error(await getResponseErrorMessage(response, "Turn execution failed"));
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("Turn stream was unavailable");
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmedLine = line.trim();
            if (!trimmedLine) {
              continue;
            }

            const event = parseDataStreamLine(trimmedLine);
            if (event === null) continue;
            if (requestResetSequence !== resetSequenceRef.current) {
              return;
            }

            if (event.type === "chunk") {
              streamRevealQueuesRef.current[thinkingId] = `${streamRevealQueuesRef.current[thinkingId] ?? ""}${event.content}`;
              scheduleStreamReveal();
              continue;
            }

            if (event.type === "status") {
              if (event.stage === "error") {
                throw new Error(event.message || "Turn execution failed");
              }
              setStatusNote(event.message);
              setMessages((currentMessages) =>
                currentMessages.map((message) =>
                  message.id === thinkingId
                    ? {
                        ...message,
                        thinkingStatus: event.message,
                      }
                    : message,
                ),
              );
              continue;
            }

            clearStreamRevealQueue(thinkingId);
            setMessages((currentMessages) =>
              currentMessages.map((message) =>
                message.id === thinkingId
                  ? {
                      ...message,
                      id: event.message_id,
                      agent_id: event.agent_id,
                      display_name: event.display_name,
                      message: event.message,
                      round_number: message.round_number ?? currentRoundNumber,
                      turn_number: event.turn_number,
                      created_at: event.created_at,
                      telemetry: event.telemetry,
                      execution_metrics: event.execution_metrics,
                      isThinking: false,
                      thinkingStatus: undefined,
                    }
                  : message,
              ),
            );
            setTurnCount((currentTurnCount) => currentTurnCount + 1);

            const shouldPauseAfterCurrentTurn = pauseAfterCurrentTurnRef.current;
            pauseAfterCurrentTurnRef.current = false;

            const isLastSpeakerInRound = currentAgentIndex + 1 >= selectedAgents.length;
            if (isLastSpeakerInRound) {
              setDiscussionActive(false);
              setCurrentAgentIndex(0);
              setIsDebatePaused(false);
              setStatusNote("Round complete.");
            } else if (shouldPauseAfterCurrentTurn) {
              setDiscussionActive(false);
              setCurrentAgentIndex(currentAgentIndex + 1);
              setIsDebatePaused(true);
              setStatusNote("Debate paused.");
            } else {
              const nextAgentId = selectedAgents[currentAgentIndex + 1];
              const nextAgentName = agents.find((agent) => agent.agent_id === nextAgentId)?.display_name ?? nextAgentId;
              setCurrentAgentIndex(currentAgentIndex + 1);
              setIsDebatePaused(false);
              setStatusNote(`Queued ${nextAgentName}.`);
            }
            return;
          }
        }

        throw new Error("Turn stream ended before final payload was received");
      } catch (turnError) {
        if (abortController.signal.aborted || requestResetSequence !== resetSequenceRef.current) {
          return;
        }

        const message = getRequestFailureMessage(turnError, "Turn execution failed");
        clearStreamRevealQueue(thinkingId);
        setControlError(message);
        setStatusNote(message);
        setDiscussionActive(false);
        setCurrentAgentIndex(0);
        setMessages((currentMessages) =>
          currentMessages.map((message) =>
            message.id === thinkingId
              ? {
                  ...message,
                  message: "Agent failed to produce a response.",
                  round_number: message.round_number ?? currentRoundNumber,
                  isThinking: false,
                  failed: true,
                  created_at: new Date().toISOString(),
                }
              : message,
          ),
        );
      } finally {
        if (currentTurnAbortControllerRef.current === abortController) {
          currentTurnAbortControllerRef.current = null;
          turnInFlightRef.current = false;
        }
        window.clearTimeout(slowTurnTimer);
      }
    })();
  }, [agents, currentAgentIndex, discussionActive, selectedAgents, sessionId, targetEntropy, topic, turnCount]);

  return {
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
    renewSession,
  };
}