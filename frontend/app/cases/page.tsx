"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Case, getCases } from "@/lib/api";

const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;

function CasesInner() {
  const params = useSearchParams();
  const router = useRouter();
  const machine = params.get("machine") || "";
  const [cases, setCases] = useState<Case[]>([]);
  const [status, setStatus] = useState<"all" | "pending_review" | "resolved">("all");
  const [priority, setPriority] = useState<string>("all");

  const refresh = useCallback(() => getCases().then(setCases).catch(() => {}), []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const machines = useMemo(
    () => Array.from(new Set(cases.map((c) => c.machine_id))).sort(), [cases]);

  const filtered = cases.filter((c) => {
    if (machine && c.machine_id !== machine) return false;
    if (status === "pending_review" && c.status !== "pending_review") return false;
    if (status === "resolved" && c.status === "pending_review") return false;
    if (priority !== "all" && c.priority !== priority) return false;
    return true;
  });
  const pendingCount = cases.filter((c) => c.status === "pending_review").length;

  const setMachine = (m: string) => {
    const q = new URLSearchParams(Array.from(params.entries()));
    if (m) q.set("machine", m); else q.delete("machine");
    router.replace(`/cases${q.toString() ? `?${q}` : ""}`);
  };

  return (
    <main className="page">
      <div className="section-head">
        <div className="section-title" style={{ margin: 0 }}>
          Triage cases {pendingCount > 0 && <span className="badge P2" style={{ marginLeft: 8 }}>{pendingCount} pending</span>}
        </div>
        <div className="filter-bar">
          <select className="input" value={machine} onChange={(e) => setMachine(e.target.value)}>
            <option value="">all machines</option>
            {machines.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value as any)}>
            <option value="all">any status</option>
            <option value="pending_review">pending review</option>
            <option value="resolved">resolved</option>
          </select>
          <select className="input" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="all">any priority</option>
            {["P1", "P2", "P3", "P4"].map((p) => <option key={p}>{p}</option>)}
          </select>
        </div>
      </div>

      {machine && (
        <div className="cross-links">
          Filtered to <b>{machine}</b> ·
          <Link href={`/machines/${machine}`}> machine</Link> ·
          <Link href={`/cmms?machine=${machine}`}> work orders</Link> ·
          <Link href={`/audit?machine=${machine}`}> audit</Link> ·
          <button className="linkbtn" onClick={() => setMachine("")}>clear</button>
        </div>
      )}

      {filtered.length === 0 && <div className="empty">No cases match. Inject a fault from the Fleet page.</div>}

      <div className="case-cards">
        {filtered.map((c) => {
          const pb = c.priority_breakdown || {};
          const conf = Math.round(c.confidence * 100);
          const abstain = pb.confidence_calibration?.abstain;
          const signature = pb.signature_analysis;
          return (
            <Link key={c.id} href={`/cases/${c.id}`} className={`case-card prio-${c.priority}`}>
              <div className="cc-head">
                <span className={`badge ${c.priority}`}>{c.priority}</span>
                <span className="cc-machine">{c.machine_id}</span>
                <span style={{ flex: 1 }} />
                <span className={`cc-status s-${c.status}`}>
                  <span className="cc-dot" />{c.status.replaceAll("_", " ")}
                </span>
              </div>

              <div className="cc-cause">{c.root_cause}</div>

              <div className="cc-conf-row">
                <div className={`cc-conf-bar ${abstain ? "low" : ""}`}><span style={{ width: `${conf}%` }} /></div>
                <span className="cc-conf-val">{conf}%</span>
                {abstain
                  ? <span className="cc-abstain">uncertain</span>
                  : <span className="cc-conf-label">confidence · {c.llm_mode === "live" ? "live LLM" : "mock"}</span>}
              </div>

              <div className="cc-foot">
                <span className="cc-id">#{c.id}</span>
                {signature && (
                  <span className={`cc-signature ${signature.abstain ? "uncertain" : ""}`}>
                    signature: {signature.abstain
                      ? "abstained"
                      : String(signature.predicted || "none").replaceAll("_", " ")}
                  </span>
                )}
                {pb.est_cost_exposure != null && (
                  <span className="cc-exposure">{usd(pb.est_cost_exposure)}<span className="cc-exposure-l"> exposure</span></span>
                )}
                <span className="cc-spacer" />
                {c.cmms_work_order_id && <span className="cc-wo">WO {c.cmms_work_order_id}</span>}
                {c.reviewer && <span className="cc-reviewer">{c.reviewer}</span>}
              </div>
            </Link>
          );
        })}
      </div>
    </main>
  );
}

export default function CasesPage() {
  return (
    <Suspense fallback={<main className="page"><div className="empty">Loading…</div></main>}>
      <CasesInner />
    </Suspense>
  );
}
