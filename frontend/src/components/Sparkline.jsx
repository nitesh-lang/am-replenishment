import React from "react";

/**
 * Inline 12-week sparkline.
 *
 * data: number[]  — units sold per week, chronological
 * trend: "RISING" | "SURGING" | "STABLE" | "COOLING" — derived from data
 */
export function Sparkline({ data = [], width = 110, height = 28, className = "" }) {
  if (!data || data.length === 0) return <span className="text-ink-300">—</span>;

  const max = Math.max(...data, 1);
  const stepX = width / Math.max(data.length - 1, 1);
  const pad = 3;

  const points = data
    .map((v, i) => {
      const x = i * stepX;
      const y = pad + (height - pad * 2) * (1 - v / max);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const trend = classifyTrend(data);
  const color = TREND_COLOR[trend];
  const last = data[data.length - 1] ?? 0;
  const lastY = pad + (height - pad * 2) * (1 - last / max);

  return (
    <div className={className}>
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} preserveAspectRatio="none" className="block">
        <polyline fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" points={points} />
        <circle cx={(data.length - 1) * stepX} cy={lastY} r="2.2" fill={color} />
      </svg>
      <div className={`text-[9px] font-semibold tracking-wide ${TREND_TEXT[trend]}`}>{TREND_LABEL[trend]}</div>
    </div>
  );
}

export function classifyTrend(data) {
  if (!data || data.length < 4) return "STABLE";
  const recent = data.slice(-4);
  const earlier = data.slice(0, -4);
  const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
  const earlierAvg = earlier.length ? earlier.reduce((a, b) => a + b, 0) / earlier.length : recentAvg;
  if (earlierAvg === 0 && recentAvg === 0) return "STABLE";
  if (earlierAvg === 0) return recentAvg > 0 ? "SURGING" : "STABLE";
  const ratio = recentAvg / earlierAvg;
  if (ratio >= 1.5) return "SURGING";
  if (ratio >= 1.15) return "RISING";
  if (ratio <= 0.7) return "COOLING";
  return "STABLE";
}

const TREND_COLOR = {
  RISING:  "#6366f1",
  SURGING: "#ef4444",
  STABLE:  "#22c55e",
  COOLING: "#f59e0b",
};
const TREND_TEXT = {
  RISING:  "text-indigo-700",
  SURGING: "text-red-700",
  STABLE:  "text-emerald-700",
  COOLING: "text-amber-700",
};
const TREND_LABEL = {
  RISING:  "RISING ↑",
  SURGING: "SURGING ↑↑",
  STABLE:  "STABLE",
  COOLING: "COOLING ↓",
};
