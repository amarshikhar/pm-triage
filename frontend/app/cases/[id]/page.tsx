"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Case, SignalStats, decideCase, getCase, getSession, retryCmmsSync } from "@/lib/api";

const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [c, setC] = useState<Case | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(
    () => getCase(Number(id)).then(setC).catch((e) => setError(e.message)),
    [id],
  );
  useEffect(() => { refresh(); }, [refresh]);

  if (error) return <main className="page narrow"><div className="empty">Case not found — {error}</div></main>;
  if (!c) return <main className="page narrow"><div className="empty">Loading case #{id}…</div></main>;

  const pending = c.status === "pending_review";
  const pb = c.priority_breakdown || {};

  return (
    <main className="page case-page">
      <div className="case-head">
        <button className="back" onClick={() => router.back()} aria-label="Back">←</button>
        <div>
          <h2>Case #{c.id} · {c.machine_id}</h2>
          <div className="meta">
            opened {new Date(c.created_ts).toLocaleString()} ·{" "}
            {c.llm_mode === "live" ? c.llm_model : "deterministic mock policy"}
          </div>
        </div>
        <span style={{ flex: 1 }} />
        <span className="badge outline big">{c.status.replaceAll("_", " ")}</span>
        <span className={`badge ${c.priority} big`}>{c.priority}</span>
      </div>

      <div className="cross-links">
        <Link href={`/machines/${c.machine_id}`}>{c.machine_id} machine</Link> ·
        <Link href={`/cases?machine=${c.machine_id}`}> its cases</Link> ·
        {c.cmms_work_order_id
          ? <Link href={`/cmms?machine=${c.machine_id}`}> work order {c.cmms_work_order_id}</Link>
          : <span className="muted"> no work order yet</span>} ·
        <Link href={`/audit?machine=${c.machine_id}`}> audit</Link>
      </div>

      <div className="case-grid">
        <section className="chat" aria-label="Agent investigation">
          <div className="section-title">Investigation — every step, verbatim</div>
          {(c.trace || []).map((t: any, i: number) => <TraceBubble key={i} t={t} />)}
          <FinalBubble c={c} />
          {!pending && <DecisionBubble c={c} />}
        </section>

        <aside className="facts">
          {c.anomaly && (
            <div className="card block">
              <h4>Detection (rules, not AI)</h4>
              <p>{c.anomaly.description}</p>
              <p className="hint">severity {c.anomaly.severity} · z = {c.anomaly.zscore}</p>
            </div>
          )}

          <SignalTable c={c} />

          <div className="card block">
            <h4>Priority — auditable formula</h4>
            <p className="hint" style={{ fontSize: 12 }}>
              criticality {pb.components?.machine_criticality} + severity {pb.components?.anomaly_severity} +
              recurrence {pb.components?.recurrence} + safety {pb.components?.safety_flag} = {pb.score} → {pb.priority}
              {pb.agent_adjustment
                ? ` · agent ${pb.agent_adjustment > 0 ? "+" : ""}${pb.agent_adjustment} (${pb.agent_justification}) → ${pb.final_priority}`
                : ""}
            </p>
            {pb.est_cost_exposure != null && (
              <p className="exposure">
                {usd(pb.est_cost_exposure)} <span className="hint">exposure if unaddressed
                ({pb.est_downtime_hours}h × {usd(pb.hourly_downtime_cost)}/h) — informational,
                not part of the score</span>
              </p>
            )}
          </div>

          {c.evidence?.historical_matches?.length > 0 && (
            <div className="card block">
              <h4>Cited history (CMMS)</h4>
              {c.evidence.historical_matches.slice(0, 4).map((m: any) => (
                <div className="evidence-wo" key={m.work_order}>
                  <span className="wo-id">{m.work_order}</span> · {m.date} · {m.machine_id}
                  {m.record_type === "routine" && <span className="badge outline" style={{ marginLeft: 6 }}>routine</span>}
                  {m.safety_related && <span className="badge P1" style={{ marginLeft: 6 }}>safety</span>}
                  <div>{m.failure_mode} — {m.root_cause}</div>
                  <div style={{ color: "var(--text-muted)" }}>fixed by: {m.action_taken} ({m.downtime_hours}h)</div>
                </div>
              ))}
            </div>
          )}

          <CmmsPanel c={c} onChanged={refresh} />
          {pending && <DecisionBox c={c} onDecided={refresh} />}
        </aside>
      </div>
    </main>
  );
}

function TraceBubble({ t }: { t: any }) {
  if (t.step === "anomaly") {
    return (
      <div className="bubble detector">
        <div className="who">detector</div>
        <p>{t.detail}</p>
      </div>
    );
  }
  if (t.step === "llm_fallback") {
    return (
      <div className="bubble warn">
        <div className="who">⚠ llm fallback</div>
        <p>{t.detail}</p>
      </div>
    );
  }
  if (t.step === "tool_call") {
    return (
      <div className="bubble agent">
        <div className="who">agent → <code>{t.tool}</code></div>
        <p className="args">{JSON.stringify(t.args)}</p>
        {t.result_summary && <div className="tool-result">{t.result_summary}</div>}
      </div>
    );
  }
  if (t.step === "final_answer") return null; // rendered as FinalBubble
  return (
    <div className="bubble system">
      <div className="who">{t.step}</div>
      <p>{t.detail}</p>
    </div>
  );
}

function FinalBubble({ c }: { c: Case }) {
  return (
    <div className="bubble agent final">
      <div className="who">agent — hypothesis · confidence {(c.confidence * 100).toFixed(0)}%</div>
      <p className="root-cause">{c.root_cause}</p>
      <p>{c.explanation}</p>
      {c.recommended_actions?.length > 0 && (
        <ul>{c.recommended_actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
      )}
    </div>
  );
}

function DecisionBubble({ c }: { c: Case }) {
  const verb = c.status === "rejected" ? "rejected" : c.status.replaceAll("_", " ");
  return (
    <div className={`bubble human ${c.status === "rejected" ? "neg" : "pos"}`}>
      <div className="who">planner — {c.reviewer}</div>
      <p><b>{verb}</b> at {new Date(c.reviewed_ts).toLocaleString()}
        {c.review_note && <> — “{c.review_note}”</>}</p>
      {c.cmms_work_order_id && (
        <p className="hint">→ work order <b>{c.cmms_work_order_id}</b> raised in the CMMS system of record</p>
      )}
    </div>
  );
}

function SignalTable({ c }: { c: Case }) {
  const signals: [string, SignalStats][] = Object.entries(c.evidence?.signal_context || {});
  if (!signals.length) return null;
  const breached = c.anomaly?.metric ?? c.evidence?.anomaly?.metric;
  return (
    <div className="card block">
      <h4>Signal context — what every signal did</h4>
      <div className="table-scroll">
        <table className="signals">
          <thead><tr><th>signal</th><th>mean</th><th>drift</th><th>volatility</th><th>range</th></tr></thead>
          <tbody>
            {signals.map(([metric, s]) => (
              <tr key={metric} className={metric === breached ? "breached" : ""}>
                <td>{metric}</td><td>{s.mean}</td>
                <td>{s.drift > 0 ? `+${s.drift}` : s.drift}</td>
                <td>{s.volatility_pct}%</td><td>{s.range}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        One signal breaches, but the pattern across all of them names the fault —
        these are the same numbers the agent was given.
      </p>
    </div>
  );
}

function CmmsPanel({ c, onChanged }: { c: Case; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (c.status === "pending_review" || !c.cmms_sync_status || c.cmms_sync_status === "not_applicable") return null;

  async function retry() {
    setBusy(true); setError("");
    try { await retryCmmsSync(c.id); onChanged(); }
    catch (e: any) { setError(e.message || "sync failed"); }
    finally { setBusy(false); }
  }

  return (
    <div className="card block">
      <h4>System of record (CMMS)</h4>
      {c.cmms_sync_status === "synced" ? (
        <div className="evidence-wo" style={{ borderLeftColor: "var(--p4)" }}>
          <span className="wo-id">Work order {c.cmms_work_order_id}</span> · status {c.cmms_status}
          <div style={{ color: "var(--text-muted)" }}>
            Approved decision written back over the CMMS adapter — human in the middle, both directions.
          </div>
        </div>
      ) : c.cmms_sync_status === "rejected" ? (
        <p style={{ color: "var(--p1)" }}>
          CMMS rejected the payload — a translation error on our side; a retry cannot succeed.
          The decision stands, audited.
        </p>
      ) : (
        <>
          <p style={{ color: "var(--p2)" }}>
            CMMS unreachable — the decision is recorded and audited; the work order has not synced yet.
          </p>
          <button className="btn" disabled={busy} onClick={retry}>Retry CMMS sync</button>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function DecisionBox({ c, onDecided }: { c: Case; onDecided: () => void }) {
  const session = typeof window !== "undefined" ? getSession() : null;
  const [reviewer, setReviewer] = useState(session?.reviewer || "");
  const [note, setNote] = useState("");
  const [editPriority, setEditPriority] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function decide(action: "approve" | "reject" | "edit") {
    setBusy(true); setError("");
    try {
      await decideCase(c.id, {
        action, reviewer, note,
        ...(action === "edit" && editPriority ? { priority: editPriority } : {}),
      });
      onDecided();
    } catch (e: any) { setError(e.message || "failed"); }
    finally { setBusy(false); }
  }

  return (
    <div className="card block decision">
      <h4>Planner decision — required</h4>
      <div className="row" style={{ marginBottom: 8 }}>
        <input className="input" style={{ flex: 1 }} placeholder="Your name (audited)"
               value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
        <select className="input" style={{ width: 140 }} value={editPriority}
                onChange={(e) => setEditPriority(e.target.value)}>
          <option value="">keep {c.priority}</option>
          {["P1", "P2", "P3", "P4"].map((p) => <option key={p} value={p}>override → {p}</option>)}
        </select>
      </div>
      <input className="input" style={{ marginBottom: 8 }} placeholder="Review note"
             value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="row">
        <button className="btn approve" disabled={busy || reviewer.length < 2}
                onClick={() => decide(editPriority ? "edit" : "approve")}>
          {editPriority ? "Approve with edits" : "Approve → raise work order"}
        </button>
        <button className="btn reject" disabled={busy || reviewer.length < 2}
                onClick={() => decide("reject")}>Reject</button>
      </div>
      {reviewer.length < 2 && <p className="hint">enter your name — every decision is attributed</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
