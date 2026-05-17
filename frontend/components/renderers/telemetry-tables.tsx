// Shared table primitives keep the telemetry column visually consistent while
// letting each section supply its own prepared row data.
import primitives from "./telemetry-primitives.module.css";
import styles from "./telemetry-tables.module.css";

type TelemetryTableVariant = "plain" | "bordered" | "shadowed";

export type TelemetryTableRow = Record<string, string>;

export type VectorUsageRow = {
  speaker: string;
  hits: string;
  top: string;
  context: string;
};

type TelemetryTableShellProps = {
  children: React.ReactNode;
  className?: string;
  variant?: TelemetryTableVariant;
};

function TelemetryTableShell({ children, className = "", variant = "plain" }: TelemetryTableShellProps) {
  const variantClassName = variant === "bordered"
    ? primitives.tableShellBordered
    : variant === "shadowed"
      ? primitives.tableShellShadowed
      : "";

  return (
    <div className={[primitives.tableShell, variantClassName, className].filter(Boolean).join(" ")}>
      {children}
    </div>
  );
}

function renderSpeakerCell(value: string) {
  const match = value.match(/^(T\d+)\s■\s(.+)$/);
  if (!match) {
    return value;
  }

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
  if (rows.length === 0) {
    return null;
  }

  return (
    <TelemetryTableShell className={styles.vectorUsageTableShell} variant="bordered">
      <div className={styles.vectorUsageTableInner}>
        <table className={[primitives.table, styles.vectorUsageTable, styles.summaryTable].join(" ")}>
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
              <tr key={row.speaker}>
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

export function TelemetryTable({ rows, variant = "plain", tableClassName = "" }: { rows: TelemetryTableRow[]; variant?: TelemetryTableVariant; tableClassName?: string }) {
  if (rows.length === 0) {
    return null;
  }

  const columns = Object.keys(rows[0]);

  return (
    <TelemetryTableShell variant={variant}>
      <table className={[primitives.table, tableClassName ? styles[tableClassName as keyof typeof styles] ?? tableClassName : ""].filter(Boolean).join(" ")}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${index}-${row[columns[0]]}`} className={row[columns[0]] === "Total" ? styles.totalRow : undefined}>
              {columns.map((column) => (
                <td key={column}>{column === "Speaker" ? renderSpeakerCell(row[column]) : row[column]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </TelemetryTableShell>
  );
}