import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Sans_Devanagari, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/AppShell";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-plex-sans",
  fallback: ["ui-sans-serif", "system-ui", "sans-serif"],
});

const plexDeva = IBM_Plex_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-plex-deva",
  fallback: ["IBM Plex Sans Devanagari", "Noto Sans Devanagari", "ui-sans-serif", "system-ui", "sans-serif"],
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-plex-mono",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
});

export const metadata: Metadata = {
  title: {
    default: "AADHESH — Environmental operations",
    template: "%s — AADHESH",
  },
  description:
    "From environmental order to verified action. AADHESH connects official restrictions, site obligations and worker acknowledgement through a verifiable evidence trail.",
  manifest: "/manifest.json",
  icons: {
    icon: "/icon.svg",
    apple: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${plexSans.variable} ${plexDeva.variable} ${plexMono.variable}`}
    >
      <head>
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content"
        />
      </head>
      <body className="font-sans">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
