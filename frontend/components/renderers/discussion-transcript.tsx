// DiscussionTranscript owns transcript-only interaction state such as message
// expansion and animated thinking indicators.
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import Image from "next/image";

import type { DebateMessage } from "../types";
import { avatarUrlForAgent, getAgentArchetype, sanitizeDebateMessageText } from "../utils";
import styles from "./discussion-transcript.module.css";


const MESSAGE_PREVIEW_LIMIT = 140;

function injectSourceFootnotes(text: string, sources: string[]): React.ReactNode {
  const eligible = sources.filter((s) => s.length >= 4);
  if (!eligible.length) return text;

  const sorted = [...eligible].sort((a, b) => b.length - a.length);
  const indexMap = new Map(sorted.map((s, i) => [s.toLowerCase(), i + 1]));
  const escaped = sorted.map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);

  if (parts.length === 1) return text;

  return (
    <>
      {parts.map((part, i) => {
        if (i % 2 === 0) return part || null;
        const num = indexMap.get(part.toLowerCase());
        return num ? <span key={i}>{part}<sup className={styles.footnoteMarker}>[{num}]</sup></span> : part;
      })}
    </>
  );
}

type DiscussionTranscriptProps = {
  emptyStateMessage: string;
  messages: DebateMessage[];
  roundSize: number;
  roundStartAgentId?: string;
  roundScrollKey: number;
  fillViewport?: boolean;
  transcriptRef: RefObject<HTMLDivElement | null>;
};

type TranscriptRound = {
  roundNumber: number;
  messages: DebateMessage[];
};

export function DiscussionTranscript({ emptyStateMessage, messages, roundSize, roundStartAgentId, roundScrollKey, fillViewport, transcriptRef }: DiscussionTranscriptProps) {
  const [expandedMessageIds, setExpandedMessageIds] = useState<Record<string, boolean>>({});
  const [collapsedRounds, setCollapsedRounds] = useState<Record<number, boolean>>({});
  const [retryCountdownTick, setRetryCountdownTick] = useState(0);
  const lastAutoCollapsedRoundRef = useRef(0);
  const retryCountdownsRef = useRef<Record<string, { initialSeconds: number; startedAtMs: number; status: string }>>({});
  const normalizedRoundSize = Math.max(roundSize, 1);

  useEffect(() => {
    if (roundScrollKey === 0) {
      lastAutoCollapsedRoundRef.current = 0;
      setCollapsedRounds({});
      setExpandedMessageIds({});
    }
  }, [roundScrollKey]);

  // Scroll so the bottom of the latest bubble sits just above the sticky controls bar.
  // CONTROLS_CLEARANCE matches the sticky .transcriptControlsBlock height (padding + button + gap).
  const CONTROLS_CLEARANCE = 96;

  function scrollToLatestBubble(targetBubble: HTMLElement) {
    const bubbleBottomInViewport = targetBubble.getBoundingClientRect().bottom;
    const availableHeight = window.innerHeight - CONTROLS_CLEARANCE;

    // Already fully visible above the controls — nothing to do.
    if (bubbleBottomInViewport <= availableHeight) {
      return;
    }

    const targetScrollTop = window.scrollY + bubbleBottomInViewport - availableHeight;
    const startTop = window.scrollY;
    const travel = targetScrollTop - startTop;

    if (Math.abs(travel) < 2) {
      window.scrollTo({ top: targetScrollTop, behavior: "auto" });
      return;
    }

    const durationMs = 380;
    const startTime = window.performance.now();

    const step = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / durationMs, 1);
      const easedProgress = 1 - Math.pow(1 - progress, 3);

      window.scrollTo({ top: startTop + travel * easedProgress, behavior: "auto" });

      if (progress < 1) {
        window.requestAnimationFrame(step);
      }
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

  // Scroll to each new bubble as it arrives so the latest content is always
  // visible just above the sticky controls bar — chat-style bottom-anchored scroll.
  const lastMessageId = messages.at(-1)?.id;
  useEffect(() => {
    if (!lastMessageId) {
      return;
    }

    const animationFrameId = window.requestAnimationFrame(() => {
      const container = transcriptRef.current;
      if (!container) {
        return;
      }

      // Full-screen convo mode scrolls the transcript internally. Keep the
      // newest content pinned just above the command bar, but only when the
      // reader is already near the bottom so scrolling up to review is stable.
      if (fillViewport) {
        const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
        if (distanceFromBottom < 160) {
          container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
        }
        return;
      }

      const targetBubble = container.querySelector(
        `article[data-message-id="${lastMessageId}"]`,
      ) as HTMLElement | null;

      if (targetBubble) {
        scrollToLatestBubble(targetBubble);
      }
    });

    return () => {
      window.cancelAnimationFrame(animationFrameId);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastMessageId, transcriptRef, fillViewport]);

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

  const transcriptRounds = useMemo(() => messages.reduce<TranscriptRound[]>((rounds, message) => {
    const roundNumber = Math.max(1, message.round_number ?? Math.ceil(message.turn_number / normalizedRoundSize));
    const existingRound = rounds.at(-1);

    if (!existingRound || existingRound.roundNumber !== roundNumber) {
      rounds.push({ roundNumber, messages: [message] });
      return rounds;
    }

    existingRound.messages.push(message);
    return rounds;
  }, []), [messages, normalizedRoundSize]);

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
    const container = transcriptRef.current;
    const useContainerScroll = fillViewport && container;
    const savedScroll = useContainerScroll ? container.scrollTop : window.scrollY;
    setCollapsedRounds((currentValue) => ({
      ...currentValue,
      [roundNumber]: !(currentValue[roundNumber] ?? false),
    }));
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if (useContainerScroll) {
          container.scrollTop = savedScroll;
        } else {
          window.scrollTo({ top: savedScroll, behavior: "auto" });
        }
      });
    });
  }

  return (
    <div className={`${styles.transcript} ${fillViewport ? styles.transcriptScroll : ""}`.trim()} ref={transcriptRef}>
      <div className={`${styles.transcriptInner} ${fillViewport ? styles.transcriptInnerFill : ""}`.trim()}>
      {messages.length === 0 ? (
        <div className={styles.emptyState}>
          <p className={styles.emptyStateText}>{emptyStateMessage}</p>
        </div>
      ) : null}
      {transcriptRounds.map((round) => {
        const isCollapsed = collapsedRounds[round.roundNumber] ?? false;
        const roundEntropyValues = round.messages
          .filter((m) => typeof m.telemetry?.entropy === "number")
          .map((m) => m.telemetry!.entropy as number);
        const roundAvgEntropy = roundEntropyValues.length > 0
          ? Math.round((roundEntropyValues.reduce((s, v) => s + v, 0) / roundEntropyValues.length) * 100)
          : null;
        const roundTopScoreValues = round.messages
          .filter((m) => typeof m.telemetry?.vector?.top_score === "number")
          .map((m) => m.telemetry!.vector!.top_score as number);
        const roundSimRange = roundTopScoreValues.length > 0
          ? {
              min: Math.min(...roundTopScoreValues).toFixed(2),
              max: Math.max(...roundTopScoreValues).toFixed(2),
            }
          : null;
        const roundTotalTokens = round.messages.some((m) =>
          typeof m.execution_metrics?.prompt_tokens === "number" || typeof m.execution_metrics?.completion_tokens === "number"
        )
          ? round.messages.reduce((sum, m) => sum + (m.execution_metrics?.prompt_tokens ?? 0) + (m.execution_metrics?.completion_tokens ?? 0), 0)
          : null;

        return (
          <section key={`round-${round.roundNumber}`} className={styles.roundSection} aria-label={`Round ${round.roundNumber}`}>
            <div
              className={styles.roundHeader}
              role="button"
              tabIndex={0}
              aria-expanded={!isCollapsed}
              aria-label={`Round ${round.roundNumber} — ${isCollapsed ? "expand" : "collapse"}`}
              onClick={() => toggleRound(round.roundNumber)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleRound(round.roundNumber); } }}
            >
              <div className={styles.roundHeaderMain}>
                <h3 className={styles.roundTitle}>ROUND {String(round.roundNumber).padStart(2, "0")}</h3>

                <div className={styles.roundMetaRow}>
                  <span className={styles.roundMeta}>
                    {round.messages.length} {round.messages.length === 1 ? "speaker" : "speakers"}
                  </span>
                </div>
              </div>

              <span className={styles.roundToggle} aria-hidden="true">{isCollapsed ? "+" : "−"}</span>
            </div>

            {!isCollapsed ? (
              <>
                {(roundAvgEntropy !== null || roundSimRange !== null || roundTotalTokens !== null) && (
                  <div className={styles.roundStats}>
                    {roundAvgEntropy !== null && (
                      <div className={styles.roundStatItem}>
                        <span className={styles.roundStatLabel}>Diversity</span>
                        <span className={styles.roundStatValue}>{roundAvgEntropy}%</span>
                      </div>
                    )}
                    {roundSimRange !== null && (
                      <div className={styles.roundStatItem}>
                        <span className={styles.roundStatLabel}>Similarity Range</span>
                        <span className={styles.roundStatValue}>
                          {roundSimRange.min === roundSimRange.max
                            ? roundSimRange.max
                            : `${roundSimRange.min} – ${roundSimRange.max}`}
                        </span>
                      </div>
                    )}
                    {roundTotalTokens !== null && (
                      <div className={styles.roundStatItem}>
                        <span className={styles.roundStatLabel}>Usage</span>
                        <span className={styles.roundStatValue}>{roundTotalTokens.toLocaleString()} tokens</span>
                      </div>
                    )}
                  </div>
                )}
                <div className={styles.roundTimeline}>
                {round.messages.map((message) => {
                  const isExpanded = expandedMessageIds[message.id] ?? false;
                  const sanitizedMessage = sanitizeDebateMessageText(message.message, message.display_name);
                  const shouldTruncate = sanitizedMessage.length > MESSAGE_PREVIEW_LIMIT;
                  const agentArchetype = getAgentArchetype(message.agent_id);
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
                  const messageSources = message.telemetry?.vector?.sources ?? [];
                  const showSources = messageSources.length > 0 && (isExpanded || !shouldTruncate);
                  const hasVectorMeta = typeof message.telemetry?.vector?.match_count === "number" ||
                    typeof message.telemetry?.vector?.context_chars === "number" ||
                    typeof message.telemetry?.vector?.top_score === "number";
                  const hasLlmMeta = typeof message.execution_metrics?.prompt_tokens === "number" ||
                    typeof message.execution_metrics?.completion_tokens === "number" ||
                    typeof message.telemetry?.latency_ms === "number";
                  const showBubbleMeta = !message.isThinking && (isExpanded || !shouldTruncate) && (
                    typeof message.telemetry?.entropy === "number" || hasVectorMeta || hasLlmMeta
                  );

                  return (
                    <div key={message.id} className={styles.turnRow}>
                      <article
                        data-message-id={message.id}
                        data-turn-number={message.turn_number}
                        data-thinking={message.isThinking ? "true" : "false"}
                        data-archetype={agentArchetype}
                        className={[
                          styles.bubble,
                          styles.bubbleAssistant,
                          message.isThinking ? styles.bubbleThinking : "",
                          message.failed ? styles.bubbleFailed : "",
                        ].filter(Boolean).join(" ")}
                      >
                        <div className={styles.bubbleHeader}>
                          <div className={styles.bubbleIdentity}>
                            <Image
                              className={styles.bubbleAvatar}
                              src={avatarUrlForAgent(message.agent_id)}
                              alt=""
                              width={26}
                              height={26}
                            />
                            <p className={styles.bubbleName}>{message.display_name}</p>
                          </div>
                          {message.turn_number ? (
                            <span className={styles.bubbleTurn}>Turn {message.turn_number}</span>
                          ) : null}
                        </div>
                        {thinkingStatus ? <p className={styles.bubbleStatus}>{thinkingStatus}</p> : null}
                        {visibleMessage ? (
                          <p className={styles.bubbleText}>
                            {injectSourceFootnotes(visibleMessage, messageSources)}
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
                        {(showSources || showBubbleMeta) && (
                          <div className={styles.bubbleFooter}>
                            {showSources && (
                              <div className={styles.bubbleSources}>
                                {messageSources.map((source, idx) => (
                                  <span key={source} className={styles.bubbleSourceChip}>
                                    [{idx + 1}] {source}
                                  </span>
                                ))}
                              </div>
                            )}
                            {showBubbleMeta && (
                              <div className={styles.bubbleMeta}>
                                {/* Diversity */}
                                {typeof message.telemetry?.entropy === "number" && (
                                  <span className={styles.bubbleMetaGroup}>
                                    <span className={styles.bubbleMetaGroupLabel}>Diversity</span>
                                    <span className={styles.bubbleMetaItem}>
                                      {Math.round(message.telemetry.entropy * 100)}%
                                    </span>
                                  </span>
                                )}
                                {/* Vector: hits · chars · top */}
                                {hasVectorMeta && (
                                  <span className={styles.bubbleMetaGroup}>
                                    <span className={styles.bubbleMetaGroupLabel}>Vector</span>
                                    {typeof message.telemetry?.vector?.match_count === "number" && (
                                      <span className={styles.bubbleMetaItem}>
                                        {message.telemetry.vector.match_count} hits
                                      </span>
                                    )}
                                    {typeof message.telemetry?.vector?.context_chars === "number" && (
                                      <span className={styles.bubbleMetaItem}>
                                        {message.telemetry.vector.context_chars.toLocaleString()} chars
                                      </span>
                                    )}
                                    {typeof message.telemetry?.vector?.top_score === "number" && (
                                      <span className={styles.bubbleMetaItem}>
                                        {message.telemetry.vector.top_score.toFixed(2)} top
                                      </span>
                                    )}
                                  </span>
                                )}
                                {/* LLM Usage: prompt · completion · latency */}
                                {hasLlmMeta && (
                                  <span className={styles.bubbleMetaGroup}>
                                    <span className={styles.bubbleMetaGroupLabel}>LLM Usage</span>
                                    {typeof message.execution_metrics?.prompt_tokens === "number" && (
                                      <span className={styles.bubbleMetaItem}>
                                        {message.execution_metrics.prompt_tokens.toLocaleString()}q
                                      </span>
                                    )}
                                    {typeof message.execution_metrics?.completion_tokens === "number" && (
                                      <span className={styles.bubbleMetaItem}>
                                        {message.execution_metrics.completion_tokens.toLocaleString()}a
                                      </span>
                                    )}
                                    {typeof message.telemetry?.latency_ms === "number" && (
                                      <span className={styles.bubbleMetaItem}>
                                        {(message.telemetry.latency_ms / 1000).toFixed(1)}s
                                      </span>
                                    )}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        )}
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
              </>
            ) : null}

          </section>
        );
      })}
      </div>
    </div>
  );
}
