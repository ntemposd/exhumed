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
  display: "optional",
  preload: false,
});

export const metadata: Metadata = {
  title: "EXHUMED Front",
  description: "Next.js frontend prototype for the EXHUMED debate backend.",
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