// Layout state is treated as a dedicated concern so viewport breakpoint logic
// and sidebar visibility do not leak into the workbench root.
import { useEffect, useLayoutEffect, useRef, useState } from "react";

type UseWorkbenchLayoutOptions = {
  mobileBreakpointPx: number;
  stackedLayoutBreakpointPx: number;
};

export function useWorkbenchLayout({
  mobileBreakpointPx,
  stackedLayoutBreakpointPx,
}: UseWorkbenchLayoutOptions) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  const [isStackedViewport, setIsStackedViewport] = useState(false);
  const [hasResolvedViewport, setHasResolvedViewport] = useState(false);
  const lastViewportWasStackedRef = useRef<boolean | null>(null);

  useLayoutEffect(() => {
    // Hydrate the chrome from the viewport before the first paint.
    const mobileViewport = window.innerWidth <= mobileBreakpointPx;
    const stackedViewport = window.innerWidth <= stackedLayoutBreakpointPx;

    setIsMobileViewport(mobileViewport);
    setIsStackedViewport(stackedViewport);
    setIsSidebarOpen(true);
    setHasResolvedViewport(true);
    lastViewportWasStackedRef.current = stackedViewport;
  }, [mobileBreakpointPx, stackedLayoutBreakpointPx]);

  useEffect(() => {
    // Crossing the stacked breakpoint reopens the sidebar so each layout mode
    // starts from a predictable, usable default.
    if (typeof window === "undefined") {
      return;
    }

    function syncViewportState() {
      const mobileViewport = window.innerWidth <= mobileBreakpointPx;
      const stackedViewport = window.innerWidth <= stackedLayoutBreakpointPx;
      setIsMobileViewport(mobileViewport);
      setIsStackedViewport(stackedViewport);

      if (lastViewportWasStackedRef.current !== stackedViewport) {
        setIsSidebarOpen(true);
        lastViewportWasStackedRef.current = stackedViewport;
      }
    }

    window.addEventListener("resize", syncViewportState);

    return () => {
      window.removeEventListener("resize", syncViewportState);
    };
  }, [mobileBreakpointPx, stackedLayoutBreakpointPx]);

  function closeSidebar() {
    setIsSidebarOpen(false);
  }

  function toggleSidebar() {
    setIsSidebarOpen((currentValue) => !currentValue);
  }

  return {
    isSidebarOpen,
    isMobileViewport,
    isStackedViewport,
    hasResolvedViewport,
    closeSidebar,
    toggleSidebar,
  };
}