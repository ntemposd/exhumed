// useDebateController owns the live debate lifecycle: turn streaming, pause /
// resume behavior, session reset flows, and transcript export actions.
import { useEffect, useRef, useState } from "react";

import { backendUrl } from "@/lib/config";
import { getRequestFailureMessage, getResponseErrorMessage } from "@/lib/http";
import type { Agent, ProcessTurnStreamEvent } from "@/lib/types";

import type { DebateMessage } from "../types";
import { clampNumber } from "../utils";

const STREAM_REVEAL_CHARS_PER_FRAME = 4;

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
  targetEntropy: number;
  issueSessionId: (nextSessionId?: string) => string;
  makeSessionId: () => string;
};

export function useDebateController({
  agents,
  selectedAgents,
  sessionId,
  topic,
  targetEntropy,
  issueSessionId,
  makeSessionId,
}: UseDebateControllerOptions) {
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [discussionActive, setDiscussionActive] = useState(false);
  const [turnCount, setTurnCount] = useState(0);
  const [currentAgentIndex, setCurrentAgentIndex] = useState(0);
  const [debateEntropy, setDebateEntropy] = useState<number | null>(null);
  const [statusNote, setStatusNote] = useState("Standby.");
  const [controlError, setControlError] = useState("");
  const [isWipingSession, setIsWipingSession] = useState(false);
  const [isDownloadingTranscript, setIsDownloadingTranscript] = useState(false);
  const [isDebatePaused, setIsDebatePaused] = useState(false);

  const turnInFlightRef = useRef(false);
  const resetSequenceRef = useRef(0);
  const currentTurnAbortControllerRef = useRef<AbortController | null>(null);
  const lastStartedTopicRef = useRef("");
  const pauseAfterCurrentTurnRef = useRef(false);
  const streamRevealQueuesRef = useRef<Record<string, string>>({});
  const streamRevealFrameRef = useRef<number | null>(null);

  const hasMessages = messages.some((message) => !message.isThinking);
  const startButtonLabel = isDebatePaused ? "⏵ Resume Debate" : hasMessages ? "🏁 Advance" : "🏁 Start";

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
    setDebateEntropy(null);
    setDiscussionActive(false);
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
      const response = await fetch(`${backendUrl}/sessions/${sessionId}`, {
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

  async function downloadTranscript() {
    if (!sessionId) {
      return;
    }

    if (!messages.some((message) => !message.isThinking)) {
      setControlError("No messages to export.");
      setStatusNote("No messages to export.");
      return;
    }

    setIsDownloadingTranscript(true);
    setControlError("");
    setStatusNote("Generating transcript...");

    try {
      const response = await fetch(`${backendUrl}/export-pdf/${sessionId}`);

      if (!response.ok) {
        throw new Error(await getResponseErrorMessage(response, "Transcript export failed"));
      }

      const pdfBlob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(pdfBlob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = `exhumed_${sessionId.slice(0, 8)}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(downloadUrl);
      setStatusNote("Transcript ready.");
    } catch (downloadError) {
      const message = getRequestFailureMessage(downloadError, "Transcript export failed");
      setControlError(message);
      setStatusNote(message);
    } finally {
      setIsDownloadingTranscript(false);
    }
  }

  function startDebate() {
    const normalizedTopic = topic.trim();

    if (!normalizedTopic) {
      setControlError("Set a discussion topic first.");
      setStatusNote("Set a discussion topic first.");
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

    setControlError("");
    pauseAfterCurrentTurnRef.current = false;
    setIsDebatePaused(false);

    if (!canResumeQueuedSpeaker) {
      setCurrentAgentIndex(0);
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
        turn_number: currentTurnNumber,
        created_at: new Date().toISOString(),
        isThinking: true,
      },
    ]);

    void (async () => {
      try {
        const response = await fetch(`${backendUrl}/process-turn/stream`, {
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

            const event = JSON.parse(trimmedLine) as ProcessTurnStreamEvent;
            if (requestResetSequence !== resetSequenceRef.current) {
              return;
            }

            if (event.type === "chunk") {
              streamRevealQueuesRef.current[thinkingId] = `${streamRevealQueuesRef.current[thinkingId] ?? ""}${event.content}`;
              scheduleStreamReveal();
              continue;
            }

            if (event.type === "status") {
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
            setDebateEntropy(clampNumber(event.telemetry.entropy, 0, 1));
            setMessages((currentMessages) =>
              currentMessages.map((message) =>
                message.id === thinkingId
                  ? {
                      id: event.message_id,
                      agent_id: event.agent_id,
                      display_name: event.display_name,
                      message: event.message,
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
  };
}