// TelemetryPanel is now a thin renderer for a fully prepared telemetry view
// model. Heavy derivation happens in a dedicated hook closer to the parent.
import type { RefObject } from "react";

import type { TelemetryPanelViewModel } from "../types";
import { TelemetryServiceStatus } from "./telemetry-service-status";
import { TelemetrySummarySections } from "./telemetry-summary-sections";

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
