"use client";
import { useEffect, useState } from "react";
import { AuditEvent, getAudit } from "@/lib/api";

export default function AuditPage() {
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  useEffect(() => {
    const load = () => getAudit().then(setAudit).catch(() => {});
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, []);

  return (
    <main className="page narrow">
      <div className="section-title">Audit trail — system → agent → human → system, every step attributed</div>
      <div className="card">
        {audit.length === 0 && <div className="empty">No events yet</div>}
        {audit.map((a) => (
          <div className="audit-row" key={a.id}>
            <span className="ts">{new Date(a.ts).toLocaleString()}</span>
            <span className={`actor ${a.actor.startsWith("human") ? "human" : ""}`}>{a.actor}</span>
            <span>{a.event_type} · {a.entity} #{a.entity_id}</span>
          </div>
        ))}
      </div>
    </main>
  );
}
