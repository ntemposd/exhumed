// LegendCard renders one selectable council member in the speaker modal.
import type { Agent } from "@/lib/types";

import type { LegendDetails } from "../types";
import { avatarUrlForAgent } from "../utils";
import styles from "./legend-card.module.css";

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
  const className = [
    styles.agentCard,
    active ? styles.agentCardActive : "",
    isUnavailable ? styles.agentCardUnavailable : "",
    onClick ? styles.agentCardInteractive : "",
  ].filter(Boolean).join(" ");

  const content = (
    <>
      <div className={styles.agentCardHeader}>
        <div className={styles.agentPortraitFrame}>
          <img
            className={styles.agentPortrait}
            src={avatarUrlForAgent(legend.agent_id)}
            alt={`${legend.display_name} portrait`}
            loading="lazy"
          />
        </div>
        <div className={styles.agentCardBody}>
          <div className={styles.agentIdentity}>
            <p className={styles.agentName}>{legend.display_name}</p>
            <p className={styles.agentDescription}>{legend.archetype}</p>
          </div>
          <div className={styles.agentCardFooter}>
            <div className={styles.agentCardTopRow}>
              <span className={styles.agentDraftState}>
                <span>{badge}</span>
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