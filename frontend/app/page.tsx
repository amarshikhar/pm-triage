"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Case, Machine, getCases, getFaults, getMachines, injectFault } from "@/lib/api";
import MachineCard from "@/components/MachineCard";

const POLL_MS = 3500;

export default function FleetPage() {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [pending, setPending] = useState<Case[]>([]);
  const [faults, setFaults] = useState<{ available: string[]; replay: Record<string, string[]> }>({ available: [], replay: {} });
  const [injMachine, setInjMachine] = useState("CMP-01");
  const [injFault, setInjFault] = useState("");
  const [injecting, setInjecting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [ms, cs] = await Promise.all([getMachines(), getCases("pending_review")]);
      setMachines(ms); setPending(cs);
    } catch { /* chrome shows offline */ }
  }, []);

  useEffect(() => {
    refresh();
    getFaults().then((f) => setFaults({ available: f.available, replay: f.replay })).catch(() => {});
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const selected = machines.find((m) => m.id === injMachine);
  const options = selected?.source === "replay"
    ? (faults.replay[injMachine] || [])
    : faults.available;
  const fault = options.includes(injFault) ? injFault : options[0] || "";

  async function inject() {
    if (!fault) return;
    setInjecting(true);
    try { await injectFault(injMachine, fault); await refresh(); }
    catch { /* 401 handled by chrome */ }
    finally { setInjecting(false); }
  }

  return (
    <main className="page">
      {pending.length > 0 && (
        <Link href="/cases" className="pending-strip">
          <span className="badge P2">{pending.length}</span>
          case{pending.length > 1 ? "s" : ""} awaiting human review — open the queue →
        </Link>
      )}

      <div className="section-head">
        <div className="section-title">Fleet — live telemetry</div>
        <div className="row inject-bar">
          <select className="input" value={injMachine} onChange={(e) => setInjMachine(e.target.value)}>
            {machines.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}{m.source === "replay" ? " (real data)" : ""}
              </option>
            ))}
          </select>
          <select className="input" value={fault} onChange={(e) => setInjFault(e.target.value)}>
            {options.map((f) => <option key={f}>{f}</option>)}
          </select>
          <button className="btn" disabled={injecting || !fault} onClick={inject}
                  title={selected?.source === "replay"
                    ? "Cues the real recording of this fault just before its labelled window — nothing is synthesized."
                    : "Ramps a synthetic fault pattern onto this machine's stream."}>
            {selected?.source === "replay" ? "Cue real fault" : "Inject fault"}
          </button>
        </div>
      </div>

      <div className="grid">
        {machines.map((m) => <MachineCard key={m.id} m={m} />)}
        {machines.length === 0 && <div className="empty">Connecting to the fleet…</div>}
      </div>
    </main>
  );
}
