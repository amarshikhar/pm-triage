"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Case, getCases } from "@/lib/api";

export default function CasesPage() {
  const [cases, setCases] = useState<Case[]>([]);
  const [tab, setTab] = useState<"queue" | "resolved">("queue");

  const refresh = useCallback(() => getCases().then(setCases).catch(() => {}), []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const pending = cases.filter((c) => c.status === "pending_review");
  const resolved = cases.filter((c) => c.status !== "pending_review");
  const list = tab === "queue" ? pending : resolved;

  return (
    <main className="page narrow">
      <div className="tabs">
        <button className={`tab ${tab === "queue" ? "active" : ""}`} onClick={() => setTab("queue")}>
          Awaiting review ({pending.length})
        </button>
        <button className={`tab ${tab === "resolved" ? "active" : ""}`} onClick={() => setTab("resolved")}>
          Resolved ({resolved.length})
        </button>
      </div>

      {list.length === 0 && (
        <div className="empty">
          {tab === "queue"
            ? "No cases awaiting review. Inject a fault from the Fleet page to see the pipeline run."
            : "Nothing resolved yet."}
        </div>
      )}
      {list.map((c) => (
        <Link key={c.id} href={`/cases/${c.id}`} className="queue-item">
          <span className={`badge ${c.priority}`}>{c.priority}</span>
          <span>
            <span className="title">{c.machine_id}: {c.root_cause.slice(0, 80)}{c.root_cause.length > 80 ? "…" : ""}</span>
            <span className="meta">
              #{c.id} · {new Date(c.created_ts).toLocaleString()} · confidence {(c.confidence * 100).toFixed(0)}%
              · {c.llm_mode === "live" ? "live LLM" : "mock"}
              {c.status !== "pending_review" && <> · {c.status.replaceAll("_", " ")} by {c.reviewer}</>}
              {c.cmms_work_order_id && <> · WO {c.cmms_work_order_id}</>}
            </span>
          </span>
          <span className="chev">›</span>
        </Link>
      ))}
    </main>
  );
}
