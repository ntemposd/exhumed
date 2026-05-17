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
  roundStartAgentId?: string;
  roundScrollKey: number;
  transcriptRef: RefObject<HTMLDivElement | null>;
};

export function DiscussionTranscript({ emptyStateMessage, messages, roundStartAgentId, roundScrollKey, transcriptRef }: DiscussionTranscriptProps) {
  const [expandedMessageIds, setExpandedMessageIds] = useState<Record<string, boolean>>({});
  const [retryCountdownTick, setRetryCountdownTick] = useState(0);
  const lastMessageStateRef = useRef<{ agentId: string; turnNumber: number; isThinking: boolean } | null>(null);
  const lastScrolledRoundKeyRef = useRef(0);
  const retryCountdownsRef = useRef<Record<string, { initialSeconds: number; startedAtMs: number; status: string }>>({});

  useEffect(() => {
    if (roundScrollKey < lastScrolledRoundKeyRef.current) {
      lastScrolledRoundKeyRef.current = roundScrollKey;
    }

    if (roundScrollKey === 0) {
      lastScrolledRoundKeyRef.current = 0;
      lastMessageStateRef.current = null;
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

  return (
    <div className={styles.transcript} ref={transcriptRef}>
      {messages.length === 0 ? (
        <div className={styles.emptyState}>
          <p className={styles.emptyStateText}>{emptyStateMessage}</p>
        </div>
      ) : null}
      {messages.map((message) => {
        const isExpanded = expandedMessageIds[message.id] ?? false;
        const sanitizedMessage = sanitizeDebateMessageText(message.message, message.display_name);
        const shouldTruncate = sanitizedMessage.length > MESSAGE_PREVIEW_LIMIT;
        const bubbleToneIndex = getStyleIndex(message.agent_id);
        const thinkingStatus = message.isThinking
          ? getThinkingStatus(message.id, message.thinkingStatus)
          : "";
        const visibleMessage = shouldTruncate && !isExpanded
          ? `${sanitizedMessage.slice(0, MESSAGE_PREVIEW_LIMIT).trimEnd()}...`
          : sanitizedMessage;
        const showRetrySkull = message.isThinking && !visibleMessage && isThrottledThinkingStatus(message.thinkingStatus);

        return (
          <article
            key={message.id}
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
              <img
                className={styles.avatar}
                src={avatarUrlForAgent(message.agent_id)}
                alt={`${message.display_name} portrait`}
              />
              <div className={styles.bubbleIdentity}>
                <p className={styles.bubbleName}>{message.display_name}</p>
                <p className={styles.bubbleMeta}>Turn {message.turn_number}</p>
              </div>
            </div>
            {thinkingStatus ? <p className={styles.bubbleStatus}>{thinkingStatus.toUpperCase()}</p> : null}
            {visibleMessage ? <p className={styles.bubbleText}>{visibleMessage}</p> : null}
            {showRetrySkull ? (
              <div className={styles.bubbleThinkingState} aria-hidden="true">
                <img className={styles.bubbleThinkingIcon} src="/waiting-skull.svg" alt="" />
              </div>
            ) : null}
            {shouldTruncate ? (
              <button
                type="button"
                className={styles.bubbleReadMore}
                onClick={() => toggleExpandedMessage(message.id)}
              >
                {isExpanded ? "Read less" : "Read more"}
              </button>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}