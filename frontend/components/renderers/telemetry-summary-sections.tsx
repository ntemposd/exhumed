// These sections render the derived telemetry summary once the parent has
// already converted raw metrics into display-ready rows and labels.
import { SidebarSection } from "./sidebar-section";
import { TelemetryTable, VectorUsageTable, type TelemetryTableRow, type VectorUsageRow } from "./telemetry-tables";

const SESSION_COST_HELPER_TEXT = "Spend estimate based on token volume.";
const DIVERSITY_HELPER_TEXT = "Diversity calculated as average pairwise Jaccard entropy between a response and the immediately preceding one.";

type TelemetrySummarySectionsProps = {
  performanceRows: TelemetryTableRow[];
  totalVectorHits: number;
  vectorTurnCount: number;
  uniqueVectorSources: number;
  uniqueVectorSourceLabels: string[];
  vectorRows: VectorUsageRow[];
  displayedTotalTokens: number;
  requestCount: number;
  tokenTableRows: TelemetryTableRow[];
  sessionBurnUsd: number;
  observedRatio: number;
  diversityValue: string;
  diversityLabel: string;
  vocalShareRows: TelemetryTableRow[];
};

export function TelemetrySummarySections({
  performanceRows,
  totalVectorHits,
  vectorTurnCount,
  uniqueVectorSources,
  uniqueVectorSourceLabels,
  vectorRows,
  displayedTotalTokens,
  requestCount,
  tokenTableRows,
  sessionBurnUsd,
  observedRatio,
  diversityValue,
  diversityLabel,
  vocalShareRows,
}: TelemetrySummarySectionsProps) {
  return (
    <>
      <SidebarSection title="MODEL PERFORMANCE">
        <TelemetryTable rows={performanceRows} variant="shadowed" />
      </SidebarSection>

      <SidebarSection title="VECTOR USAGE">
        <div className="telemetryCard telemetryMetricCard">
          <div className="telemetryTokenHeader">
            <div className="telemetryTokenTopline">
              <div className="telemetryTokenValue">{totalVectorHits} {totalVectorHits === 1 ? "Hit" : "Hits"}</div>
              <span className="telemetryTokenBadge">{vectorTurnCount} {vectorTurnCount === 1 ? "Turn" : "Turns"}</span>
            </div>
          </div>
          <div className="telemetryCaption">
            {vectorTurnCount > 0
              ? `${uniqueVectorSources} unique ${uniqueVectorSources === 1 ? "source" : "sources"} contributed retrieval context.`
              : "No retrieval activity yet."}
          </div>
          {uniqueVectorSourceLabels.length > 0 ? (
            <div className="vectorUsageSourceChipRow">
              {uniqueVectorSourceLabels.map((source) => (
                <span key={source} className="vectorSourceChip">{source}</span>
              ))}
            </div>
          ) : null}
          {vectorRows.length > 0 ? <VectorUsageTable rows={vectorRows} /> : null}
        </div>
      </SidebarSection>

      <SidebarSection title="TOKEN USAGE">
        <div className="telemetryCard telemetryMetricCard">
          <div className="telemetryTokenHeader">
            <div className="telemetryTokenTopline">
              <div className="telemetryTokenValue">{displayedTotalTokens} Tokens</div>
              <span className="telemetryTokenBadge">{requestCount} {requestCount === 1 ? "Request" : "Requests"}</span>
            </div>
          </div>
          {tokenTableRows.length > 0 ? <TelemetryTable rows={tokenTableRows} variant="bordered" /> : <div className="telemetryCaption">No request metrics yet. Each turn will be one model request.</div>}
        </div>
      </SidebarSection>

      <SidebarSection title="SESSION COST">
        <div className="telemetryCard">
          <div className="telemetryCostValue">${sessionBurnUsd.toFixed(6)}</div>
          <div className="telemetryCaption">{SESSION_COST_HELPER_TEXT}</div>
        </div>
      </SidebarSection>

      <SidebarSection title="DEBATE DIVERSITY">
        <div className="telemetryCard">
          <div className="telemetryEntropyTopline">
            <span className="telemetryEntropyValue">{diversityValue}</span>
            <span className="telemetryEntropyStatus">{diversityLabel}</span>
          </div>
          <div className="telemetryEntropyTrack">
            <div className="telemetryEntropyFill" style={{ width: `${observedRatio * 100}%` }} />
          </div>
          <div className="telemetryCaption">{DIVERSITY_HELPER_TEXT}</div>
        </div>
      </SidebarSection>

      <SidebarSection title="VOCAL SHARE">
        {vocalShareRows.length > 0 ? <TelemetryTable rows={vocalShareRows} variant="shadowed" /> : <div className="telemetryCaption">No air-time data yet.</div>}
      </SidebarSection>
    </>
  );
}