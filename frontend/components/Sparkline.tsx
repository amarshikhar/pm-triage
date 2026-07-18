"use client";
import { useState } from "react";

/** Single-series 2px sparkline with hover tooltip; the metric name is the title,
 * so no legend is needed. Ink stays in text tokens; the line carries identity. */
export default function Sparkline({
  values, labels, width = 110, height = 30, threshold, fluid = false,
}: {
  values: number[]; labels?: string[]; width?: number; height?: number;
  threshold?: number; fluid?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (values.length < 2) return <svg width={width} height={height} aria-hidden />;

  const all = threshold != null ? [...values, threshold] : values;
  const min = Math.min(...all), max = Math.max(...all);
  const span = max - min || 1;
  const x = (i: number) => (i / (values.length - 1)) * (width - 4) + 2;
  const y = (v: number) => height - 3 - ((v - min) / span) * (height - 6);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");

  return (
    <span style={{ position: "relative", display: fluid ? "block" : "inline-block" }}>
      <svg
        {...(fluid
          ? { viewBox: `0 0 ${width} ${height}`, style: { width: "100%", height: "auto", display: "block" } }
          : { width, height })}
        role="img" aria-label="recent trend"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((e.clientX - rect.left) / rect.width) * (values.length - 1));
          setHover(Math.max(0, Math.min(values.length - 1, i)));
        }}
      >
        {threshold != null && (
          <line x1={0} x2={width} y1={y(threshold)} y2={y(threshold)}
                stroke="var(--p1)" strokeWidth={1} strokeDasharray="3 3" opacity={0.7} />
        )}
        <path d={d} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" />
        {hover != null && (
          <circle cx={x(hover)} cy={y(values[hover])} r={3.5}
                  fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
        )}
      </svg>
      {hover != null && (
        <span className="spark-tip" style={{ left: Math.min(x(hover), width - 60), top: -26 }}>
          {values[hover]}{labels?.[hover] ? ` · ${labels[hover]}` : ""}
        </span>
      )}
    </span>
  );
}
