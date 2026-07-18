"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Case, Machine, Reading, getCases, getMachines, getTelemetry } from "@/lib/api";
import Sparkline from "@/components/Sparkline";

const POLL_MS = 5000;

export default function MachinePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [machine, setMachine] = useState<Machine | null>(null);
  const [series, setSeries] = useState<Reading[]>([]);
  const [cases, setCases] = useState<Case[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [ms, tel, cs] = await Promise.all([
        getMachines(), getTelemetry(id, 200), getCases(),
      ]);
      setMachine(ms.find((m) => m.id === id) || null);
      setSeries(tel);
      setCases(cs.filter((c) => c.machine_id === id));
    } catch { /* chrome shows offline */ }
  }, [id]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  if (!machine) return <main className="page narrow"><div className="empty">Loading {id}…</div></main>;

  const times = series.map((r) => new Date(r.ts).toLocaleTimeString());
  const latest = series[series.length - 1];

  return (
    <main className="page narrow">
      <div className="case-head">
        <button className="back" onClick={() => router.back()} aria-label="Back">←</button>
        <div>
          <h2>{machine.name}</h2>
          <div className="meta">
            {machine.location} · criticality {machine.criticality}/5 · {machine.type}
          </div>
        </div>
        <span style={{ flex: 1 }} />
        {machine.source === "replay" && (
          <span className="badge real" title={`${machine.dataset.dataset} (${machine.dataset.license}) — real recorded telemetry`}>
            ● real data — {machine.dataset.dataset}
          </span>
        )}
        {machine.fault_active && <span className="badge P2 big">fault active</span>}
      </div>

      <div className="section-title">Signals — last {series.length} readings</div>
      {machine.signals.map((s) => {
        const vals = series.map((r) => r[s.key]).filter((v) => typeof v === "number");
        return (
          <div className="card block big-signal" key={s.key}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="metric-title">{s.name} <span className="hint">{s.unit}</span></span>
              <span className="metric-now">{typeof latest?.[s.key] === "number" ? latest[s.key] : "—"}</span>
            </div>
            <Sparkline fluid values={vals} labels={times} width={760} height={120} />
          </div>
        );
      })}

      <div className="section-title" style={{ marginTop: 18 }}>Cases on this machine</div>
      {cases.length === 0 && <div className="empty">No cases yet for {machine.id}.</div>}
      {cases.map((c) => (
        <Link key={c.id} href={`/cases/${c.id}`} className="queue-item">
          <span className={`badge ${c.priority}`}>{c.priority}</span>
          <span>
            <span className="title">{c.root_cause.slice(0, 80)}{c.root_cause.length > 80 ? "…" : ""}</span>
            <span className="meta">
              #{c.id} · {new Date(c.created_ts).toLocaleString()} · {c.status.replaceAll("_", " ")}
              {c.reviewer && <> by {c.reviewer}</>}
            </span>
          </span>
          <span className="chev">›</span>
        </Link>
      ))}
    </main>
  );
}
