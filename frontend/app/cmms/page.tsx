"use client";
import { useEffect, useState } from "react";
import { WorkOrder, getWorkOrders } from "@/lib/api";

export default function CmmsPage() {
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  useEffect(() => {
    const load = () => getWorkOrders().then(setWorkOrders).catch(() => {});
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, []);

  return (
    <main className="page narrow">
      <div className="section-title">
        CMMS — the maintenance system of record (a separate service; this reads it directly)
      </div>
      {workOrders.length === 0 && (
        <div className="empty">No work orders yet. Approve a case to raise one here.</div>
      )}
      {workOrders.map((w) => (
        <div className="card" style={{ marginBottom: 8 }} key={w.order_id}>
          <div className="evidence-wo" style={{ borderLeftColor: "var(--p4)", margin: 0 }}>
            <span className="wo-id">{w.order_id}</span> · {w.notification_type} · priority {w.priority_code} ({w.priority_text}) · {w.system_status}
            <div>{w.equipment_id} @ {w.functional_location} — {w.damage_text} ({w.damage_code})</div>
            <div style={{ color: "var(--text-muted)" }}>
              {w.short_text} · exposure ${Math.round(w.est_cost_exposure).toLocaleString()} · {w.reported_by} · {w.external_ref}
            </div>
          </div>
        </div>
      ))}
    </main>
  );
}
