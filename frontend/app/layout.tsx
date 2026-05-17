// RootLayout owns the global font setup and document shell for the Next app.
import { Analytics } from "@vercel/analytics/react";
import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";

import "./globals.css";

const displayFont = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "700"],
});

const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: "EXHUMED Front",
  description: "Next.js frontend prototype for the EXHUMED debate backend.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${displayFont.variable} ${monoFont.variable}`}>
        {children}
        <Analytics />
      </body>
    </html>
  );
}