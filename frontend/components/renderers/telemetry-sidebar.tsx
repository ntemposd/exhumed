// TelemetrySidebar owns every component in the telemetry column:
// the layout wrapper (SidebarSection), table primitives (TelemetryTable /
// VectorUsageTable), per-section renderers, and the panel root (TelemetryPanel).
// Internal helpers are not exported — only the three public surfaces are.
import { type RefObject, useCallback, useRef } from "react";

import type { ServiceStatus } from "@/lib/types";

import { formatConvoCostUsd } from "../utils";
import type { AsyncViewState, TelemetryPanelViewModel, TelemetryTableRow, VectorUsageRow } from "../types";
import styles from "./telemetry-sidebar.module.css";

export type { TelemetryTableRow, VectorUsageRow };

type TelemetryTableVariant = "plain" | "bordered" | "shadowed";

// ─── SidebarSection ───────────────────────────────────────────────────────

type SidebarSectionProps = {
  title?: React.ReactNode;
  children: React.ReactNode;
  panelClassName?: string;
};

function SidebarSection({ title, children, panelClassName }: SidebarSectionProps) {
  return (
    <section className="sidebarSectionGroup">
      {title ? <h2 className="sectionHeading">{title}</h2> : null}
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
              <th>Context</th>
              <th>Top score</th>
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
    "Net RTT": typeof service.latency_ms === "number" ? `${Math.round(service.latency_ms)} ms` : "IDLE",
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

  const statusClass = `telemetryStatusValue telemetryStatusValue${slug.charAt(0).toUpperCase()}${slug.slice(1)}`;

  return (
    <SidebarSection title={<>SYSTEM STATUS: <span className={statusClass}>{slug.toUpperCase()}</span></>}>
      <div className="telemetryStatusBody">
        {serviceTableRows.length > 0
          ? <TelemetryTable rows={serviceTableRows} variant="shadowed" />
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

const CONVO_COST_CAPTION = "Spend estimate for this convo, based on LLM token volume.";
const DIVERSITY_CAPTION = "Lexical spread (Jaccard): average pairwise word-set entropy between each response and the one before it. Measures vocabulary overlap, not semantic similarity.";

type TelemetrySummarySectionsProps = {
  performanceRows: TelemetryTableRow[];
  convoCostUsd: number;
  observedRatio: number;
  diversityValue: string;
  diversityLabel: string;
  vocalShareRows: TelemetryTableRow[];
};

function TelemetrySummarySections({
  performanceRows,
  convoCostUsd,
  observedRatio,
  diversityValue,
  diversityLabel,
  vocalShareRows,
}: TelemetrySummarySectionsProps) {
  return (
    <>
      <SidebarSection title="INFERENCE LATENCY">
        <TelemetryTable rows={performanceRows} variant="shadowed" />
      </SidebarSection>

      <SidebarSection title="CONVO COST">
        <div className={styles.card}>
          <div className={styles.costValue}>{formatConvoCostUsd(convoCostUsd)}</div>
          <div className={styles.caption}>{CONVO_COST_CAPTION}</div>
        </div>
      </SidebarSection>

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
    </>
  );
}

// ─── Panel root ───────────────────────────────────────────────────────────

type TelemetryPanelProps = {
  viewModel: TelemetryPanelViewModel;
  containerRef: RefObject<HTMLDivElement | null>;
  isSidebarOpen: boolean;
  onToggleSidebar: () => void;
};

export function TelemetryPanel({ viewModel, containerRef, isSidebarOpen, onToggleSidebar }: TelemetryPanelProps) {
  const toggleBtnRef = useRef<HTMLButtonElement | null>(null);

  const handleToggle = useCallback(() => {
    onToggleSidebar();
    // On mobile the telemetry column is stacked below the convo, so scroll
    // the toggle button to the top of the viewport after toggling.
    requestAnimationFrame(() => {
      const btn = toggleBtnRef.current;
      if (btn) {
        const top = btn.getBoundingClientRect().top + window.scrollY - 12;
        window.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
      }
    });
  }, [onToggleSidebar]);
  const {
    servicesState,
    onlineServices,
    serviceRows,
    performanceRows,
    convoCostUsd,
    observedRatio,
    diversityValue,
    diversityLabel,
    vocalShareRows,
  } = viewModel;

  return (
    <aside className="telemetryColumn">
      <div className="panel telemetryPanel">
        <button
          ref={toggleBtnRef}
          type="button"
          className={styles.telemetryToggleBtn}
          onClick={handleToggle}
          aria-expanded={isSidebarOpen}
        >
          <span className={styles.telemetryToggleIcon} aria-hidden="true">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </span>
          <span className={styles.telemetryToggleLabel}>{isSidebarOpen ? "Close Telemetry" : "Open Telemetry"}</span>
          <span className={styles.telemetryToggleChevron} aria-hidden="true">{isSidebarOpen ? "−" : "+"}</span>
        </button>
        <div className={styles.telemetrySidebarScroll} ref={containerRef}>
          {isSidebarOpen ? (
            <>
              <TelemetryServiceStatus
                servicesState={servicesState}
                onlineServices={onlineServices}
                serviceRows={serviceRows}
              />
              <TelemetrySummarySections
                performanceRows={performanceRows}
                convoCostUsd={convoCostUsd}
                observedRatio={observedRatio}
                diversityValue={diversityValue}
                diversityLabel={diversityLabel}
                vocalShareRows={vocalShareRows}
              />
            </>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
