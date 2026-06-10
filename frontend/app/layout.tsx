// RootLayout owns the global font setup and document shell for the Next app.
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/next";
import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import Script from "next/script";

import { BuyMeACoffee } from "@/components/buy-me-a-coffee";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

import "./globals.css";

// Single load — --font-display is aliased to --font-mono in globals.css :root.
const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://exhumed.ntemposd.me"),
  title: "EXHUMED – Historical Convo Engine",
  description: "Historical Convo Engine",
  openGraph: {
    title: "EXHUMED – Historical Convo Engine",
    description: "Historical Convo Engine",
    url: "https://exhumed.ntemposd.me",
    siteName: "EXHUMED",
    images: [{ url: "/logo.png", alt: "EXHUMED" }],
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "EXHUMED – Historical Convo Engine",
    description: "Historical Convo Engine",
    images: ["/logo.png"],
  },
};

// Theme init runs before first paint via beforeInteractive Script below.

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={monoFont.variable}>
        <Script id="exhumed-theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
        {children}
        <Analytics />
        <SpeedInsights />
        <BuyMeACoffee />
      </body>
    </html>
  );
}