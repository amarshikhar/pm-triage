"use client";
import { useId, useState } from "react";

/** Full-size time-series chart, hand-rolled SVG (no chart library — a point in
 *  the defense pack). One series, a faint grid, a soft area fill, an emphasized
 *  endpoint, y-axis tick labels, x-axis time labels, and a crosshair tooltip.
 *  Responsive via viewBox; the parent controls width. */
export default function AxisChart({
  values, times, unit = "", label, threshold,
  height = 200,
}: {
  values: number[]; times: string[]; unit?: string; label?: string;
  threshold?: number; height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const uid = useId().replace(/:/g, "");
  const W = 640, H = height;
  const padL = 52, padR = 14, padT = 14, padB = 26;
  const plotW = W - padL - padR, plotH = H - padT - padB;

  if (values.length < 2) {
    return <div className="axis-empty" style={{ height }}>collecting readings…</div>;
  }

  const consider = threshold != null ? [...values, threshold] : values;
  let min = Math.min(...consider), max = Math.max(...consider);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.08; min -= pad; max += pad;

  const x = (i: number) => padL + (i / (values.length - 1)) * plotW;
  const y = (v: number) => padT + (1 - (v - min) / (max - min)) * plotH;

  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(values.length - 1).toFixed(1)},${(padT + plotH).toFixed(1)} L${padL},${(padT + plotH).toFixed(1)} Z`;

  // y ticks (4) and a sparse set of x ticks
  const yTicks = Array.from({ length: 4 }, (_, k) => min + ((max - min) * k) / 3);
  const xTickIdx = [0, Math.floor((values.length - 1) / 2), values.length - 1];
  const fmt = (v: number) => (Math.abs(v) >= 100 ? Math.round(v).toLocaleString()
    : Math.abs(v) >= 1 ? v.toFixed(1) : v.toFixed(3));

  return (
    <div className="axis-chart">
      {label && <div className="axis-label">{label}{unit && <span className="axis-unit"> · {unit}</span>}</div>}
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label ?? "signal"} over time`}
           preserveAspectRatio="none" style={{ width: "100%", height: "auto", display: "block" }}
           onMouseLeave={() => setHover(null)}
           onMouseMove={(e) => {
             const r = e.currentTarget.getBoundingClientRect();
             const i = Math.round(((e.clientX - r.left) / r.width * W - padL) / plotW * (values.length - 1));
             setHover(Math.max(0, Math.min(values.length - 1, i)));
           }}>
        <defs>
          <linearGradient id={`g${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--series-1)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--series-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {yTicks.map((t, k) => (
          <g key={k}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth="1" opacity="0.5" />
            <text x={padL - 8} y={y(t) + 3.5} textAnchor="end" className="axis-tick">{fmt(t)}</text>
          </g>
        ))}
        {xTickIdx.map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === values.length - 1 ? "end" : "middle"}
                className="axis-tick">{times[i] ?? ""}</text>
        ))}
        {threshold != null && (
          <line x1={padL} x2={W - padR} y1={y(threshold)} y2={y(threshold)}
                stroke="var(--p1)" strokeWidth="1.5" strokeDasharray="4 3" opacity="0.75" />
        )}
        <path d={area} fill={`url(#g${uid})`} />
        <path d={line} fill="none" stroke="var(--series-1)" strokeWidth="2" strokeLinejoin="round" />
        <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r="3.5"
                fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth="2" />
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={padT} y2={padT + plotH} stroke="var(--text-muted)" strokeWidth="1" opacity="0.5" />
            <circle cx={x(hover)} cy={y(values[hover])} r="4" fill="var(--series-1)" stroke="var(--surface-0)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hover != null && (
        <div className="axis-tip">
          <b>{fmt(values[hover])}</b>{unit && ` ${unit}`} · {times[hover] ?? ""}
        </div>
      )}
    </div>
  );
}
