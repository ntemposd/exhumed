// DiscussionPanel frames the transcript stage: title, live status, topic input,
// and the transcript renderer itself.
import type { RefObject } from "react";

import type { DebateMessage, TranscriptViewState } from "../types";
import { DiscussionTranscript } from "./discussion-transcript";

type DiscussionPanelProps = {
  topic: string;
  hasHydratedTopic: boolean;
  topicEditorRef: RefObject<HTMLTextAreaElement | null>;
  discussionActive: boolean;
  transcriptState: TranscriptViewState;
  messages: DebateMessage[];
  transcriptRef: RefObject<HTMLDivElement | null>;
  onTopicChange: (value: string) => void;
};

export function DiscussionPanel({
  topic,
  hasHydratedTopic,
  topicEditorRef,
  discussionActive,
  transcriptState,
  messages,
  transcriptRef,
  onTopicChange,
}: DiscussionPanelProps) {
  return (
    <section className="chatColumn">
      <div className="discussionPane">
        <header className="chatHeader">
          <div className="discussionTitleRow">
            <h2 className="sectionTitle columnTitle">DISCUSSION</h2>
            <p className="discussionStatus">[{transcriptState.statusLabel.toUpperCase()}]</p>
          </div>
        </header>

        <div className="topicSection">
          <h3 className="sidebarSectionHeading topicSectionHeading">DEBATE TOPIC</h3>
          {hasHydratedTopic ? (
            <textarea
              ref={topicEditorRef}
              className="topicEditor"
              value={topic}
              rows={1}
              onChange={(event) => onTopicChange(event.target.value)}
              placeholder="Set the frame for the debate"
              disabled={discussionActive}
            />
          ) : (
            <div className="topicEditor topicEditorLoading" aria-live="polite">
              Loading saved topic...
            </div>
          )}
        </div>

        <DiscussionTranscript emptyStateMessage={transcriptState.emptyMessage} messages={messages} transcriptRef={transcriptRef} />
      </div>
    </section>
  );
}