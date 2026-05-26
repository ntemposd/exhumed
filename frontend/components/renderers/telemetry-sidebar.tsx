// TelemetrySidebar owns every component in the telemetry column:
// the layout wrapper (SidebarSection), table primitives (TelemetryTable /
// VectorUsageTable), per-section renderers, and the panel root (TelemetryPanel).
// Internal helpers are not exported — only the three public surfaces are.
import type { RefObject } from "react";

import type { ServiceStatus } from "@/lib/types";

import type { AsyncViewState, TelemetryPanelViewModel, TelemetryTableRow, VectorUsageRow } from "../types";
import styles from "./telemetry-sidebar.module.css";

export type { TelemetryTableRow, VectorUsageRow };

type TelemetryTableVariant = "plain" | "bordered" | "shadowed";

// ─── SidebarSection ───────────────────────────────────────────────────────

type SidebarSectionProps = {
  title?: string;
  heading?: React.ReactNode;
  children: React.ReactNode;
  panelClassName?: string;
  headingClassName?: string;
};

function SidebarSection({ title, heading, children, panelClassName, headingClassName }: SidebarSectionProps) {
  const resolvedHeading = heading ?? title;

  return (
    <section className="sidebarSectionGroup">
      {resolvedHeading
        ? <h3 className={`sidebarSectionHeading ${headingClassName ?? ""}`.trim()}>{resolvedHeading}</h3>
        : null}
      <div className={`sidebarSectionBody ${panelClassName ?? ""}`.trim()}>{children}</div>
    </section>
  );
}

// ─── Table primitives ─────────────────────────────────────────────────────

function TelemetryTableShell({
  children,
  className = "",
  variant = "plain",
}: {
  children: React.ReactNode;
  className?: string;
  variant?: TelemetryTableVariant;
}) {
  const variantClass = variant === "bordered"
    ? styles.tableShellBordered
    : variant === "shadowed"
      ? styles.tableShellShadowed
      : "";

  return (
    <div className={[styles.tableShell, variantClass, className].filter(Boolean).join(" ")}>
      {children}
    </div>
  );
}

function renderSpeakerCell(value: string) {
  const match = value.match(/^(T\d+)\s■\s(.+)$/);
  if (!match) return value;

  const [, turnLabel, speakerLabel] = match;
  return (
    <span className={styles.speakerCell}>
      <span>{turnLabel}</span>
      <span className={styles.speakerMarker} aria-hidden="true">■</span>
      <span>{speakerLabel}</span>
    </span>
  );
}

export function VectorUsageTable({ rows }: { rows: VectorUsageRow[] }) {
  if (rows.length === 0) return null;

  return (
    <TelemetryTableShell className={styles.vectorUsageTableShell} variant="bordered">
      <div className={styles.vectorUsageTableInner}>
        <table className={[styles.table, styles.vectorUsageTable, styles.summaryTable].join(" ")}>
          <thead>
            <tr>
              <th>Speaker</th>
              <th>Hits</th>
              <th>Chars</th>
              <th>Top</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.speaker} {...(row._tone !== undefined ? { "data-tone": row._tone } : {})}>
                <td>{renderSpeakerCell(row.speaker)}</td>
                <td>{row.hits}</td>
                <td>{row.context}</td>
                <td>{row.top}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </TelemetryTableShell>
  );
}

export function TelemetryTable({
  rows,
  variant = "plain",
  tableClassName = "",
}: {
  rows: TelemetryTableRow[];
  variant?: TelemetryTableVariant;
  tableClassName?: string;
}) {
  if (rows.length === 0) return null;

  const columns = Object.keys(rows[0]).filter((key) => !key.startsWith("_"));

  return (
    <TelemetryTableShell variant={variant}>
      <table className={[styles.table, tableClassName ? styles[tableClassName as keyof typeof styles] ?? tableClassName : ""].filter(Boolean).join(" ")}>
        <thead>
          <tr>
            {columns.map((col) => <th key={col}>{col}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={`${idx}-${row[columns[0]]}`}
              className={row[columns[0]] === "Total" ? styles.totalRow : undefined}
              data-tone={row["_tone"]}
            >
              {columns.map((col) => (
                <td key={col}>{col === "Speaker" ? renderSpeakerCell(row[col]) : row[col]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </TelemetryTableShell>
  );
}

// ─── Service status ───────────────────────────────────────────────────────

const SERVICE_PROVIDER: Record<string, string> = {
  Redis: "Upstash",
  Vector: "Upstash",
  Inference: "Groq",
};

type TelemetryServiceStatusProps = {
  servicesState: AsyncViewState;
  onlineServices: number;
  serviceRows: ServiceStatus[];
};

function TelemetryServiceStatus({ servicesState, onlineServices, serviceRows }: TelemetryServiceStatusProps) {
  const serviceTableRows: TelemetryTableRow[] = serviceRows.map((service) => ({
    Service: service.name,
    Provider: SERVICE_PROVIDER[service.name] ?? "—",
    "Net RTT": typeof service.latency_ms === "number" ? `${Math.round(service.latency_ms)} ms` : "--",
  }));
  const serviceNotes = serviceRows
    .filter((s) => s.detail && s.status?.toUpperCase() !== "ONLINE")
    .map((s) => `${s.name}: ${s.detail}`);
  const slug = servicesState.phase === "error"
    ? "offline"
    : servicesState.phase === "loading" || onlineServices === 0
      ? "standby"
      : onlineServices === serviceRows.length
        ? "online"
        : "degraded";
  const heading = (
    <span className="telemetryStatusSummary sessionInline">
      <span className="sessionInlineLabel telemetryStatusLabel">System Status:</span>
      <span className={`sessionInlineValue telemetryStatusValue telemetryStatusValue${slug.charAt(0).toUpperCase()}${slug.slice(1)}`}>
        {slug.toUpperCase()}
      </span>
    </span>
  );

  return (
    <SidebarSection heading={heading} headingClassName="telemetryStatusHeading">
      <div className="telemetryStatusBody">
        {serviceTableRows.length > 0
          ? <TelemetryTable rows={serviceTableRows} variant="bordered" />
          : <p className="statusNote">{servicesState.summary}</p>}
        {servicesState.phase === "refreshing" && servicesState.detail
          ? <p className="telemetryNote">{servicesState.detail}</p>
          : null}
        {serviceNotes.map((note) => <p key={note} className="telemetryNote">{note}</p>)}
        {servicesState.phase === "error" && servicesState.detail
          ? <p className="statusNote">{servicesState.detail}</p>
          : null}
      </div>
    </SidebarSection>
  );
}

// ─── Summary sections ─────────────────────────────────────────────────────

const SESSION_COST_CAPTION = "Spend estimate based on token volume.";
const DIVERSITY_CAPTION = "Diversity calculated as average pairwise Jaccard entropy between a response and the immediately preceding one.";

type TelemetrySummarySectionsProps = {
  performanceRows: TelemetryTableRow[];
  sessionBurnUsd: number;
  observedRatio: number;
  diversityValue: string;
  diversityLabel: string;
  vocalShareRows: TelemetryTableRow[];
};

function TelemetrySummarySections({
  performanceRows,
  sessionBurnUsd,
  observedRatio,
  diversityValue,
  diversityLabel,
  vocalShareRows,
}: TelemetrySummarySectionsProps) {
  return (
    <>
      <SidebarSection title="DEBATE DIVERSITY">
        <div className={styles.card}>
          <div className={styles.entropyTopline}>
            <span className={styles.entropyValue}>{diversityValue}</span>
            <span className={styles.entropyStatus}>{diversityLabel}</span>
          </div>
          <div className={styles.track}>
            <div className={styles.fill} style={{ width: `${observedRatio * 100}%` }} />
          </div>
          <div className={styles.caption}>{DIVERSITY_CAPTION}</div>
        </div>
      </SidebarSection>

      <SidebarSection title="MODEL PERFORMANCE">
        <TelemetryTable rows={performanceRows} variant="shadowed" />
      </SidebarSection>

      <SidebarSection
        title="VOCAL SHARE"
        panelClassName={vocalShareRows.length > 0 ? styles.vocalSharePanel : undefined}
      >
        {vocalShareRows.length > 0
          ? <TelemetryTable rows={vocalShareRows} variant="shadowed" />
          : (
            <div className={styles.emptyState}>
              <p className={styles.emptyStateText}>No air-time data yet.</p>
            </div>
          )}
      </SidebarSection>

      <SidebarSection title="SESSION COST">
        <div className={styles.card}>
          <div className={styles.costValue}>${sessionBurnUsd.toFixed(6)}</div>
          <div className={styles.caption}>{SESSION_COST_CAPTION}</div>
        </div>
      </SidebarSection>
    </>
  );
}

// ─── Panel root ───────────────────────────────────────────────────────────

type TelemetryPanelProps = {
  viewModel: TelemetryPanelViewModel;
  containerRef: RefObject<HTMLElement | null>;
};

export function TelemetryPanel({ viewModel, containerRef }: TelemetryPanelProps) {
  const {
    servicesState,
    onlineServices,
    serviceRows,
    performanceRows,
    sessionBurnUsd,
    observedRatio,
    diversityValue,
    diversityLabel,
    vocalShareRows,
  } = viewModel;

  return (
    <aside className="telemetryColumn" ref={containerRef}>
      <div className="panel telemetryPanel">
        <TelemetryServiceStatus
          servicesState={servicesState}
          onlineServices={onlineServices}
          serviceRows={serviceRows}
        />
        <TelemetrySummarySections
          performanceRows={performanceRows}
          sessionBurnUsd={sessionBurnUsd}
          observedRatio={observedRatio}
          diversityValue={diversityValue}
          diversityLabel={diversityLabel}
          vocalShareRows={vocalShareRows}
        />
      </div>
    </aside>
  );
}
