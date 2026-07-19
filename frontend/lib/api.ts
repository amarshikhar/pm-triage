export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- session (crew password + reviewer name) --------------------------------
// Token + name live in localStorage; every mutating request carries the token.
// A 401 dispatches "pm-auth-required" so the chrome can raise the login modal.

export type Session = { token: string; reviewer: string };

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("pm-triage-session");
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function setSession(s: Session | null) {
  if (s) localStorage.setItem("pm-triage-session", JSON.stringify(s));
  else localStorage.removeItem("pm-triage-session");
  window.dispatchEvent(new Event("pm-auth-changed"));
}

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getSession()?.token;
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (res.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event("pm-auth-required"));
  }
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || res.statusText);
  return res.json();
}

// --- types ------------------------------------------------------------------

/** One telemetry instant: ts plus the machine's own signal keys (dynamic). */
export type Reading = { ts: string } & Record<string, any>;
export type SignalDef = { key: string; name: string; unit: string };
export type Machine = {
  id: string; name: string; type: string; location: string; criticality: number;
  source: "simulated" | "replay";
  signals: SignalDef[];
  dataset: { dataset?: string; url?: string; license?: string };
  fault_active: boolean; pending_cases: number; latest: Reading | null;
};
/** Per-metric statistics the detector computes over the detection window and
 *  hands to the agent — reported for every signal, not just the one that
 *  breached, because the fault is identified by the pattern across them. */
export type SignalStats = {
  mean: number; drift: number; volatility_pct: number; range: number; n: number;
};
export type SignatureAnalysis = {
  predicted: string | null; confidence: number; ranked: [string, number][];
  evidence: string[]; abstain: boolean; agent_agreement?: boolean | null;
};
export type Case = {
  id: number; anomaly_id: number; machine_id: string; created_ts: string; status: string;
  root_cause: string; confidence: number; priority: "P1" | "P2" | "P3" | "P4";
  priority_breakdown: any; recommended_actions: string[]; explanation: string;
  llm_mode: string; llm_model: string; reviewer: string; review_note: string; reviewed_ts: string;
  // Write-back to the CMMS system of record, populated after a human approves.
  cmms_work_order_id: string; cmms_status: string; cmms_sync_status: string;
  evidence?: any; trace?: any[]; anomaly?: any;
};
/** A work order as the CMMS (system of record) stores it — its own schema,
 *  which the triage side reaches only over HTTP through the adapter. */
export type WorkOrder = {
  order_id: string; external_ref: string; equipment_id: string; functional_location: string;
  notification_type: string; priority_code: number; priority_text: string;
  damage_code: string; damage_text: string; short_text: string; long_text: string;
  reported_by: string; est_downtime_hours: number; est_cost_exposure: number;
  system_status: string; created_at: string;
};
export type AuditEvent = {
  id: number; ts: string; actor: string; event_type: string;
  entity: string; entity_id: string; detail: any;
};
/** The evaluation harness output — what the /eval page renders. */
export type EvalModeReport = {
  n_trials: number; n_scored: number; n_detector_missed: number; n_agent_errors: number;
  llm_mode: string; llm_model: string; detection_rate_pct: number;
  accuracy: { top1_text_pct: number; top1_citation_pct: number; classifier_top1_pct?: number; hit_any_pct: number; hedged_pct: number; unclassifiable_pct: number; abstained_pct?: number };
  scorer_agreement_pct: number; scorer_agreement_n: number;
  per_class: Record<string, { n: number; top1_text_pct: number; classifier_top1_pct?: number; hit_any_pct: number; mean_confidence: number; mean_ticks_to_detect: number }>;
  confusion: Record<string, Record<string, number>>;
  classifier_confusion?: Record<string, Record<string, number>>;
  classifier?: {
    top1_accuracy_pct: number; coverage_pct: number;
    selective_accuracy_pct: number | null; abstained_pct: number;
    per_class: Record<string, { n: number; top1_pct: number; coverage_pct: number; abstained_pct: number }>;
  };
  comparison?: { agent_top1_pct: number; classifier_top1_pct: number; mock_top1_pct: number | null };
  calibration: { bucket: string; n: number; mean_confidence_pct: number; accuracy_pct: number; gap_pct: number }[];
  ece: number; latency_s: { mean: number; p50: number; max: number } | any;
  replay?: { detection_rate_pct: number; in_labelled_window_pct: number };
};
export type EvalReport = {
  generated_at: string; seed: number; trials_requested: number;
  reports: { mock?: EvalModeReport; live?: EvalModeReport };
};
export type EvalBundle = { synthetic?: EvalReport; real?: EvalReport };

export type LlmStatus = {
  mode: "live" | "mock"; model: string; runtime_override: string | null;
  key_configured: boolean;
  budget: { daily_cap: number; used_today: number; remaining: number };
};

// --- calls ------------------------------------------------------------------

export const getHealth = () => j<any>("/api/health");
export const getMachines = () => j<Machine[]>("/api/machines");
export const getTelemetry = (id: string, n = 60) => j<Reading[]>(`/api/machines/${id}/telemetry?n=${n}`);
export const getCases = (status?: string) => j<Case[]>(`/api/cases${status ? `?status=${status}` : ""}`);
export const getCase = (id: number) => j<Case>(`/api/cases/${id}`);
export const getAudit = (machine?: string) =>
  j<AuditEvent[]>(`/api/audit?limit=150${machine ? `&machine=${machine}` : ""}`);
export const getEvalReport = () => j<EvalBundle>("/api/eval-report");
export const getFaults = () =>
  j<{ available: string[]; replay: Record<string, string[]>; active: Record<string, string> }>("/api/simulate/faults");
export const injectFault = (machine_id: string, fault: string) =>
  j("/api/simulate/inject", { method: "POST", body: JSON.stringify({ machine_id, fault }) });
export const decideCase = (
  id: number,
  body: { action: "approve" | "reject" | "edit"; reviewer: string; note?: string; priority?: string; recommended_actions?: string[] },
) => j<Case>(`/api/cases/${id}/decision`, { method: "POST", body: JSON.stringify(body) });
export const retryCmmsSync = (id: number) =>
  j<Case>(`/api/cases/${id}/sync-cmms`, { method: "POST" });
// The CMMS is a separate service mounted at /cmms; the UI reads it directly to
// prove the work order really landed in the system of record.
export const getWorkOrders = () => j<WorkOrder[]>("/cmms/api/workorders");

export const login = (password: string, reviewer: string) =>
  j<{ token: string; reviewer: string; auth_enabled: boolean }>(
    "/api/auth/login", { method: "POST", body: JSON.stringify({ password, reviewer }) });
export const getLlm = () => j<LlmStatus>("/api/llm");
export const setLlmMode = (mode: "live" | "mock" | "auto") =>
  j<LlmStatus>("/api/llm/mode", { method: "POST", body: JSON.stringify({ mode }) });
