// These sections render the derived telemetry summary once the parent has
// already converted raw metrics into display-ready rows and labels.
import primitives from "./telemetry-primitives.module.css";

import { SidebarSection } from "./sidebar-section";
import { TelemetryTable, VectorUsageTable, type TelemetryTableRow, type VectorUsageRow } from "./telemetry-tables";

const SESSION_COST_HELPER_TEXT = "Spend estimate based on token volume.";
const DIVERSITY_HELPER_TEXT = "Diversity calculated as average pairwise Jaccard entropy between a response and the immediately preceding one.";

type TelemetrySummarySectionsProps = {
  performanceRows: TelemetryTableRow[];
  totalVectorHits: number;
  uniqueVectorSources: number;
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
  uniqueVectorSources,
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
      <SidebarSection title="VECTOR CALLS">
        <div className={primitives.metricCardBare}>
          {vectorRows.length > 0 ? <VectorUsageTable rows={vectorRows} /> : (
            <div className={primitives.emptyState}>
              <p className={primitives.emptyStateText}>Vector usage details  will appear here.</p>
            </div>
          )}
        </div>
      </SidebarSection>

      <SidebarSection title="DEBATE DIVERSITY">
        <div className={primitives.card}>
          <div className={primitives.entropyTopline}>
            <span className={primitives.entropyValue}>{diversityValue}</span>
            <span className={primitives.entropyStatus}>{diversityLabel}</span>
          </div>
          <div className={primitives.track}>
            <div className={primitives.fill} style={{ width: `${observedRatio * 100}%` }} />
          </div>
          <div className={primitives.caption}>{DIVERSITY_HELPER_TEXT}</div>
        </div>
      </SidebarSection>

      <SidebarSection title="MODEL PERFORMANCE">
        <TelemetryTable rows={performanceRows} variant="shadowed" />
      </SidebarSection>

      <SidebarSection title="VOCAL SHARE" panelClassName={vocalShareRows.length > 0 ? primitives.vocalSharePanel : undefined}>
        {vocalShareRows.length > 0 ? <TelemetryTable rows={vocalShareRows} variant="shadowed" /> : (
          <div className={primitives.emptyState}>
            <p className={primitives.emptyStateText}>No air-time data yet.</p>
          </div>
        )}
      </SidebarSection>

      <SidebarSection title="TOKENS USED">
        <div className={primitives.metricCardBare}>
          {tokenTableRows.length > 0 ? <TelemetryTable rows={tokenTableRows} variant="bordered" tableClassName="summaryTable" /> : (
            <div className={primitives.emptyState}>
              <p className={primitives.emptyStateText}>No request metrics yet. Each turn will be one model request.</p>
            </div>
          )}
        </div>
      </SidebarSection>

      <SidebarSection title="SESSION COST">
        <div className={primitives.card}>
          <div className={primitives.costValue}>${sessionBurnUsd.toFixed(6)}</div>
          <div className={primitives.caption}>{SESSION_COST_HELPER_TEXT}</div>
        </div>
      </SidebarSection>
    </>
  );
}
