// DiscussionTranscript owns transcript-only interaction state such as message
// expansion and animated thinking indicators.
import { useEffect, useRef, useState, type RefObject } from "react";

import type { DebateMessage } from "../types";
import { avatarUrlForAgent, getStyleIndex, sanitizeDebateMessageText } from "../utils";
import styles from "./discussion-transcript.module.css";

const MESSAGE_PREVIEW_LIMIT = 140;

type DiscussionTranscriptProps = {
  emptyStateMessage: string;
  messages: DebateMessage[];
  roundSize: number;
  roundStartAgentId?: string;
  roundScrollKey: number;
  transcriptRef: RefObject<HTMLDivElement | null>;
};

type TranscriptRound = {
  roundNumber: number;
  messages: DebateMessage[];
};

export function DiscussionTranscript({ emptyStateMessage, messages, roundSize, roundStartAgentId, roundScrollKey, transcriptRef }: DiscussionTranscriptProps) {
  const [expandedMessageIds, setExpandedMessageIds] = useState<Record<string, boolean>>({});
  const [collapsedRounds, setCollapsedRounds] = useState<Record<number, boolean>>({});
  const [retryCountdownTick, setRetryCountdownTick] = useState(0);
  const lastMessageStateRef = useRef<{ agentId: string; turnNumber: number; isThinking: boolean } | null>(null);
  const lastScrolledRoundKeyRef = useRef(0);
  const lastAutoCollapsedRoundRef = useRef(0);
  const retryCountdownsRef = useRef<Record<string, { initialSeconds: number; startedAtMs: number; status: string }>>({});
  const normalizedRoundSize = Math.max(roundSize, 1);

  useEffect(() => {
    if (roundScrollKey < lastScrolledRoundKeyRef.current) {
      lastScrolledRoundKeyRef.current = roundScrollKey;
    }

    if (roundScrollKey === 0) {
      lastScrolledRoundKeyRef.current = 0;
      lastAutoCollapsedRoundRef.current = 0;
      lastMessageStateRef.current = null;
      setCollapsedRounds({});
      setExpandedMessageIds({});
    }
  }, [roundScrollKey]);

  function scrollBubbleToViewportTop(targetBubble: HTMLElement) {
    const targetTop = Math.max(window.scrollY + targetBubble.getBoundingClientRect().top, 0);
    const startTop = window.scrollY;
    const travel = targetTop - startTop;

    if (Math.abs(travel) < 2) {
      window.scrollTo({ top: targetTop, behavior: "auto" });
      return;
    }

    const durationMs = 440;
    const startTime = window.performance.now();

    const step = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / durationMs, 1);
      const easedProgress = 1 - Math.pow(1 - progress, 3);

      window.scrollTo({
        top: startTop + travel * easedProgress,
        behavior: "auto",
      });

      if (progress < 1) {
        window.requestAnimationFrame(step);
        return;
      }

      window.scrollTo({ top: targetTop, behavior: "auto" });
    };

    window.requestAnimationFrame(step);
  }

  useEffect(() => {
    const activeRetryIds = new Set<string>();

    for (const message of messages) {
      if (!message.isThinking || !message.thinkingStatus) {
        continue;
      }

      const retryMatch = message.thinkingStatus.match(/retrying in\s+([\d.]+)s?/i);
      if (!retryMatch) {
        continue;
      }

      activeRetryIds.add(message.id);
      const initialSeconds = Number.parseFloat(retryMatch[1]);
      const currentEntry = retryCountdownsRef.current[message.id];

      if (!currentEntry || currentEntry.status !== message.thinkingStatus) {
        retryCountdownsRef.current[message.id] = {
          initialSeconds,
          startedAtMs: window.performance.now(),
          status: message.thinkingStatus,
        };
      }
    }

    for (const messageId of Object.keys(retryCountdownsRef.current)) {
      if (!activeRetryIds.has(messageId)) {
        delete retryCountdownsRef.current[messageId];
      }
    }
  }, [messages]);

  const hasActiveRetryCountdown = messages.some((message) =>
    Boolean(message.isThinking && message.thinkingStatus && /retrying in\s+[\d.]+s?/i.test(message.thinkingStatus)),
  );

  useEffect(() => {
    if (!hasActiveRetryCountdown) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setRetryCountdownTick(window.performance.now());
    }, 100);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [hasActiveRetryCountdown]);

  useEffect(() => {
    // Scroll only when the round-opening speaker finishes after an explicit Start/Advance intent.
    const lastMessage = messages.at(-1);
    if (!lastMessage) {
      return;
    }

    const animationFrameId = window.requestAnimationFrame(() => {
      const previousMessageState = lastMessageStateRef.current;
      const isFirstAnswerOfRound = Boolean(
        !lastMessage.isThinking
        && previousMessageState?.agentId === lastMessage.agent_id
        && previousMessageState?.turnNumber === lastMessage.turn_number
        && previousMessageState.isThinking,
      );
      const isRoundOpeningAnswer = !roundStartAgentId || lastMessage.agent_id === roundStartAgentId;

      if (isFirstAnswerOfRound && isRoundOpeningAnswer && roundScrollKey > lastScrolledRoundKeyRef.current) {
        const targetBubble = transcriptRef.current?.querySelector(
          `article[data-message-id="${lastMessage.id}"]`,
        ) as HTMLElement | null;

        if (targetBubble) {
          lastScrolledRoundKeyRef.current = roundScrollKey;
          scrollBubbleToViewportTop(targetBubble);
        }
      }

      lastMessageStateRef.current = {
        agentId: lastMessage.agent_id,
        turnNumber: lastMessage.turn_number,
        isThinking: Boolean(lastMessage.isThinking),
      };
    });

    return () => {
      window.cancelAnimationFrame(animationFrameId);
    };
  }, [messages, transcriptRef]);

  function getThinkingStatus(messageId: string, explicitStatus?: string): string {
    if (explicitStatus) {
      const retryCountdown = retryCountdownsRef.current[messageId];
      if (retryCountdown) {
        const elapsedSeconds = Math.max((retryCountdownTick - retryCountdown.startedAtMs) / 1000, 0);
        const remainingSeconds = Math.max(retryCountdown.initialSeconds - elapsedSeconds, 0);

        return `Request throttled. Retrying in ${remainingSeconds.toFixed(1)}s`;
      }

      if (/rate limit|retry|\b429\b|\b5\d{2}\b/i.test(explicitStatus)) {
        return "Request throttled";
      }
    }

    return "";
  }

  function isThrottledThinkingStatus(explicitStatus?: string): boolean {
    if (!explicitStatus) {
      return false;
    }

    return /rate limit|retry|\b429\b/i.test(explicitStatus);
  }

  function toggleExpandedMessage(messageId: string) {
    setExpandedMessageIds((currentValue) => ({
      ...currentValue,
      [messageId]: !(currentValue[messageId] ?? false),
    }));
  }

  const bubbleToneClasses = [
    styles.bubbleTone0,
    styles.bubbleTone1,
    styles.bubbleTone2,
    styles.bubbleTone3,
    styles.bubbleTone4,
  ];

  const transcriptRounds = messages.reduce<TranscriptRound[]>((rounds, message) => {
    const roundNumber = Math.max(1, message.round_number ?? Math.ceil(message.turn_number / normalizedRoundSize));
    const existingRound = rounds.at(-1);

    if (!existingRound || existingRound.roundNumber !== roundNumber) {
      rounds.push({ roundNumber, messages: [message] });
      return rounds;
    }

    existingRound.messages.push(message);
    return rounds;
  }, []);

  useEffect(() => {
    if (transcriptRounds.length === 0) {
      setCollapsedRounds({});
      return;
    }

    const latestRoundNumber = transcriptRounds[transcriptRounds.length - 1]?.roundNumber ?? 1;
    if (latestRoundNumber === lastAutoCollapsedRoundRef.current) {
      return;
    }

    lastAutoCollapsedRoundRef.current = latestRoundNumber;
    setCollapsedRounds((currentValue) => {
      const nextValue: Record<number, boolean> = { ...currentValue };
      let changed = false;

      for (const round of transcriptRounds) {
        const nextCollapsed = round.roundNumber < latestRoundNumber;
        nextValue[round.roundNumber] = nextCollapsed;
        if (currentValue[round.roundNumber] !== nextCollapsed) {
          changed = true;
        }
      }

      if (!changed && Object.keys(currentValue).length === Object.keys(nextValue).length) {
        return currentValue;
      }

      return nextValue;
    });
  }, [transcriptRounds]);

  function toggleRound(roundNumber: number) {
    setCollapsedRounds((currentValue) => ({
      ...currentValue,
      [roundNumber]: !(currentValue[roundNumber] ?? false),
    }));
  }

  return (
    <div className={styles.transcript} ref={transcriptRef}>
      {messages.length === 0 ? (
        <div className={styles.emptyState}>
          <p className={styles.emptyStateText}>{emptyStateMessage}</p>
        </div>
      ) : null}
      {transcriptRounds.map((round) => {
        const isCollapsed = collapsedRounds[round.roundNumber] ?? false;
        const roundSpeakers = Array.from(
          new Map(round.messages.map((m) => [m.agent_id, m.display_name])).entries(),
        ).map(([agentId, displayName]) => ({ agentId, displayName }));
        const roundSpeakerNames = roundSpeakers.map((s) => s.displayName);
        const roundEntropyValues = round.messages
          .filter((m) => typeof m.telemetry?.entropy === "number")
          .map((m) => m.telemetry!.entropy as number);
        const roundAvgEntropy = roundEntropyValues.length > 0
          ? Math.round((roundEntropyValues.reduce((s, v) => s + v, 0) / roundEntropyValues.length) * 100)
          : null;
        const roundTopScoreValues = round.messages
          .filter((m) => typeof m.telemetry?.vector?.top_score === "number")
          .map((m) => m.telemetry!.vector!.top_score as number);
        const roundAvgRagScore = roundTopScoreValues.length > 0
          ? (roundTopScoreValues.reduce((s, v) => s + v, 0) / roundTopScoreValues.length).toFixed(2)
          : null;
        const roundSources = Array.from(
          new Set(
            round.messages.flatMap((m) => m.telemetry?.vector?.sources ?? []),
          ),
        ).filter(Boolean);

        return (
          <section key={`round-${round.roundNumber}`} className={styles.roundSection} aria-label={`Round ${round.roundNumber}`}>
            <div className={styles.roundHeader}>
              <div className={styles.roundHeadingBlock}>
                <div>
                  <p className={styles.roundKicker}>ROUND</p>
                  <h3 className={styles.roundTitle}>{String(round.roundNumber).padStart(2, "0")}</h3>
                </div>
                {isCollapsed && roundSpeakers.length > 0 && (
                  <>
                    <div className={styles.roundAvatarRow}>
                      {roundSpeakers.map((speaker) => (
                        <img
                          key={speaker.agentId}
                          className={styles.roundAvatar}
                          src={avatarUrlForAgent(speaker.agentId)}
                          alt={speaker.displayName}
                          title={speaker.displayName}
                        />
                      ))}
                    </div>
                    <p className={styles.roundSpeakerSummary}>
                      {roundSpeakerNames.join(" · ")}
                    </p>
                  </>
                )}
              </div>

              <div className={styles.roundMetaBlock}>
                <div className={styles.roundMetaTopRow}>
                  <span className={styles.roundMeta}>
                    {round.messages.length} {round.messages.length === 1 ? "turn" : "turns"}
                  </span>
                  {roundAvgEntropy !== null && (
                    <span className={styles.roundTelemetryBadge}>{roundAvgEntropy}% div</span>
                  )}
                  {roundAvgRagScore !== null && (
                    <span className={styles.roundTelemetryBadge}>{roundAvgRagScore} sim</span>
                  )}
                </div>
              </div>
            </div>

            {roundSources.length > 0 && (
              <div className={styles.roundSourceRow}>
                {roundSources.map((source) => (
                  <span key={source} className={styles.roundSourceChip} title={source}>
                    {source}
                  </span>
                ))}
              </div>
            )}

            <div className={styles.roundControls}>
              <button type="button" className={styles.roundToggleButton} onClick={() => toggleRound(round.roundNumber)}>
                <span className={styles.roundToggle} aria-hidden="true">{isCollapsed ? "+" : "-"}</span>
                <span>{isCollapsed ? "Expand round" : "Collapse round"}</span>
              </button>
            </div>

            {!isCollapsed ? (
              <div className={styles.roundTimeline}>
                {round.messages.map((message) => {
                  const isExpanded = expandedMessageIds[message.id] ?? false;
                  const sanitizedMessage = sanitizeDebateMessageText(message.message, message.display_name);
                  const shouldTruncate = sanitizedMessage.length > MESSAGE_PREVIEW_LIMIT;
                  const bubbleToneIndex = getStyleIndex(message.agent_id);
                  const thinkingStatus = message.isThinking
                    ? getThinkingStatus(message.id, message.thinkingStatus)
                    : "";
                  const previewMessage = shouldTruncate
                    ? sanitizedMessage.slice(0, MESSAGE_PREVIEW_LIMIT).trimEnd()
                    : sanitizedMessage;
                  const visibleMessage = shouldTruncate && !isExpanded
                    ? previewMessage
                    : sanitizedMessage;
                  const showRetrySkull = message.isThinking && !visibleMessage && isThrottledThinkingStatus(message.thinkingStatus);

                  return (
                    <div key={message.id} className={styles.turnRow}>
                      <div className={styles.turnRail}>
                        <div className={styles.turnInfoRow}>
                          <img
                            className={styles.avatar}
                            src={avatarUrlForAgent(message.agent_id)}
                            alt={`${message.display_name} portrait`}
                          />
                        </div>
                        <div className={styles.turnConnector} aria-hidden="true" />
                      </div>
                      <article
                        data-message-id={message.id}
                        data-turn-number={message.turn_number}
                        data-thinking={message.isThinking ? "true" : "false"}
                        className={[
                          styles.bubble,
                          styles.bubbleAssistant,
                          bubbleToneClasses[bubbleToneIndex] ?? styles.bubbleTone0,
                          message.isThinking ? styles.bubbleThinking : "",
                          message.failed ? styles.bubbleFailed : "",
                        ].filter(Boolean).join(" ")}
                      >
                        <div className={styles.bubbleHeader}>
                          <div className={styles.bubbleIdentity}>
                            <p className={styles.bubbleName}>{message.display_name}</p>
                          </div>
                        </div>
                        {thinkingStatus ? <p className={styles.bubbleStatus}>{thinkingStatus.toUpperCase()}</p> : null}
                        {visibleMessage ? (
                          <p className={styles.bubbleText}>
                            {visibleMessage}
                            {shouldTruncate ? (
                              <>
                                {!isExpanded ? "... " : " "}
                                <button
                                  type="button"
                                  className={styles.bubbleInlineToggle}
                                  onClick={() => toggleExpandedMessage(message.id)}
                                >
                                  {isExpanded ? "Read less" : "Read more"}
                                </button>
                              </>
                            ) : null}
                          </p>
                        ) : null}
                        {showRetrySkull ? (
                          <div className={styles.bubbleThinkingState} aria-hidden="true">
                            <img className={styles.bubbleThinkingIcon} src="/waiting-skull.svg" alt="" />
                          </div>
                        ) : null}
                      </article>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}