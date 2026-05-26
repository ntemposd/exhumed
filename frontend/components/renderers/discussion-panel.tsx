// DiscussionPanel frames the transcript stage and now owns the primary debate
// controls so the main column is the single operator surface.
import { type RefObject } from "react";

import type { DebateMessage, LegendDetails, TranscriptViewState } from "../types";
import { avatarUrlForAgent, getStyleIndex } from "../utils";
import { DiscussionTranscript } from "./discussion-transcript";
import styles from "./discussion-panel.module.css";

type DiscussionPanelProps = {
  topic: string;
  hasHydratedTopic: boolean;
  topicEditorRef: RefObject<HTMLTextAreaElement | null>;
  discussionActive: boolean;
  selectedCouncil: LegendDetails[];
  legendEntries: LegendDetails[];
  isCouncilEditing: boolean;
  targetEntropy: number;
  controlError: string;
  sessionId: string;
  isWipingSession: boolean;
  isDownloadingTranscript: boolean;
  startButtonLabel: string;
  transcriptState: TranscriptViewState;
  messages: DebateMessage[];
  hasMessages: boolean;
  roundStartAgentId?: string;
  roundScrollKey: number;
  transcriptRef: RefObject<HTMLDivElement | null>;
  onTopicChange: (value: string) => void;
  onToggleCouncilEdit: () => void;
  onToggleCouncilMember: (agentId: string) => void;
  onTargetEntropyChange: (value: number) => void;
  onStartDebate: () => void;
  onHaltDebate: () => void;
  onWipeDebate: () => void | Promise<void>;
  onDownloadTranscript: () => void | Promise<void>;
};

const ENTROPY_PROFILES = [
  { label: "Historical Overview", value: 0 },
  { label: "Grounded Discussion", value: 0.375 },
  { label: "Balanced Debate", value: 0.75 },
  { label: "Philosophical Drift", value: 1.125 },
  { label: "Creative Synthesis", value: 1.5 },
] as const;

export function DiscussionPanel({
  topic,
  hasHydratedTopic,
  topicEditorRef,
  discussionActive,
  selectedCouncil,
  legendEntries,
  isCouncilEditing,
  targetEntropy,
  controlError,
  hasMessages,
  roundStartAgentId,
  roundScrollKey,
  isWipingSession,
  isDownloadingTranscript,
  startButtonLabel,
  transcriptState,
  messages,
  transcriptRef,
  onTopicChange,
  onToggleCouncilEdit,
  onToggleCouncilMember,
  onTargetEntropyChange,
  onStartDebate,
  onHaltDebate,
  onWipeDebate,
  onDownloadTranscript,
}: DiscussionPanelProps) {
  const selectedEntropyValue = ENTROPY_PROFILES.reduce((closest, profile) => {
    return Math.abs(profile.value - targetEntropy) < Math.abs(closest.value - targetEntropy) ? profile : closest;
  }, ENTROPY_PROFILES[0]);
  const hasTranscriptHistory = messages.some((message) => !message.isThinking);
  const showTranscriptControls = discussionActive || hasTranscriptHistory;
  const selectedAgentIds = new Set(selectedCouncil.map((legend) => legend.agent_id));
  const availableCouncil = legendEntries.filter((legend) => !selectedAgentIds.has(legend.agent_id));

  return (
    <section className="chatColumn">
      <div className={`discussionPane ${styles.discussionPane}`.trim()}>
        <div className={styles.controlsDeck}>
          <section className={styles.sectionGroup}>
            <div className={styles.topicSectionLayout}>
              <div className={styles.topicSection}>
                <div className="topicEditorWrap">
                  {hasHydratedTopic ? (
                    <textarea
                      ref={topicEditorRef}
                      className="topicEditorField"
                      value={topic}
                      rows={1}
                      onChange={(event) => onTopicChange(event.target.value)}
                      onInput={(event) => {
                        const el = event.currentTarget;
                        el.style.height = "auto";
                        el.style.height = `${el.scrollHeight}px`;
                      }}
                      placeholder="The future of AI in society"
                      disabled={discussionActive}
                    />
                  ) : (
                    <span className="topicEditorLoading" aria-live="polite">
                      Loading saved topic...
                    </span>
                  )}
                </div>
                <div className={styles.entropyOptions} role="radiogroup" aria-label="Logic entropy selector">
                  {ENTROPY_PROFILES.map((profile) => {
                    const isSelected = profile.value === selectedEntropyValue.value;

                    return (
                      <button
                        key={profile.value}
                        type="button"
                        role="radio"
                        aria-checked={isSelected}
                        className={`${styles.entropyOption} ${isSelected ? styles.entropyOptionActive : ""}`.trim()}
                        onClick={() => onTargetEntropyChange(profile.value)}
                        disabled={discussionActive}
                      >
                        <span className={styles.entropyOptionValue}>{profile.label}</span>
                      </button>
                    );
                  })}
                </div>
                {!showTranscriptControls && (
                  <button className={`button ${styles.commandButton} ${styles.startConvoButton}`.trim()} type="button" onClick={onStartDebate}>
                    {startButtonLabel}
                  </button>
                )}
              </div>
            </div>
            {!showTranscriptControls && controlError ? <p className="statusNote">{controlError}</p> : null}
          </section>

          <section className={`${styles.sectionGroup} ${styles.dividedSection}`.trim()}>
            <span className={styles.sectionLabel}>Participants</span>
            <div className={`draftedCouncil ${styles.councilChips}`.trim()}>
              {selectedCouncil.map((legend) => (
                <div
                  key={legend.agent_id}
                  className="draftedChip"
                  data-tone={getStyleIndex(legend.agent_id)}
                  data-disabled={discussionActive ? "true" : "false"}
                >
                  <div className="draftedChipMain" title={legend.display_name}>
                    <img
                      className="draftedChipAvatar"
                      src={avatarUrlForAgent(legend.agent_id)}
                      alt=""
                    />
                    <span className="draftedChipText">
                      <span className="draftedChipLabel">{legend.display_name}</span>
                      <span className="draftedChipArchetype">{legend.archetype}</span>
                    </span>
                  </div>
                  {isCouncilEditing ? (
                    <button
                      type="button"
                      className="draftedChipActionButton draftedChipActionRemove"
                      onClick={() => onToggleCouncilMember(legend.agent_id)}
                      disabled={discussionActive}
                      aria-label={`Remove ${legend.display_name} from council`}
                      title={`Remove ${legend.display_name}`}
                    >
                      <span className="draftedChipActionGlyph" aria-hidden="true">×</span>
                    </button>
                  ) : null}
                </div>
              ))}

              <button
                className={`button ${styles.editCouncilButton}`.trim()}
                type="button"
                onClick={onToggleCouncilEdit}
                aria-pressed={isCouncilEditing}
                disabled={discussionActive}
              >
                {isCouncilEditing ? "Done" : "Edit"}
              </button>

              {isCouncilEditing ? availableCouncil.map((legend) => (
                <div
                  key={legend.agent_id}
                  className="draftedChip draftedChipAvailable"
                  data-tone={getStyleIndex(legend.agent_id)}
                  data-disabled={discussionActive ? "true" : "false"}
                >
                  <div className="draftedChipMain" title={legend.display_name}>
                    <img
                      className="draftedChipAvatar"
                      src={avatarUrlForAgent(legend.agent_id)}
                      alt=""
                    />
                    <span className="draftedChipText">
                      <span className="draftedChipLabel">{legend.display_name}</span>
                      <span className="draftedChipArchetype">{legend.archetype}</span>
                    </span>
                  </div>
                  <button
                    type="button"
                    className="draftedChipActionButton draftedChipActionAdd"
                    onClick={() => onToggleCouncilMember(legend.agent_id)}
                    disabled={discussionActive}
                    aria-label={`Add ${legend.display_name} to council`}
                    title={`Add ${legend.display_name}`}
                  >
                    <span className="draftedChipActionGlyph" aria-hidden="true">✓</span>
                  </button>
                </div>
              )) : null}
            </div>
          </section>
        </div>

        <div className={`${styles.transcriptShell} ${styles.dividedSection}`.trim()}>
          <div className={styles.transcriptHeading}>
            <div className={styles.transcriptHeadingRow}>
              <span>Live Transcript</span>
              <span className={styles.status}>[{transcriptState.statusLabel.toUpperCase()}]</span>
            </div>
          </div>
          <DiscussionTranscript
            emptyStateMessage={transcriptState.emptyMessage}
            messages={messages}
            roundSize={Math.max(selectedCouncil.length, 1)}
            roundStartAgentId={roundStartAgentId}
            roundScrollKey={roundScrollKey}
            transcriptRef={transcriptRef}
          />
          {showTranscriptControls ? (
            <div className={styles.transcriptControlsBlock}>
              <div className={styles.transcriptControls}>
                <div className={styles.commandGrid}>
                  <button
                    className={`button ${styles.commandButton}`.trim()}
                    type="button"
                    onClick={discussionActive ? onHaltDebate : onStartDebate}
                  >
                    {discussionActive ? "Pause" : startButtonLabel}
                  </button>
                  <button className={`buttonDanger ${styles.commandButton}`.trim()} type="button" onClick={() => void onWipeDebate()} disabled={isWipingSession}>
                    {isWipingSession ? "Wiping..." : "Wipe"}
                  </button>
                  <button
                    className={`buttonGhost ${styles.commandButton}`.trim()}
                    type="button"
                    onClick={() => void onDownloadTranscript()}
                    disabled={isDownloadingTranscript}
                  >
                    {isDownloadingTranscript ? "Preparing..." : "Export"}
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
