"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Case, WorkOrder, getCases, getWorkOrders } from "@/lib/api";

function CmmsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const machine = params.get("machine") || "";
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  const [cases, setCases] = useState<Case[]>([]);

  useEffect(() => {
    const load = () => {
      getWorkOrders().then(setWorkOrders).catch(() => {});
      getCases().then(setCases).catch(() => {});
    };
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, []);

  const machines = useMemo(
    () => Array.from(new Set(workOrders.map((w) => w.equipment_id))).sort(), [workOrders]);
  // work order external_ref is "triage-case-<id>" — link each WO back to its case
  const caseForWO = (w: WorkOrder) => {
    const m = /triage-case-(\d+)/.exec(w.external_ref || "");
    return m ? Number(m[1]) : cases.find((c) => c.cmms_work_order_id === w.order_id)?.id;
  };
  const filtered = machine ? workOrders.filter((w) => w.equipment_id === machine) : workOrders;

  const setMachine = (m: string) => router.replace(`/cmms${m ? `?machine=${m}` : ""}`);

  return (
    <main className="page narrow">
      <div className="section-head">
        <div className="section-title" style={{ margin: 0 }}>CMMS — system of record</div>
        <select className="input" style={{ width: "auto" }} value={machine} onChange={(e) => setMachine(e.target.value)}>
          <option value="">all machines</option>
          {machines.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <p className="hint" style={{ marginTop: 0 }}>
        A separate service with its own schema; this reads it directly to prove the write-back landed.
      </p>

      {filtered.length === 0 && <div className="empty">No work orders{machine ? ` for ${machine}` : ""} yet. Approve a case to raise one.</div>}
      {filtered.map((w) => {
        const caseId = caseForWO(w);
        return (
          <div className="card wo-card" key={w.order_id}>
            <div className="wo-head">
              <span className="wo-id">{w.order_id}</span>
              <span className="chip mini">{w.notification_type}</span>
              <span className="chip mini">priority {w.priority_code} · {w.priority_text}</span>
              <span className="chip mini">{w.system_status}</span>
              <span style={{ flex: 1 }} />
              {caseId && <Link className="panel-link" href={`/cases/${caseId}`}>case #{caseId} →</Link>}
            </div>
            <div className="wo-body">
              <Link href={`/machines/${w.equipment_id}`} className="wo-machine">{w.equipment_id}</Link>
              {" @ "}{w.functional_location} — <b>{w.damage_text}</b> ({w.damage_code})
            </div>
            <div className="wo-foot">
              {w.short_text} · exposure ${Math.round(w.est_cost_exposure).toLocaleString()} · raised by {w.reported_by}
            </div>
          </div>
        );
      })}
    </main>
  );
}

export default function CmmsPage() {
  return (
    <Suspense fallback={<main className="page narrow"><div className="empty">Loading…</div></main>}>
      <CmmsInner />
    </Suspense>
  );
}
