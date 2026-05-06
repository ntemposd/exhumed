// DiscussionTranscript owns transcript-only interaction state such as message
// expansion and animated thinking indicators.
import { useEffect, useRef, useState, type RefObject } from "react";

import type { DebateMessage } from "../types";
import { avatarUrlForAgent, getStyleIndex, sanitizeDebateMessageText } from "../utils";

const MESSAGE_PREVIEW_LIMIT = 140;

type DiscussionTranscriptProps = {
  emptyStateMessage: string;
  messages: DebateMessage[];
  transcriptRef: RefObject<HTMLDivElement | null>;
};

export function DiscussionTranscript({ emptyStateMessage, messages, transcriptRef }: DiscussionTranscriptProps) {
  const [expandedMessageIds, setExpandedMessageIds] = useState<Record<string, boolean>>({});
  const lastAutoScrollRef = useRef<{ messageId: string; bubbleHeight: number } | null>(null);

  useEffect(() => {
    // Keep the newest speech bubble visible, but only react to genuinely new or meaningfully taller bubbles.
    const lastMessage = messages.at(-1);
    const lastBubble = transcriptRef.current?.querySelector("article:last-of-type") as HTMLElement | null;
    if (!lastBubble || !lastMessage) {
      return;
    }

    const animationFrameId = window.requestAnimationFrame(() => {
      const bubbleBounds = lastBubble.getBoundingClientRect();
      const previousAutoScroll = lastAutoScrollRef.current;
      const isNewBubble = previousAutoScroll?.messageId !== lastMessage.id;
      const grewMeaningfully = previousAutoScroll?.messageId === lastMessage.id
        && bubbleBounds.height - previousAutoScroll.bubbleHeight > 72;
      const viewportBottom = window.innerHeight - 88;
      const bubbleOverflow = bubbleBounds.bottom - viewportBottom;
      const shouldKeepThinkingVisible = lastMessage.isThinking && bubbleOverflow > 8;

      if (((isNewBubble || grewMeaningfully) && bubbleOverflow > 0) || shouldKeepThinkingVisible) {
        const scrollBuffer = lastMessage.isThinking ? 36 : 20;
        window.scrollBy({
          top: Math.ceil(Math.max(bubbleOverflow, 0) + scrollBuffer),
          behavior: "smooth",
        });
      }

      lastAutoScrollRef.current = {
        messageId: lastMessage.id,
        bubbleHeight: bubbleBounds.height,
      };
    });

    return () => {
      window.cancelAnimationFrame(animationFrameId);
    };
  }, [messages, transcriptRef]);

  function getThinkingStatus(explicitStatus?: string): string {
    if (explicitStatus) {
      const retryMatch = explicitStatus.match(/retrying in\s+[\d.]+s?/i);

      if (/rate limit|retry|\b429\b|\b5\d{2}\b/i.test(explicitStatus)) {
        return retryMatch ? `Request throttled. ${retryMatch[0]}` : "Request throttled";
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
      [messageId]: !(currentValue[messageId] ?? true),
    }));
  }

  return (
    <div className="transcript" ref={transcriptRef}>
      {!messages.length ? (
        <p className="emptyState">
          {emptyStateMessage}
        </p>
      ) : null}

      {messages.map((message) => {
        const isExpanded = expandedMessageIds[message.id] ?? true;
        const sanitizedMessage = sanitizeDebateMessageText(message.message, message.display_name);
        const shouldTruncate = sanitizedMessage.length > MESSAGE_PREVIEW_LIMIT;
        const bubbleToneIndex = getStyleIndex(message.agent_id);
        const thinkingStatus = message.isThinking
          ? getThinkingStatus(message.thinkingStatus)
          : "";
        const visibleMessage = shouldTruncate && !isExpanded
          ? `${sanitizedMessage.slice(0, MESSAGE_PREVIEW_LIMIT).trimEnd()}...`
          : sanitizedMessage;
        const showRetrySkull = message.isThinking && !visibleMessage && isThrottledThinkingStatus(message.thinkingStatus);

        return (
          <article
            key={message.id}
            className={`bubble bubbleAssistant bubbleTone${bubbleToneIndex} ${message.isThinking ? "bubbleThinking" : ""} ${message.failed ? "bubbleFailed" : ""}`.trim()}
          >
            <div className="bubbleHeader">
              <img
                className="avatar"
                src={avatarUrlForAgent(message.agent_id)}
                alt={`${message.display_name} portrait`}
              />
              <div className="bubbleIdentity">
                <p className="bubbleName">{message.display_name}</p>
                <p className="bubbleMeta">
                  Turn {message.turn_number}
                  {thinkingStatus ? ` · ${thinkingStatus.toUpperCase()}` : ""}
                </p>
              </div>
            </div>
            {visibleMessage ? <p className="bubbleText">{visibleMessage}</p> : null}
            {showRetrySkull ? (
              <div className="bubbleThinkingState" aria-hidden="true">
                <img className="bubbleThinkingIcon" src="/waiting-skull.svg" alt="" />
              </div>
            ) : null}
            {shouldTruncate ? (
              <button
                type="button"
                className="bubbleReadMore"
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