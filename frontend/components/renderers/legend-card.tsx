// LegendCard renders one selectable council member in the speaker modal.
import type { Agent } from "@/lib/types";

import type { LegendDetails } from "../types";
import { avatarUrlForAgent } from "../utils";

type LegendCardProps = {
  legend: LegendDetails;
  agent?: Agent;
  badge: string;
  active?: boolean;
  onClick?: () => void;
  disabled?: boolean;
};

export function LegendCard({ legend, agent, badge, active = false, onClick, disabled = false }: LegendCardProps) {
  const isUnavailable = !agent;
  const className = `agentCard ${active ? "agentCardActive" : ""} ${isUnavailable ? "agentCardUnavailable" : ""} ${onClick ? "agentCardInteractive" : ""}`.trim();

  const content = (
    <>
      <div className="agentCardHeader">
        <div className="agentPortraitFrame">
          <img
            className="agentPortrait"
            src={avatarUrlForAgent(legend.agent_id)}
            alt={`${legend.display_name} portrait`}
            loading="lazy"
          />
        </div>
        <div className="agentCardBody">
          <div className="agentIdentity">
            <p className="agentName">{legend.display_name}</p>
            <p className="agentDescription">{legend.archetype}</p>
          </div>
          <div className="agentCardFooter">
            <div className="agentCardTopRow">
              <span className="agentDraftState">
                <span className="agentDraftStateText">{badge}</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </>
  );

  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick} disabled={disabled}>
        {content}
      </button>
    );
  }

  return <article className={className}>{content}</article>;
}