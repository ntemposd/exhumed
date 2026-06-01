"use client";

// The Buy Me a Coffee widget mounts its floating button on the page's
// DOMContentLoaded event. Loaded via next/script (after hydration) that event
// has already fired, so the listener never runs and the button never appears.
// Re-dispatching DOMContentLoaded once the script loads triggers the mount.
import Script from "next/script";

export function BuyMeACoffee() {
  return (
    <Script
      data-name="BMC-Widget"
      data-cfasync="false"
      src="https://cdnjs.buymeacoffee.com/1.0.0/widget.prod.min.js"
      data-id="ntemposd"
      data-description="Support me on Buy me a coffee!"
      data-message=""
      data-color="#BD5FFF"
      data-position="Right"
      data-x_margin="18"
      data-y_margin="18"
      strategy="afterInteractive"
      onLoad={() => {
        window.dispatchEvent(new Event("DOMContentLoaded", { bubbles: true, cancelable: true }));
      }}
    />
  );
}
