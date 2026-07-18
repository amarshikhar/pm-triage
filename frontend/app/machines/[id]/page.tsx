"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  AuditEvent, Case, Machine, Reading, WorkOrder,
  getAudit, getCases, getMachines, getTelemetry, getWorkOrders,
} from "@/lib/api";
import AxisChart from "@/components/AxisChart";

const POLL_MS = 5000;

export default function MachinePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [machine, setMachine] = useState<Machine | null>(null);
  const [series, setSeries] = useState<Reading[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [ms, tel, cs, wo, au] = await Promise.all([
        getMachines(), getTelemetry(id, 240), getCases(), getWorkOrders(), getAudit(id),
      ]);
      setMachine(ms.find((m) => m.id === id) || null);
      setSeries(tel);
      setCases(cs.filter((c) => c.machine_id === id));
      setWorkOrders(wo.filter((w) => w.equipment_id === id));
      setAudit(au);
    } catch { /* chrome shows offline */ }
  }, [id]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  if (!machine) return <main className="page"><div className="empty">Loading {id}…</div></main>;

  const times = series.map((r) => new Date(r.ts).toLocaleTimeString());
  const pending = cases.filter((c) => c.status === "pending_review");
  const resolved = cases.filter((c) => c.status !== "pending_review");

  return (
    <main className="page">
      <div className="case-head">
        <button className="back" onClick={() => router.back()} aria-label="Back">←</button>
        <div>
          <h2>{machine.name}</h2>
          <div className="meta">{machine.location} · criticality {machine.criticality}/5 · {machine.type}</div>
        </div>
        <span style={{ flex: 1 }} />
        {machine.source === "replay" && (
          <span className="badge real" title={`${machine.dataset.dataset} (${machine.dataset.license})`}>
            ● real data — {machine.dataset.dataset}
          </span>
        )}
        {machine.fault_active && <span className="badge P2 big">fault active</span>}
      </div>

      <div className="section-title">Signals — last {series.length} readings</div>
      <div className="chart-grid">
        {machine.signals.map((s) => (
          <div className="card chart-card" key={s.key}>
            <AxisChart
              label={s.name} unit={s.unit}
              values={series.map((r) => r[s.key]).filter((v) => typeof v === "number")}
              times={times}
            />
          </div>
        ))}
      </div>

      <div className="machine-panels">
        <div className="card block">
          <h4>Cases on this machine</h4>
          {cases.length === 0 && <div className="empty small">No cases yet.</div>}
          {pending.length > 0 && <div className="panel-sub">Pending review ({pending.length})</div>}
          {pending.map((c) => <CaseRow key={c.id} c={c} />)}
          {resolved.length > 0 && <div className="panel-sub">Resolved ({resolved.length})</div>}
          {resolved.map((c) => <CaseRow key={c.id} c={c} />)}
        </div>

        <div className="panel-col">
          <div className="card block">
            <h4>Work orders <Link className="panel-link" href={`/cmms?machine=${id}`}>open in CMMS →</Link></h4>
            {workOrders.length === 0 && <div className="empty small">No work orders raised.</div>}
            {workOrders.map((w) => (
              <div className="evidence-wo" key={w.order_id} style={{ borderLeftColor: "var(--p4)" }}>
                <span className="wo-id">{w.order_id}</span> · priority {w.priority_code} · {w.system_status}
                <div style={{ color: "var(--text-muted)" }}>{w.damage_text} ({w.damage_code}) — {w.short_text}</div>
              </div>
            ))}
          </div>

          <div className="card block">
            <h4>Audit for this machine <Link className="panel-link" href={`/audit?machine=${id}`}>full trail →</Link></h4>
            {audit.length === 0 && <div className="empty small">No events yet.</div>}
            {audit.slice(0, 12).map((a) => (
              <div className="audit-row compact" key={a.id}>
                <span className="ts">{new Date(a.ts).toLocaleTimeString()}</span>
                <span className={`actor ${a.actor.startsWith("human") ? "human" : ""}`}>{a.actor}</span>
                <span>{a.event_type.replaceAll("_", " ")}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}

function CaseRow({ c }: { c: Case }) {
  return (
    <Link href={`/cases/${c.id}`} className="queue-item compact">
      <span className={`badge ${c.priority}`}>{c.priority}</span>
      <span>
        <span className="title">{c.root_cause.slice(0, 64)}{c.root_cause.length > 64 ? "…" : ""}</span>
        <span className="meta">#{c.id} · {c.status.replaceAll("_", " ")}{c.reviewer && ` · ${c.reviewer}`}</span>
      </span>
      <span className="chev">›</span>
    </Link>
  );
}
