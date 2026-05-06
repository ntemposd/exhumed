// SpeakerSelectorModal is the curated drafting surface for assembling the
// active debate council from the registered legend catalog.
import type { Agent } from "@/lib/types";

import { LegendCard } from "./legend-card";
import type { AsyncViewState, LegendDetails } from "../types";

type SpeakerSelectorModalProps = {
  isOpen: boolean;
  discussionActive: boolean;
  agents: Agent[];
  legendEntries: LegendDetails[];
  selectedAgents: string[];
  catalogState: AsyncViewState;
  onClose: () => void;
  onToggleCouncilMember: (agentId: string) => void;
};

export function SpeakerSelectorModal({
  isOpen,
  discussionActive,
  agents,
  legendEntries,
  selectedAgents,
  catalogState,
  onClose,
  onToggleCouncilMember,
}: SpeakerSelectorModalProps) {
  return (
    <div className={`speakerModalRoot ${isOpen ? "speakerModalOpen" : ""}`.trim()} aria-hidden={!isOpen}>
      <button type="button" className="speakerModalScrim" aria-label="Close speaker selector" onClick={onClose} />
      <section className="speakerModalPanel" role="dialog" aria-modal="true" aria-labelledby="speaker-modal-title">
        <div className="speakerModalHeader">
          <div>
            <h2 id="speaker-modal-title" className="sectionTitle">Select Speaker</h2>
            <p className="helper">Draft the voices that enter the chamber.</p>
          </div>
          <button type="button" className="sidebarToggle speakerModalClose" onClick={onClose} aria-label="Close speaker selector">
            <span className="sidebarToggleGlyph" aria-hidden="true">×</span>
          </button>
        </div>

    {catalogState.phase !== "ready" ? <p className="statusNote">{catalogState.summary}</p> : null}
    {catalogState.phase === "error" && catalogState.detail ? <p className="statusNote">{catalogState.detail}</p> : null}

        <div className="speakerModalGrid">
          {legendEntries.map((legend) => {
            const matchingAgent = agents.find((agent) => agent.agent_id === legend.agent_id);
            const isDrafted = selectedAgents.includes(legend.agent_id);

            return (
              <LegendCard
                key={legend.agent_id}
                legend={legend}
                agent={matchingAgent}
                badge={isDrafted ? "Drafted" : "Available"}
                active={isDrafted}
                onClick={() => onToggleCouncilMember(legend.agent_id)}
                disabled={!matchingAgent || discussionActive}
              />
            );
          })}
        </div>

        <div className="speakerModalFooter">
          <p className="statusNote">{selectedAgents.length} legends drafted.</p>
          <button type="button" className="button" onClick={onClose}>Done</button>
        </div>
      </section>
    </div>
  );
}