import type { Metadata, Viewport } from "next";
import Chrome from "@/components/Chrome";
import "./globals.css";

export const metadata: Metadata = {
  title: "PM Triage — Predictive Maintenance Triage Assistant",
  description:
    "Telemetry → explainable detection → AI triage with evidence → human approval → CMMS write-back. Grounded in real SKAB pump data.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Chrome />
        {children}
      </body>
    </html>
  );
}
