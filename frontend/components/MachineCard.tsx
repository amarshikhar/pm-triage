"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Machine, Reading, getTelemetry } from "@/lib/api";
import Sparkline from "./Sparkline";

export default function MachineCard({ m }: { m: Machine }) {
  const [series, setSeries] = useState<Reading[]>([]);

  useEffect(() => {
    let alive = true;
    const load = () => getTelemetry(m.id, 40).then((s) => alive && setSeries(s)).catch(() => {});
    load();
    const t = setInterval(load, 4000);
    return () => { alive = false; clearInterval(t); };
  }, [m.id]);

  const l = m.latest;
  const times = series.map((r) => new Date(r.ts).toLocaleTimeString());
  const fmt = (v: any) =>
    typeof v === "number" ? (Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : v) : "—";

  return (
    <div className={`card machine-card ${m.fault_active ? "faulted" : ""}`}>
      <div className="head">
        <div>
          <Link href={`/machines/${m.id}`} className="name machine-link"
                title="Open full-size charts">{m.name} ↗</Link>
          <div className="loc">{m.location} · criticality {m.criticality}/5</div>
        </div>
        <div className="row" style={{ gap: 4 }}>
          {m.source === "replay" && (
            <span className="badge real" title={`${m.dataset.dataset} — real recorded telemetry (${m.dataset.license})`}>
              ● real data
            </span>
          )}
          {m.pending_cases > 0 && <span className="badge P2">⚠ {m.pending_cases} case{m.pending_cases > 1 ? "s" : ""}</span>}
          {m.fault_active && <span className="badge outline">fault active</span>}
        </div>
      </div>
      <div className="metrics">
        {m.signals.map((s) => (
          <div className="metric" key={s.key}>
            <div className="label">{s.name} {s.unit && <span className="unit">{s.unit}</span>}</div>
            <div className="value"><b>{fmt(l?.[s.key])}</b></div>
            <Sparkline values={series.map((r) => r[s.key]).filter((v) => typeof v === "number")}
                       labels={times} />
          </div>
        ))}
      </div>
    </div>
  );
}
