// ControlSidebar renders the operator controls for council selection, entropy,
// command actions, and session metadata.
import type { CSSProperties } from "react";

import { SidebarSection } from "./sidebar-section";
import type { ControlSidebarActions, ControlSidebarViewModel } from "../types";
import { logoUrl } from "../utils";

type ControlSidebarProps = {
  viewModel: ControlSidebarViewModel;
  actions: ControlSidebarActions;
};

export function ControlSidebar({
  viewModel,
  actions,
}: ControlSidebarProps) {
  const { chrome, session } = viewModel;
  const draftedCouncilNote = session.selectedCouncil.length === 0
    ? session.legendCatalogState.phase === "loading" || session.legendCatalogState.phase === "error"
      ? session.legendCatalogState.summary
      : "No entities recovered. Draft at least one legend."
    : null;
  const sliderFill = `${Math.max(0, Math.min(100, (session.targetEntropy / 1.5) * 100))}%`;
  const sliderStyle = {
    "--slider-fill": sliderFill,
  } as CSSProperties;

  return (
    <>
      <div className="sidebarRailHeader">
        <div className="sidebarBrand">
          <img className="sidebarLogo" src={logoUrl()} alt="Exhumed logo" />
          {chrome.isSidebarOpen || chrome.isMobileViewport ? (
            <div className="sidebarBrandCopy">
              <span className="sidebarBrandTitle">EXHUMED</span>
              <span className="sidebarBrandSubtitle">Historical Logic Engine</span>
            </div>
          ) : null}
        </div>
        {chrome.showSidebarToggle ? (
          <button
            type="button"
            className="sidebarToggle sidebarToggleIntegrated"
            onClick={actions.onToggleSidebar}
            aria-expanded={chrome.isSidebarOpen}
            aria-controls="exhumed-control-sidebar"
            aria-label={chrome.isSidebarOpen ? "Collapse controls sidebar" : "Expand controls sidebar"}
          >
            <span className="sidebarToggleGlyph" aria-hidden="true">
              {chrome.isMobileViewport ? "x" : chrome.isSidebarOpen ? "x" : ">"}
            </span>
          </button>
        ) : null}
      </div>

      <div className="panel">
        <div className="stack">
          <button className="button buttonBlock" type="button" onClick={actions.onOpenSpeakerModal}>
            Select Speaker
          </button>

          <SidebarSection title="DRAFTED COUNCIL" panelClassName="panel">
            {draftedCouncilNote ? <p className="statusNote">{draftedCouncilNote}</p> : null}
            <div className="draftedCouncil">
              {session.selectedCouncil.map((legend) => (
                <button
                  key={legend.agent_id}
                  type="button"
                  className="draftedChip"
                  onClick={() => actions.onToggleCouncilMember(legend.agent_id)}
                  disabled={session.discussionActive}
                >
                  <span className="draftedChipLabel">{legend.display_name}</span>
                  <span className="draftedChipRemove" aria-hidden="true">x</span>
                </button>
              ))}
            </div>
          </SidebarSection>

          <SidebarSection title="LOGIC ENTROPY" panelClassName="entropyPanel">
            <div className="entropyHeader">
              <div>
                <p className="helper">Adjust between rigid logic and creative unpredictability.</p>
              </div>
            </div>
            <input
              className="entropySlider"
              type="range"
              min="0"
              max="1.5"
              step="0.05"
              value={session.targetEntropy}
              style={sliderStyle}
              onChange={(event) => actions.onTargetEntropyChange(Number(event.target.value))}
              disabled={session.discussionActive}
            />
            <div className="sliderLabels">
              <span>Rigid</span>
              <span>Creative</span>
            </div>
          </SidebarSection>

          <SidebarSection title="COMMANDS" panelClassName="stack commandPanel">
            <div className="actions actionsCompact">
              <button className="button" type="button" onClick={actions.onStartDebate} disabled={session.discussionActive}>
                {session.startButtonLabel}
              </button>
              <button className="buttonGhost" type="button" onClick={actions.onHaltDebate} disabled={!session.discussionActive}>
                ❚❚ Halt Debate
              </button>
            </div>

            <div className="actions actionsCompact">
              <button className="buttonDanger" type="button" onClick={() => void actions.onWipeDebate()} disabled={session.isWipingSession}>
                {session.isWipingSession ? "Wiping..." : "🧹 Wipe Debate"}
              </button>
              <button
                className="buttonGhost"
                type="button"
                onClick={() => void actions.onDownloadTranscript()}
                disabled={session.isDownloadingTranscript}
              >
                {session.isDownloadingTranscript ? "Preparing..." : "📃 Download Transcript"}
              </button>
            </div>
          </SidebarSection>

          <SidebarSection title="SESSION" panelClassName="sessionPanel">
            <div className="sessionInline">
              <span className="sessionInlineLabel">Current ID:</span>
              <span className="sessionInlineValue" title={session.sessionId || "Pending"}>
                {session.sessionId || "Pending"}
              </span>
            </div>
            <div className="actions actionsCompact sessionActions">
              <button className="buttonGhost" type="button" onClick={actions.onRenewSession}>
                ⟳ Refresh Session
              </button>
            </div>
          </SidebarSection>

          {session.controlError ? <p className="statusNote">{session.controlError}</p> : null}
        </div>
      </div>
    </>
  );
}
