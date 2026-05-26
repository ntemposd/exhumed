import type { ServiceStatus } from "@/lib/types";

import type { AsyncViewState } from "../types";
import { SidebarSection } from "./sidebar-section";
import { TelemetryTable, type TelemetryTableRow } from "./telemetry-tables";

type TelemetryServiceStatusProps = {
  servicesState: AsyncViewState;
  onlineServices: number;
  serviceRows: ServiceStatus[];
};

export function TelemetryServiceStatus({
  servicesState,
  onlineServices,
  serviceRows,
}: TelemetryServiceStatusProps) {
  const serviceTableRows: TelemetryTableRow[] = serviceRows.map((service) => ({
    Service: service.name,
    "Net RTT": typeof service.latency_ms === "number" ? `${Math.round(service.latency_ms)} ms` : "--",
  }));
  const serviceNotes = serviceRows
    .filter((service) => service.detail && service.status?.toUpperCase() !== "ONLINE")
    .map((service) => `${service.name}: ${service.detail}`);
  const overallStatusSlug = servicesState.phase === "error"
    ? "offline"
    : servicesState.phase === "loading" || onlineServices === 0
      ? "standby"
      : onlineServices === serviceRows.length
        ? "online"
        : "degraded";
  const overallStatusLabel = overallStatusSlug.toUpperCase();
  const heading = (
    <span className="telemetryStatusSummary sessionInline">
      <span className="sessionInlineLabel telemetryStatusLabel">System Status:</span>
      <span className={`sessionInlineValue telemetryStatusValue telemetryStatusValue${overallStatusSlug.charAt(0).toUpperCase()}${overallStatusSlug.slice(1)}`}>{overallStatusLabel}</span>
    </span>
  );

  return (
    <SidebarSection heading={heading} headingClassName="telemetryStatusHeading">
      <div className="telemetryStatusBody">
        {serviceTableRows.length > 0 ? <TelemetryTable rows={serviceTableRows} variant="bordered" /> : <p className="statusNote">{servicesState.summary}</p>}
        {servicesState.phase === "refreshing" && servicesState.detail ? <p className="telemetryNote">{servicesState.detail}</p> : null}
        {serviceNotes.map((note) => (
          <p key={note} className="telemetryNote">{note}</p>
        ))}
        {servicesState.phase === "error" && servicesState.detail ? <p className="statusNote">{servicesState.detail}</p> : null}
      </div>
    </SidebarSection>
  );
}
