// SidebarSection standardizes the title/body pattern used across control and
// telemetry panes so those surfaces stay visually consistent.
import type { ReactNode } from "react";

type SidebarSectionProps = {
  title?: string;
  heading?: ReactNode;
  children: ReactNode;
  panelClassName?: string;
  headingClassName?: string;
};

export function SidebarSection({ title, heading, children, panelClassName, headingClassName }: SidebarSectionProps) {
  const resolvedHeading = heading ?? title;

  return (
    <section className="sidebarSectionGroup">
      {resolvedHeading ? <h3 className={`sidebarSectionHeading ${headingClassName ?? ""}`.trim()}>{resolvedHeading}</h3> : null}
      <div className={`sidebarSectionBody ${panelClassName ?? ""}`.trim()}>{children}</div>
    </section>
  );
}