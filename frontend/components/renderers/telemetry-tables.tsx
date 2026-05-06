// Shared table primitives keep the telemetry column visually consistent while
// letting each section supply its own prepared row data.
type TelemetryTableVariant = "plain" | "bordered" | "shadowed";

export type TelemetryTableRow = Record<string, string>;

export type VectorUsageRow = {
  turn: string;
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
  return (
    <div className={`telemetryTableShell ${className}`.trim()} data-variant={variant}>
      {children}
    </div>
  );
}

export function VectorUsageTable({ rows }: { rows: VectorUsageRow[] }) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <TelemetryTableShell className="vectorUsageTableShell" variant="bordered">
      <div className="vectorUsageTableInner">
        <table className="telemetryTable vectorUsageTable">
          <thead>
            <tr>
              <th>Turn</th>
              <th>Speaker</th>
              <th>Hits</th>
              <th>Chars</th>
              <th>Top</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.turn}-${row.speaker}`}>
                <td>{row.turn}</td>
                <td>{row.speaker}</td>
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

export function TelemetryTable({ rows, variant = "plain" }: { rows: TelemetryTableRow[]; variant?: TelemetryTableVariant }) {
  if (rows.length === 0) {
    return null;
  }

  const columns = Object.keys(rows[0]);

  return (
    <TelemetryTableShell variant={variant}>
      <table className="telemetryTable">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${index}-${row[columns[0]]}`}>
              {columns.map((column) => (
                <td key={column}>{row[column]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </TelemetryTableShell>
  );
}