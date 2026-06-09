import React from "react";

/**
 * In-table expanded detail panel.
 * Shows 12-week bar chart with the 4-wk window highlighted,
 * channel split (when available), recent PO, similar SKUs.
 */
export function DetailRow({ row, colSpan, allRows }) {
  const weeks = row.weekly_window || [];
  const sales = row.weekly_sales  || [];
  const max = Math.max(...sales, 1);
  const last4Start = Math.max(0, sales.length - 4);

  const windowAvg = sales.length ? (sales.reduce((a, b) => a + b, 0) / sales.length).toFixed(1) : "0.0";
  const last4Avg  = sales.length >= 4
    ? (sales.slice(-4).reduce((a, b) => a + b, 0) / 4).toFixed(1)
    : windowAvg;
  const deltaPct  = Number(windowAvg) > 0
    ? Math.round(((Number(last4Avg) - Number(windowAvg)) / Number(windowAvg)) * 100)
    : 0;

  // Similar SKUs: same category, top 3 by velocity, excluding current row
  const similar = (allRows || [])
    .filter(r => r.category && r.category === row.category && r.sku !== row.sku)
    .sort((a, b) => (b.sales_velocity || 0) - (a.sales_velocity || 0))
    .slice(0, 3);

  // Chart geometry
  const W = 360, H = 110;
  const barW = (W - 12) / Math.max(weeks.length, 1) - 4;

  return (
    <tr className="bg-indigo-50/20">
      <td colSpan={colSpan} className="!p-0">
        <div className="px-6 py-5 bg-gradient-to-b from-indigo-50/40 to-white border-l-4 border-indigo-500 grid grid-cols-12 gap-5">

          {/* 12-week chart */}
          <div className="col-span-5">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
              12-Week Sales · {row.model}
            </div>
            <div className="bg-white rounded-md border border-slate-200 p-3">
              <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[110px]">
                {/* Grid */}
                <line x1="0" y1="20" x2={W} y2="20" stroke="#f1f5f9" />
                <line x1="0" y1="55" x2={W} y2="55" stroke="#f1f5f9" />
                <line x1="0" y1="90" x2={W} y2="90" stroke="#f1f5f9" />
                {/* 4-wk window highlight */}
                {sales.length >= 4 && (() => {
                  const xStart = 6 + (barW + 4) * last4Start;
                  const xEnd   = 6 + (barW + 4) * sales.length;
                  return (
                    <>
                      <rect x={xStart - 4} y="0" width={xEnd - xStart} height={H} fill="#eef2ff" opacity="0.7" />
                      <text x={(xStart + xEnd) / 2 - 4} y="12" fontSize="9" fill="#4f46e5" textAnchor="middle" fontWeight="600">
                        4wk window
                      </text>
                    </>
                  );
                })()}
                {/* Bars */}
                {sales.map((v, i) => {
                  const x = 6 + i * (barW + 4);
                  const h = (90 / max) * v;
                  const y = 90 - h;
                  const inWindow = i >= last4Start;
                  return <rect key={i} x={x} y={y} width={barW} height={h || 0.5} rx="2" fill={inWindow ? "#4338ca" : "#6366f1"} />;
                })}
                {/* Week labels */}
                {weeks.map((w, i) => (
                  <text key={i} x={6 + i * (barW + 4) + barW / 2} y="105" fontSize="8" fill="#94a3b8" textAnchor="middle" fontFamily="JetBrains Mono">
                    W{w}
                  </text>
                ))}
              </svg>
              <div className="flex justify-between items-center mt-2 pt-2 border-t border-slate-100 text-xs">
                <div><span className="text-slate-500">Window avg:</span> <span className="font-semibold tabular-nums">{windowAvg}</span></div>
                <div><span className="text-slate-500">4-wk avg:</span> <span className="font-semibold tabular-nums text-indigo-700">{last4Avg}</span></div>
                <div>
                  <span className="text-slate-500">Δ:</span>{" "}
                  <span className={`font-semibold tabular-nums ${deltaPct >= 0 ? "text-emerald-700" : "text-amber-700"}`}>
                    {deltaPct > 0 ? "+" : ""}{deltaPct}%
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Inventory snapshot */}
          <div className="col-span-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Inventory Snapshot</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <Row label="Amazon FBA"     val={row.amazon_inventory} />
              <Row label="Inbound"        val={row.inbound_inventory} />
              <Row label="Mother WH"      val={row.ampm_inventory} accent />
              <Row label="B2B"            val={row.b2b_inventory} />
              <Row label="Required (8wk)" val={row.required_units} />
              <Row label="Shortfall"      val={row.warehouse_shortfall} danger={row.warehouse_shortfall > 0} />
            </div>
          </div>

          {/* Velocity comparison */}
          <div className="col-span-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Velocity</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <Row label="Window avg"   val={row.window_velocity} />
              <Row label="4-wk avg"     val={row.last_4_velocity} accent />
              <Row label="Used (max)"   val={row.sales_velocity} />
              <div className="pt-1 border-t border-slate-100">
                <span className="text-slate-500">Basis: </span>
                <span className={`font-semibold ${row.velocity_basis === "4wk" ? "text-indigo-700" : "text-slate-700"}`}>
                  {row.velocity_basis === "4wk" ? "4-week" : "Window"}
                </span>
              </div>
            </div>
          </div>

          {/* Similar SKUs */}
          <div className="col-span-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Similar (Category)</div>
            <div className="space-y-1.5">
              {similar.length === 0 && (
                <div className="text-xs text-slate-400 italic">No similar SKUs</div>
              )}
              {similar.map(s => (
                <div key={s.sku} className="bg-white rounded border border-slate-200 px-2 py-1.5 text-xs flex justify-between">
                  <span className="font-medium truncate" title={s.model}>{s.model}</span>
                  <span className="font-mono text-slate-500 tabular-nums">{s.sales_velocity}/wk</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

function Row({ label, val, accent, danger }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={`font-mono tabular-nums font-semibold ${
        danger ? "text-red-700" :
        accent ? "text-indigo-700" :
        "text-slate-900"
      }`}>
        {val ?? 0}
      </span>
    </div>
  );
}
