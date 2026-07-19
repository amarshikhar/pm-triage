"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { AuditEvent, getAudit } from "@/lib/api";

function actorClass(a: string) {
  if (a.startsWith("human")) return "human";
  if (a === "agent") return "agent";
  return "system";
}

function localTimestamp(value: string) {
  return new Date(value).toLocaleString(undefined, { timeZoneName: "short" });
}

function AuditInner() {
  const params = useSearchParams();
  const router = useRouter();
  const machine = params.get("machine") || "";
  const [audit, setAudit] = useState<AuditEvent[]>([]);

  const load = useCallback(() => getAudit(machine || undefined).then(setAudit).catch(() => {}), [machine]);
  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

  const linkFor = (a: AuditEvent) =>
    a.entity === "case" ? `/cases/${a.entity_id}`
      : a.entity === "machine" ? `/machines/${a.entity_id}` : null;

  return (
    <main className="page narrow">
      <div className="section-head">
        <div className="section-title" style={{ margin: 0 }}>Audit trail</div>
        {machine && (
          <div className="cross-links" style={{ margin: 0 }}>
            <b>{machine}</b> · <Link href={`/machines/${machine}`}>machine</Link> ·{" "}
            <Link href={`/cases?machine=${machine}`}>cases</Link> ·{" "}
            <button className="linkbtn" onClick={() => router.replace("/audit")}>clear</button>
          </div>
        )}
      </div>
      <p className="hint" style={{ marginTop: 0 }}>
        system → agent → human → system, every step attributed. Times use your device timezone.
        “Anomaly detected” is when rules fired; “case created” is later, after triage finished.
      </p>

      <div className="card">
        {audit.length === 0 && <div className="empty small">No events{machine ? ` for ${machine}` : ""} yet.</div>}
        {audit.map((a) => {
          const href = linkFor(a);
          const inner = (
            <>
              <span className="ts" title={`Stored as ${new Date(a.ts).toISOString()}`}>
                {localTimestamp(a.ts)}
              </span>
              <span className={`actor ${actorClass(a.actor)}`}>{a.actor}</span>
              <span>{a.event_type.replaceAll("_", " ")} · {a.entity} #{a.entity_id}{href && <span className="chev"> ›</span>}</span>
            </>
          );
          return href
            ? <Link className="audit-row link" key={a.id} href={href}>{inner}</Link>
            : <div className="audit-row" key={a.id}>{inner}</div>;
        })}
      </div>
    </main>
  );
}

export default function AuditPage() {
  return (
    <Suspense fallback={<main className="page narrow"><div className="empty">Loading…</div></main>}>
      <AuditInner />
    </Suspense>
  );
}
