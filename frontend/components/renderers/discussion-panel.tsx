// DiscussionPanel frames the transcript stage and now owns the primary debate
// controls so the main column is the single operator surface.
import type { RefObject } from "react";

import type { DebateMessage, LegendDetails, TranscriptViewState } from "../types";
import { DiscussionTranscript } from "./discussion-transcript";
import styles from "./discussion-panel.module.css";

type DiscussionPanelProps = {
  topic: string;
  hasHydratedTopic: boolean;
  topicEditorRef: RefObject<HTMLTextAreaElement | null>;
  discussionActive: boolean;
  selectedCouncil: LegendDetails[];
  targetEntropy: number;
  controlError: string;
  sessionId: string;
  isWipingSession: boolean;
  isDownloadingTranscript: boolean;
  startButtonLabel: string;
  transcriptState: TranscriptViewState;
  messages: DebateMessage[];
    hasMessages: boolean;
  transcriptRef: RefObject<HTMLDivElement | null>;
  onTopicChange: (value: string) => void;
  onOpenSpeakerModal: () => void;
  onToggleCouncilMember: (agentId: string) => void;
  onTargetEntropyChange: (value: number) => void;
  onStartDebate: () => void;
  onHaltDebate: () => void;
  onWipeDebate: () => void | Promise<void>;
  onDownloadTranscript: () => void | Promise<void>;
  onRenewSession: () => void;
};

const ENTROPY_OPTIONS = [0, 0.375, 0.75, 1.125, 1.5];

function formatEntropyValue(value: number) {
  if (value === 0 || value === 1.5) {
    return value.toFixed(value === 0 ? 0 : 1);
  }

  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

export function DiscussionPanel({
  topic,
  hasHydratedTopic,
  topicEditorRef,
  discussionActive,
  selectedCouncil,
  targetEntropy,
  controlError,
    hasMessages,
  sessionId,
  isWipingSession,
  isDownloadingTranscript,
  startButtonLabel,
  transcriptState,
  messages,
  transcriptRef,
  onTopicChange,
  onOpenSpeakerModal,
  onToggleCouncilMember,
  onTargetEntropyChange,
  onStartDebate,
  onHaltDebate,
  onWipeDebate,
  onDownloadTranscript,
  onRenewSession,
}: DiscussionPanelProps) {
  const selectedEntropyValue = ENTROPY_OPTIONS.reduce((closestValue, option) => {
    const currentDistance = Math.abs(option - targetEntropy);
    const closestDistance = Math.abs(closestValue - targetEntropy);
    return currentDistance < closestDistance ? option : closestValue;
  }, ENTROPY_OPTIONS[0]);
  const hasTranscriptHistory = messages.some((message) => !message.isThinking);
  const showTranscriptControls = discussionActive || hasTranscriptHistory;

  return (
    <section className="chatColumn">
      <div className={`discussionPane ${styles.discussionPane}`.trim()}>
        <header className={styles.header}>
          <div className={styles.titleRow}>
            <h2 className={`sectionTitle columnTitle ${styles.title}`.trim()}>DEBATE TOPIC</h2>
          </div>
        </header>

        <div className={styles.controlsDeck}>
          <section className={styles.sectionGroup}>
            <div className={styles.topicSection}>
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
            <div className={styles.commandCluster}>
              <div className={styles.commandGridCompact}>
                <button className={`button ${styles.commandButton}`.trim()} type="button" onClick={onStartDebate} disabled={discussionActive}>
                  {startButtonLabel}
                </button>
                <button className={`buttonGhost ${styles.commandButton}`.trim()} type="button" onClick={onHaltDebate} disabled={!discussionActive}>
                  ❚❚ Halt
                </button>
              </div>

              {!showTranscriptControls && controlError ? <p className="statusNote">{controlError}</p> : null}
            </div>
          </section>

          <section className={styles.sectionGroup}>
            <div className={`${styles.sectionHeading} ${styles.councilHeading}`.trim()}>
              <span className={styles.councilHeadingLabel}>COUNCIL</span>
              <span className={styles.councilCountInline}>{selectedCouncil.length} Selected</span>
            </div>
            <div className={`draftedCouncil ${styles.councilChips}`.trim()}>
              {selectedCouncil.map((legend) => (
                <button
                  key={legend.agent_id}
                  type="button"
                  className="draftedChip"
                  onClick={() => onToggleCouncilMember(legend.agent_id)}
                  disabled={discussionActive}
                >
                  <span className="draftedChipLabel">{legend.display_name}</span>
                  <span className="draftedChipRemove" aria-hidden="true">x</span>
                </button>
              ))}

              <button className={styles.editCouncilChip} type="button" onClick={onOpenSpeakerModal}>
                Edit Council
              </button>
            </div>
          </section>

          <section className={styles.sectionGroup}>
            <div className={`${styles.sectionHeading} ${styles.entropyHeadingRow}`.trim()}>
              <span>LOGIC ENTROPY</span>
              <details className={styles.tooltipDetails}>
                <summary className={styles.tooltipButton} aria-label="What is logic entropy?">
                  ?
                </summary>
                <div className={styles.tooltipCard} role="note">
                  Adjust between rigid logic and creative unpredictability.
                </div>
              </details>
            </div>
            <div className={styles.entropyPanel}>
              <div className={styles.entropyOptions} role="radiogroup" aria-label="Logic entropy selector">
                {ENTROPY_OPTIONS.map((option) => {
                  const isSelected = option === selectedEntropyValue;

                  return (
                    <button
                      key={option}
                      type="button"
                      role="radio"
                      aria-checked={isSelected}
                      className={`${styles.entropyOption} ${isSelected ? styles.entropyOptionActive : ""}`.trim()}
                      onClick={() => onTargetEntropyChange(option)}
                      disabled={discussionActive}
                    >
                      <span className={styles.entropyOptionValue}>{formatEntropyValue(option)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </section>
        </div>

        <div className={styles.transcriptShell}>
          <div className={styles.transcriptHeading}>
            <div className={`${styles.sectionHeading} ${styles.transcriptHeadingRow}`.trim()}>
              <span>LIVE TRANSCRIPT</span>
              <span className={styles.status}>[{transcriptState.statusLabel.toUpperCase()}]</span>
            </div>
          </div>
          <DiscussionTranscript emptyStateMessage={transcriptState.emptyMessage} messages={messages} transcriptRef={transcriptRef} />
          {showTranscriptControls ? (
            <div className={styles.transcriptControlsBlock}>
              <div className={styles.transcriptControls}>
                <div className={styles.commandGrid}>
                  <button className={`button ${styles.commandButton}`.trim()} type="button" onClick={onStartDebate} disabled={discussionActive}>
                    {startButtonLabel}
                  </button>
                  <button className={`buttonGhost ${styles.commandButton}`.trim()} type="button" onClick={onHaltDebate} disabled={!discussionActive}>
                    ❚❚ Halt
                  </button>
                  <button className={`buttonDanger ${styles.commandButton}`.trim()} type="button" onClick={() => void onWipeDebate()} disabled={isWipingSession}>
                    {isWipingSession ? "Wiping..." : "🧹 Wipe"}
                  </button>
                  <button
                    className={`buttonGhost ${styles.commandButton}`.trim()}
                    type="button"
                    onClick={() => void onDownloadTranscript()}
                    disabled={isDownloadingTranscript}
                  >
                    {isDownloadingTranscript ? "Preparing..." : "📃 Export"}
                  </button>
                </div>
              </div>
              <div className={styles.commandFooter}>
                <div className={styles.commandMeta}>
                  <span className={styles.commandMetaLabel}>Active Session</span>
                  <span className={styles.commandMetaValue}>{sessionId || "Pending"}</span>
                </div>
                <div className={styles.commandMetaActions}>
                  <button className={`buttonGhost ${styles.commandButton}`.trim()} type="button" onClick={onRenewSession}>
                    ⟳ Refresh Session
                  </button>
                </div>
              </div>
              {controlError ? <p className="statusNote">{controlError}</p> : null}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}