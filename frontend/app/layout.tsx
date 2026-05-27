// RootLayout owns the global font setup and document shell for the Next app.
import { Analytics } from "@vercel/analytics/react";
import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";

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

// Runs synchronously before first paint: reads localStorage and stamps
// data-theme on <html> before React hydrates, eliminating the light→dark
// flash. Wrapped in try/catch so storage errors never break the page.
const THEME_INIT_SCRIPT = `try{var t=localStorage.getItem('exhumed-theme');if(t==='dark')document.documentElement.dataset.theme='dark';}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className={monoFont.variable}>
        {children}
        <Analytics />
      </body>
    </html>
  );
}