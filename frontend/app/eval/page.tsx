"use client";
import { useEffect, useState } from "react";
import { EvalBundle, EvalModeReport, EvalReport, getEvalReport } from "@/lib/api";
import syntheticStatic from "./reports/synthetic.json";
import realStatic from "./reports/real.json";

// The committed CI-measured reports, bundled at build time. They are the same
// artifacts the backend serves at /api/eval-report, so the Evaluation page can
// render the benchmark even when the (free-tier) backend is asleep, stale, or
// hasn't yet picked up a fresh report. A live API response overrides them.
const STATIC_BUNDLE: EvalBundle = {
  synthetic: syntheticStatic as unknown as EvalReport,
  real: realStatic as unknown as EvalReport,
};

/** A report "has data" only if at least one mode actually produced results. */
function hasReports(r?: EvalReport): boolean {
  return !!(r?.reports && (r.reports.mock || r.reports.live));
}

function reportTimestamp(value: string): string {
  return new Date(value).toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
}

export default function EvalPage() {
  const [bundle, setBundle] = useState<EvalBundle>(STATIC_BUNDLE);
  const [which, setWhich] = useState<"synthetic" | "real">("synthetic");

  useEffect(() => {
    // Prefer the live backend, but only where it actually returned data; fall
    // back to the bundled static copy per-key so one missing side never blanks
    // the whole page.
    getEvalReport()
      .then((live) => setBundle((prev) => ({
        synthetic: hasReports(live.synthetic) ? live.synthetic : prev.synthetic,
        real: hasReports(live.real) ? live.real : prev.real,
      })))
      .catch(() => { /* keep the static bundle */ });
  }, []);

  const report: EvalReport | undefined = bundle[which];
  const mock = report?.reports?.mock;
  const live = report?.reports?.live;
  const primary = live || mock;

  return (
    <main className="page narrow">
      <div className="section-title">Evaluation — does the agent actually work?</div>
      <p className="eval-intro">
        The simulator and the SKAB/CWRU datasets already know which fault is present, so every anomaly is a
        free labelled test. This harness replays them through the <b>real</b> pipeline (real detector,
        real agent tool-loop) and scores the case that comes out — never a reimplementation.
      </p>

      <div className="tabs">
        <button className={`tab ${which === "synthetic" ? "active" : ""}`} onClick={() => setWhich("synthetic")}>
          Synthetic faults
        </button>
        <button className={`tab ${which === "real" ? "active" : ""}`} onClick={() => setWhich("real")}
                disabled={!hasReports(bundle.real)}>
          Real testbeds
        </button>
      </div>

      {which === "real" && (
        <div className="eval-note">
          <b>What does this real-data result now prove?</b> The suite contains five SKAB pump
          recordings plus three CWRU bearing recordings. Detection sees all eight. A trained Extra
          Trees layer is used only for the overlapping SKAB suction/discharge pair; learned novelty
          detection or an unsupported signal roster makes that narrow model abstain.
          <ul>
            <li><b>Result:</b> the hybrid classifier is correct on 7/8 overall, speaks on 7/8,
              and is 7/7 correct when it speaks. It abstains on the remaining cavitation run.</li>
            <li><b>Limit:</b> n=8 across two laboratory testbeds is still small. The three CWRU
              sequences concatenate real healthy and faulty steady-state frames; they are not natural
              run-to-failure transitions. CWRU commercial/redistribution terms also need confirmation.</li>
          </ul>
          So the correct claim is “safe improvement on a frozen development benchmark,” not
          “production accuracy is solved.”
        </div>
      )}

      {!primary ? (
        <div className="empty">This report hasn’t been generated yet. Run the eval workflow.</div>
      ) : (
        <>
          <div className="stat-row">
            <Stat n={`${primary.detection_rate_pct}%`} l="detection rate" good />
            {primary.classifier && <Stat n={`${primary.classifier.top1_accuracy_pct}%`} l="hybrid classifier top-1" />}
            {mock && <Stat n={`${mock.accuracy.top1_text_pct}%`} l="mock top-1 accuracy" />}
            {live && <Stat n={`${live.accuracy.top1_text_pct}%`} l={`live top-1 (${live.llm_model || "LLM"})`} accent />}
            {live && <Stat n={live.ece.toFixed(3)} l="calibration error (ECE)" accent />}
            {primary.replay && <Stat n={`${primary.replay.in_labelled_window_pct}%`} l="fired in labelled window" />}
          </div>

          {primary.classifier && (
            <Panel title="Agent vs rules + trained classifier">
              <p className="hint" style={{ marginTop: 0 }}>
                Classifier top-1 counts abstentions as not correct. Coverage and selective accuracy show
                how often it speaks, and how often it is right when it does.
              </p>
              <div className="table-scroll"><table className="etable">
                <thead><tr><th>method</th><th>top-1</th><th>coverage</th><th>selective accuracy</th></tr></thead>
                <tbody>
                  <tr>
                    <td>agent ({primary.llm_mode})</td>
                    <td className="tnum">{primary.accuracy.top1_text_pct}%</td>
                    <td className="tnum">{primary.agent_selection?.coverage_pct ?? 100}%</td>
                    <td className="tnum">{primary.agent_selection?.selective_accuracy_pct ?? "—"}{primary.agent_selection?.selective_accuracy_pct != null ? "%" : ""}</td>
                  </tr>
                  <tr>
                    <td><b>rules + trained hard-fault layer</b></td>
                    <td className="tnum"><b>{primary.classifier.top1_accuracy_pct}%</b></td>
                    <td className="tnum">{primary.classifier.coverage_pct}%</td>
                    <td className="tnum">{primary.classifier.selective_accuracy_pct ?? "—"}{primary.classifier.selective_accuracy_pct != null ? "%" : ""}</td>
                  </tr>
                  <tr>
                    <td>mock (scripted baseline)</td>
                    <td className="tnum">{mock?.accuracy.top1_text_pct ?? primary.comparison?.mock_top1_pct ?? "—"}{mock || primary.comparison?.mock_top1_pct != null ? "%" : ""}</td>
                    <td className="tnum">100%</td><td>—</td>
                  </tr>
                </tbody>
              </table></div>
            </Panel>
          )}

          {mock && live && (
            <Panel title="What the LLM buys over a scripted baseline">
              <div className="table-scroll"><table className="etable">
                <thead><tr><th>metric</th><th>mock (scripted)</th><th>live ({live.llm_model || "LLM"})</th><th>delta</th></tr></thead>
                <tbody>
                  <Row label="top-1 accuracy" a={mock.accuracy.top1_text_pct} b={live.accuracy.top1_text_pct} pct />
                  <Row label="hit@any" a={mock.accuracy.hit_any_pct} b={live.accuracy.hit_any_pct} pct />
                  <Row label="ECE (lower better)" a={mock.ece} b={live.ece} invert />
                </tbody>
              </table></div>
            </Panel>
          )}

          <Panel title={`Operational confusion — ${primary.llm_mode} (truth → prediction or abstention)`}>
            <p className="hint" style={{ marginTop: 0 }}>
              This applies the confidence gate: an uncertain case is shown as “abstained” even if its draft named a cause.
            </p>
            <Confusion c={primary.operational_confusion || primary.confusion} />
          </Panel>

          {primary.classifier_confusion && (
            <Panel title="Hybrid classifier confusion (truth → predicted)">
              <p className="hint" style={{ marginTop: 0 }}>
                “Abstained” is deliberate: rules and the trained/OOD gates did not have enough supported evidence.
              </p>
              <Confusion c={primary.classifier_confusion} />
            </Panel>
          )}

          <Panel title="Per fault class">
            <div className="table-scroll"><table className="etable">
              <thead><tr><th>class</th><th>n</th><th>agent top-1</th><th>classifier</th><th>hit@any</th><th>conf</th></tr></thead>
              <tbody>
                {Object.entries(primary.per_class).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k.replaceAll("_", " ")}</td><td className="tnum">{v.n}</td>
                    <td className="tnum">{v.top1_text_pct}%</td>
                    <td className="tnum">{v.classifier_top1_pct != null ? `${v.classifier_top1_pct}%` : "—"}</td>
                    <td className="tnum">{v.hit_any_pct}%</td>
                    <td className="tnum">{v.mean_confidence.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </Panel>

          {primary.calibration?.length > 0 && (
            <Panel title="Calibration — is the confidence trustworthy?">
              <p className="hint" style={{ marginTop: 0 }}>
                If it says 75%, is it right ~75% of the time? Gap near 0 = trustworthy.
              </p>
              <div className="table-scroll"><table className="etable">
                <thead><tr><th>confidence band</th><th>n</th><th>states</th><th>actual</th><th>gap</th></tr></thead>
                <tbody>
                  {primary.calibration.map((c) => (
                    <tr key={c.bucket}>
                      <td className="tnum">{c.bucket}</td><td className="tnum">{c.n}</td>
                      <td className="tnum">{c.mean_confidence_pct}%</td><td className="tnum">{c.accuracy_pct}%</td>
                      <td className={`tnum ${Math.abs(c.gap_pct) <= 10 ? "good-t" : "warn-t"}`}>
                        {c.gap_pct > 0 ? "+" : ""}{c.gap_pct}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            </Panel>
          )}

          <p className="hint">
            The measuring tape is itself checked: two independent scorers (free-text vs cited work-order ids)
            share no code and agree {primary.scorer_agreement_pct}% of the time when both return a class
            (coverage {primary.scorer_coverage_pct ?? "—"}%, n={primary.scorer_agreement_n}).
            {report && <> Report seed {report.seed}, generated {reportTimestamp(report.generated_at)}.</>}
          </p>
        </>
      )}
    </main>
  );
}

function Stat({ n, l, good, accent }: { n: string; l: string; good?: boolean; accent?: boolean }) {
  return (
    <div className={`estat ${good ? "good" : ""} ${accent ? "accent" : ""}`}>
      <div className="estat-n tnum">{n}</div><div className="estat-l">{l}</div>
    </div>
  );
}
function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="card block"><h4>{title}</h4>{children}</div>;
}
function Row({ label, a, b, pct, invert }: { label: string; a: number; b: number; pct?: boolean; invert?: boolean }) {
  const d = b - a;
  const better = invert ? d < 0 : d > 0;
  return (
    <tr>
      <td>{label}</td>
      <td className="tnum">{a}{pct ? "%" : ""}</td>
      <td className="tnum"><b>{b}{pct ? "%" : ""}</b></td>
      <td className={`tnum ${better ? "good-t" : d === 0 ? "" : "warn-t"}`}>
        {d > 0 ? "+" : ""}{pct ? d.toFixed(1) + "pp" : d.toFixed(3)}
      </td>
    </tr>
  );
}
function Confusion({ c }: { c: Record<string, Record<string, number>> }) {
  const classes = Object.keys(c);
  const preds = Array.from(new Set(classes.flatMap((t) => Object.keys(c[t]))));
  const cols = Array.from(new Set([...classes, ...preds]));
  const max = Math.max(1, ...classes.flatMap((t) => Object.values(c[t])));
  const short = (s: string) => s.split("_").map((w) => w.slice(0, 4)).join(".");
  return (
    <div className="table-scroll">
      <table className="confusion">
        <thead>
          <tr><th className="corner">truth ＼ pred</th>{cols.map((p) => <th key={p} title={p}>{short(p)}</th>)}</tr>
        </thead>
        <tbody>
          {classes.map((t) => (
            <tr key={t}>
              <th title={t}>{t.replaceAll("_", " ")}</th>
              {cols.map((p) => {
                const v = c[t]?.[p] || 0;
                const diag = t === p;
                const alpha = v === 0 ? 0 : 0.15 + 0.6 * (v / max);
                return (
                  <td key={p} className={`cm ${diag ? "diag" : ""}`}
                      style={{ background: v ? `color-mix(in srgb, var(${diag ? "--p4" : "--p1"}) ${Math.round(alpha * 100)}%, transparent)` : "transparent" }}>
                    {v || ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
