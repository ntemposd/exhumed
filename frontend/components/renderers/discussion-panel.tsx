// DiscussionPanel frames the transcript stage and now owns the primary debate
// controls so the main column is the single operator surface.
import { type RefObject, useEffect, useRef, useState } from "react";
import Image from "next/image";


import type { AsyncViewState, DebateMessage, LegendDetails, TranscriptViewState } from "../types";
import { avatarUrlForAgent, ENTROPY_PROFILES, getAgentArchetype } from "../utils";
import { DiscussionTranscript } from "./discussion-transcript";
import styles from "./discussion-panel.module.css";

type DiscussionPanelProps = {
  topic: string;
  defaultTopic: string;
  discussionActive: boolean;
  selectedCouncil: LegendDetails[];
  legendEntries: LegendDetails[];
  legendCatalogState: AsyncViewState;
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
  onToggleCouncilMember: (agentId: string) => void;
  onTargetEntropyChange: (value: number) => void;
  onStartDebate: () => void;
  onHaltDebate: () => void;
  onWipeDebate: () => void | Promise<void>;
  onDownloadTranscript: () => void | Promise<void>;
};

export function DiscussionPanel({
  topic,
  defaultTopic,
  discussionActive,
  selectedCouncil,
  legendEntries,
  legendCatalogState,
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
  onToggleCouncilMember,
  onTargetEntropyChange,
  onStartDebate,
  onHaltDebate,
  onWipeDebate,
  onDownloadTranscript,
}: DiscussionPanelProps) {
  const [isTypeEditing, setIsTypeEditing] = useState(false);
  const [isRosterOpen, setIsRosterOpen] = useState(false);
  const typeSelectRef = useRef<HTMLDivElement | null>(null);
  const rosterRef = useRef<HTMLDivElement | null>(null);
  const topicFieldRef = useRef<HTMLTextAreaElement | null>(null);
  const transcriptSectionRef = useRef<HTMLElement | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const selectedEntropyValue = ENTROPY_PROFILES.reduce((closest, profile) => {
    return Math.abs(profile.value - targetEntropy) < Math.abs(closest.value - targetEntropy) ? profile : closest;
  }, ENTROPY_PROFILES[0]);

  useEffect(() => {
    if (!isTypeEditing) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      if (typeSelectRef.current && !typeSelectRef.current.contains(event.target as Node)) {
        setIsTypeEditing(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsTypeEditing(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isTypeEditing]);
  const hasTranscriptHistory = messages.some((message) => !message.isThinking);
  const showTranscriptControls = discussionActive || hasTranscriptHistory;
  const selectedAgentIds = new Set(selectedCouncil.map((legend) => legend.agent_id));
  const unselectedLegends = legendEntries.filter((legend) => !selectedAgentIds.has(legend.agent_id));
  const selectableUnselected = unselectedLegends.filter((legend) => legend.selectable);

  useEffect(() => {
    if (!isRosterOpen) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      if (rosterRef.current && !rosterRef.current.contains(event.target as Node)) {
        setIsRosterOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsRosterOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isRosterOpen]);

  useEffect(() => {
    if (unselectedLegends.length === 0 || discussionActive) {
      setIsRosterOpen(false);
    }
  }, [unselectedLegends.length, discussionActive]);

  // When a dropdown opens on mobile, scroll the page so the popover is fully
  // visible — a long topic can push the council/style sections near the fold.
  useEffect(() => {
    if (!isRosterOpen) return;
    const raf = requestAnimationFrame(() => {
      const popover = rosterRef.current?.querySelector<HTMLElement>('[role="listbox"]');
      if (!popover) return;
      const rect = popover.getBoundingClientRect();
      if (rect.bottom > window.innerHeight - 8) {
        window.scrollBy({ top: rect.bottom - window.innerHeight + 8, behavior: "smooth" });
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [isRosterOpen]);

  useEffect(() => {
    if (!isTypeEditing) return;
    const raf = requestAnimationFrame(() => {
      const list = typeSelectRef.current?.querySelector<HTMLElement>('[role="listbox"]');
      if (!list) return;
      const rect = list.getBoundingClientRect();
      if (rect.bottom > window.innerHeight - 8) {
        window.scrollBy({ top: rect.bottom - window.innerHeight + 8, behavior: "smooth" });
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [isTypeEditing]);

  // In full-screen convo mode the transcript section is sized to fill from its
  // top down to the bottom of the viewport, so the command bar lands exactly at
  // the bottom of the screen and the rounds scroll internally above it.
  useEffect(() => {
    if (!showTranscriptControls) {
      return;
    }
    const section = transcriptSectionRef.current;
    if (!section) {
      return;
    }
    const applyHeight = () => {
      const rect = section.getBoundingClientRect();
      section.style.height = `${Math.max(window.innerHeight - rect.top, 0)}px`;
    };
    const raf = window.requestAnimationFrame(() => {
      // Reset to the top so the section's measured offset is its natural one,
      // then fit it to the viewport and pin the transcript to its newest entry.
      window.scrollTo({ top: 0, behavior: "auto" });
      applyHeight();
      const scrollContainer = chatScrollRef.current;
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    });
    window.addEventListener("resize", applyHeight);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", applyHeight);
      section.style.height = "";
    };
  }, [showTranscriptControls, transcriptRef]);

  const councilEditor = (
    <div className={`draftedCouncil ${styles.councilChips}`.trim()}>
      {selectedCouncil.map((legend) => (
        <div
          key={legend.agent_id}
          className="draftedChip"
          data-archetype={getAgentArchetype(legend.agent_id)}
          data-disabled={discussionActive ? "true" : "false"}
        >
          <div className="draftedChipMain" title={legend.display_name}>
            <Image
              className="draftedChipAvatar"
              src={avatarUrlForAgent(legend.agent_id)}
              alt=""
              width={32}
              height={32}
            />
            <span className="draftedChipText">
              <span className="draftedChipLabel">{legend.display_name}</span>
              <span className="draftedChipArchetype">{legend.archetype}</span>
            </span>
          </div>
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
        </div>
      ))}

      {unselectedLegends.length > 0 ? (
        <div className={styles.rosterControl} ref={rosterRef}>
          <button
            type="button"
            className={styles.rosterAddTile}
            onClick={() => setIsRosterOpen((value) => !value)}
            aria-haspopup="listbox"
            aria-expanded={isRosterOpen}
            disabled={discussionActive}
            aria-label={isRosterOpen ? "Close speaker picker" : "Add a speaker"}
            title={
              selectableUnselected.length === 0
                ? "All available speakers are drafted"
                : isRosterOpen
                  ? "Close speaker picker"
                  : "Add a speaker"
            }
          >
            <span className={styles.rosterAddGlyph} aria-hidden="true">{isRosterOpen ? "↵" : "+"}</span>
            <span className={styles.rosterAddText}>{isRosterOpen ? "Done" : "Add Speaker"}</span>
          </button>

          {isRosterOpen ? (
            <div className={styles.rosterPopover} role="listbox" aria-label="Available speakers">
              {unselectedLegends.map((legend) => (
                <button
                  key={legend.agent_id}
                  type="button"
                  role="option"
                  aria-selected={false}
                  aria-disabled={!legend.selectable}
                  className={styles.rosterOption}
                  data-archetype={getAgentArchetype(legend.agent_id)}
                  data-unavailable={legend.selectable ? "false" : "true"}
                  onClick={() => onToggleCouncilMember(legend.agent_id)}
                  disabled={discussionActive || !legend.selectable}
                  title={legend.selectable ? `Add ${legend.display_name}` : "Corpus not yet available"}
                >
                  <Image
                    className={styles.rosterOptionAvatar}
                    src={avatarUrlForAgent(legend.agent_id)}
                    alt=""
                    width={28}
                    height={28}
                  />
                  <span className={styles.rosterOptionText}>
                    <span className={styles.rosterOptionName}>{legend.display_name}</span>
                    <span className={styles.rosterOptionArchetype}>
                      {legend.selectable ? legend.archetype : "Corpus pending"}
                    </span>
                  </span>
                  <span className={styles.rosterOptionGlyph} aria-hidden="true">{legend.selectable ? "+" : "—"}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );

  return (
    <section className="convoColumn">
      <div className={styles.convoPane}>
        {!showTranscriptControls && (
          <div className={styles.setupGroup}>
        <section className={styles.themeSection}>
            <h2 className={"sectionHeading"}>Topic</h2>
            <div className={styles.topicSectionLayout}>
              <div className={styles.topicSection}>
                <div className="topicEditorWrap" data-replicated-value={topic || defaultTopic}>
                  <textarea
                    ref={topicFieldRef}
                    className="topicEditorField"
                    value={topic}
                    rows={1}
                    onChange={(event) => onTopicChange(event.target.value)}
                    onFocus={() => { if (topic === defaultTopic) onTopicChange(""); }}
                    onBlur={() => { if (!topic.trim()) onTopicChange(defaultTopic); }}
                    maxLength={255}
                    placeholder={defaultTopic}
                    disabled={discussionActive}
                    data-is-default={topic === defaultTopic ? "true" : "false"}
                  />
                  {!discussionActive && (
                    <button
                      type="button"
                      className={styles.editHint}
                      onClick={() => {
                        const field = topicFieldRef.current;
                        if (!field) {
                          return;
                        }
                        field.focus();
                        const end = field.value.length;
                        field.setSelectionRange(end, end);
                      }}
                    >
                      ✏️ Tap to edit the topic
                    </button>
                  )}
                </div>
              </div>
            </div>
        </section>

        <section className={styles.participantsSection}>
            <h2 className={"sectionHeading"}>Council</h2>
            {legendCatalogState.phase === "loading" || legendCatalogState.phase === "refreshing" ? (
              <p className="statusNote">{legendCatalogState.summary}</p>
            ) : null}
            {legendCatalogState.phase === "error" ? (
              <p className="statusNote" role="alert">
                {legendCatalogState.summary}
                {legendCatalogState.detail ? ` ${legendCatalogState.detail}` : ""}
              </p>
            ) : null}
            {legendCatalogState.phase === "empty" ? (
              <p className="statusNote">{legendCatalogState.summary}</p>
            ) : null}
            {councilEditor}
        </section>

          </div>
        )}

        {!showTranscriptControls && (
          <section className={styles.startSection}>
            <div className={styles.startRow}>
              <button className="buttonPrimary" type="button" onClick={onStartDebate}>
                {startButtonLabel}
              </button>
              <div className={styles.typeSelect} ref={typeSelectRef}>
                <button
                  type="button"
                  className={styles.typeSelectTrigger}
                  onClick={() => setIsTypeEditing((value) => !value)}
                  aria-haspopup="listbox"
                  aria-expanded={isTypeEditing}
                  disabled={discussionActive}
                >
                  <span className={styles.typeSelectLabel}>Style:</span>
                  <span className={styles.typeSelectValue}>{selectedEntropyValue.label}</span>
                  <span className={styles.typeSelectCaret} aria-hidden="true">▾</span>
                </button>

                {isTypeEditing ? (
                  <ul className={styles.typeSelectList} role="listbox" aria-label="Conversation style selector">
                    {ENTROPY_PROFILES.map((profile) => {
                      const isSelected = profile.value === selectedEntropyValue.value;

                      return (
                        <li key={profile.value} role="option" aria-selected={isSelected}>
                          <button
                            type="button"
                            className={`${styles.typeSelectOption} ${isSelected ? styles.typeSelectOptionActive : ""}`.trim()}
                            onClick={() => {
                              onTargetEntropyChange(profile.value);
                              setIsTypeEditing(false);
                            }}
                          >
                            {profile.label}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
            </div>
            {controlError ? <p className="statusNote">{controlError}</p> : null}
          </section>
        )}

        <section
          ref={transcriptSectionRef}
          className={`${styles.transcriptSection} ${showTranscriptControls ? styles.transcriptSectionActive : ""}`.trim()}
        >
          <div className={`${styles.transcriptHeader} ${showTranscriptControls ? styles.chatHeader : ""}`.trim()}>
            {showTranscriptControls ? (
              <>
                <div className={styles.chatTopicBlock}>
                  <span className={styles.chatTopicLabel}>Topic</span>
                  <h2 className={styles.chatTopicTitle} title={topic}>{topic || "Untitled topic"}</h2>
                </div>
                <div className={styles.chatRoster}>{councilEditor}</div>
                <p className={`${styles.transcriptStatusMessage} ${styles.chatStatusMessage}`.trim()}>{transcriptState.statusLabel}</p>
              </>
            ) : (
              <>
                <h2 className={"sectionHeading"}>Transcript</h2>
                <p className={styles.transcriptStatusMessage}>{transcriptState.statusLabel}</p>
              </>
            )}
          </div>
          <DiscussionTranscript
            emptyStateMessage={transcriptState.emptyMessage}
            messages={messages}
            roundSize={Math.max(selectedCouncil.length, 1)}
            roundStartAgentId={roundStartAgentId}
            roundScrollKey={roundScrollKey}
            fillViewport={showTranscriptControls}
            transcriptRef={showTranscriptControls ? chatScrollRef : transcriptRef}
          />
          {showTranscriptControls ? (
            <div className={styles.transcriptControlsBlock}>
              <div className={styles.commandGrid}>
                <button
                  className="buttonPrimary"
                  type="button"
                  onClick={discussionActive ? onHaltDebate : onStartDebate}
                >
                  {discussionActive ? "⏸ Pause" : startButtonLabel}
                </button>
                <button className="buttonGhost" type="button" onClick={() => void onWipeDebate()} disabled={isWipingSession || discussionActive}>
                  {isWipingSession ? "Wiping..." : "🧹 Wipe"}
                </button>
              </div>
              {controlError ? <p className="statusNote">{controlError}</p> : null}
            </div>
          ) : null}
        </section>
      </div>
    </section>
  );
}
