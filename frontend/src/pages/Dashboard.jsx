import { useEffect, useMemo, useState, useCallback } from "react";
import { getReplenishment, getFCFinal } from "../api/replenishment";

/* ============================================================
   CONSTANTS
============================================================ */
const ACCOUNTS = ["NEXLEV", "VIOMI", "AUDIO ARRAY", "WHITE MULBERRY"];
const ACCOUNT_FC_MAP = {
  "NEXLEV": "Nexlev",
  "VIOMI": "Viomi",
  "AUDIO ARRAY": "Audio Array",
  "WHITE MULBERRY": "White Mulberry",
};

const SALES_WINDOW = 4;
const REPLENISH_WEEKS = 8;

/* ============================================================
   HELPERS
============================================================ */
function weeksOfCover(amazonInv, velocity) {
  if (!velocity || velocity === 0) return 99;
  return amazonInv / velocity;
}

function coverColor(woc) {
  if (woc < 1) return { bg: "bg-red-500", text: "text-red-500", light: "bg-red-50 border-red-200", label: "CRITICAL" };
  if (woc < REPLENISH_WEEKS) return { bg: "bg-amber-400", text: "text-amber-500", light: "bg-amber-50 border-amber-200", label: "LOW COVER" };
  return { bg: "bg-emerald-500", text: "text-emerald-500", light: "bg-emerald-50 border-emerald-200", label: "HEALTHY" };
}

function fmt(n) {
  if (n === null || n === undefined) return "—";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return Math.round(n).toString();
}

function pct(a, b) {
  if (!b || b === 0) return 0;
  return Math.min(100, Math.round((a / b) * 100));
}

/* ============================================================
   SUB-COMPONENTS
============================================================ */

function Pulse({ color = "bg-red-500" }) {
  return (
    <span className="relative flex h-2.5 w-2.5">
      <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${color} opacity-50`} />
      <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${color}`} />
    </span>
  );
}

function StatCard({ label, value, sub, accent = "slate", icon, pulse }) {
  const accents = {
    red: "from-red-500/10 to-red-500/5 border-red-200",
    amber: "from-amber-500/10 to-amber-500/5 border-amber-200",
    emerald: "from-emerald-500/10 to-emerald-500/5 border-emerald-200",
    blue: "from-blue-500/10 to-blue-500/5 border-blue-200",
    slate: "from-slate-100 to-slate-50 border-slate-200",
  };
  const textAccents = {
    red: "text-red-600",
    amber: "text-amber-600",
    emerald: "text-emerald-600",
    blue: "text-blue-600",
    slate: "text-slate-800",
  };

  return (
    <div className={`rounded-2xl border bg-gradient-to-br ${accents[accent]} p-5 flex flex-col gap-1`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">{label}</span>
        <div className="flex items-center gap-2">
          {pulse && <Pulse color={accent === "red" ? "bg-red-500" : accent === "amber" ? "bg-amber-400" : "bg-emerald-500"} />}
          {icon && <span className="text-lg">{icon}</span>}
        </div>
      </div>
      <div className={`text-3xl font-black tabular-nums tracking-tight ${textAccents[accent]}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function FillBar({ pct: p, color = "bg-blue-500" }) {
  return (
    <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-700 ${color}`}
        style={{ width: `${p}%` }}
      />
    </div>
  );
}

function SectionHeader({ title, count, countColor = "bg-slate-200 text-slate-600" }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">{title}</h2>
      {count !== undefined && (
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${countColor}`}>{count}</span>
      )}
    </div>
  );
}

/* ============================================================
   CRITICAL SKUS TABLE
============================================================ */
function CriticalTable({ rows }) {
  if (!rows.length) return (
    <div className="text-sm text-slate-400 py-6 text-center">
      ✓ No critical SKUs right now
    </div>
  );

  return (
    <div className="overflow-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-100">
            {["Model", "SKU", "Cover", "Repl. Qty", "AMPM Stock", "Shortfall"].map(h => (
              <th key={h} className="pb-2 pr-4 text-left font-semibold uppercase tracking-wider text-slate-400">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const woc = weeksOfCover(row.amazon_inventory, row.sales_velocity);
            const c = coverColor(woc);
            return (
              <tr key={i} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                <td className="py-2.5 pr-4 font-semibold text-slate-800">{row.model}</td>
                <td className="py-2.5 pr-4 text-slate-500 font-mono">{row.sku || "—"}</td>
                <td className="py-2.5 pr-4">
                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-bold border ${c.light} ${c.text}`}>
                    {woc === 99 ? "No sales" : `${woc.toFixed(1)}w`}
                  </span>
                </td>
                <td className="py-2.5 pr-4 font-bold text-slate-800">{fmt(row.replenishment_qty)}</td>
                <td className="py-2.5 pr-4 text-slate-600">{fmt(row.ampm_inventory)}</td>
                <td className={`py-2.5 font-bold ${row.warehouse_shortfall > 0 ? "text-red-600" : "text-emerald-600"}`}>
                  {row.warehouse_shortfall > 0 ? `-${fmt(row.warehouse_shortfall)}` : "✓ OK"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ============================================================
   FC STATUS ROWS
============================================================ */
function FCStatusRow({ fc, sendQty, totalRequired, shortCount }) {
  const fillPct = pct(sendQty, totalRequired);
  const isShort = fillPct < 70;

  return (
    <div className="flex items-center gap-4 py-2.5 border-b border-slate-50 last:border-0">
      <div className="w-16 font-mono text-xs font-bold text-slate-700 shrink-0">{fc}</div>
      <div className="flex-1">
        <FillBar pct={fillPct} color={isShort ? "bg-red-400" : fillPct > 90 ? "bg-emerald-500" : "bg-blue-500"} />
      </div>
      <div className={`w-12 text-right text-xs font-bold tabular-nums ${isShort ? "text-red-600" : "text-slate-700"}`}>
        {fillPct}%
      </div>
      <div className="w-20 text-right text-xs text-slate-400 tabular-nums">
        {fmt(sendQty)} / {fmt(totalRequired)}
      </div>
      {isShort && (
        <span className="text-xs font-bold text-red-500 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">
          SHORT
        </span>
      )}
    </div>
  );
}

/* ============================================================
   AMPM FLOW VISUAL
============================================================ */
function AMPMFlow({ totalAMPM, totalDemand, shortfallSkus }) {
  const coverPct = pct(totalAMPM, totalDemand);
  const shortfall = Math.max(0, totalDemand - totalAMPM);

  return (
    <div className="space-y-4">
      <div className="flex justify-between text-xs text-slate-500 font-medium">
        <span>AMPM Available: <span className="text-slate-800 font-bold">{fmt(totalAMPM)} units</span></span>
        <span>Total Demand: <span className="text-slate-800 font-bold">{fmt(totalDemand)} units</span></span>
      </div>

      {/* Big fill bar */}
      <div className="relative h-8 bg-slate-100 rounded-xl overflow-hidden">
        <div
          className={`h-full rounded-xl transition-all duration-1000 flex items-center justify-end pr-3
            ${coverPct >= 90 ? "bg-gradient-to-r from-emerald-400 to-emerald-500" :
              coverPct >= 60 ? "bg-gradient-to-r from-amber-400 to-amber-500" :
              "bg-gradient-to-r from-red-400 to-red-500"}`}
          style={{ width: `${coverPct}%` }}
        >
          <span className="text-white text-xs font-bold">{coverPct}%</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
          <div className="text-xl font-black text-slate-800">{coverPct}%</div>
          <div className="text-xs text-slate-400 mt-0.5">Coverage</div>
        </div>
        <div className={`rounded-xl p-3 border ${shortfall > 0 ? "bg-red-50 border-red-100" : "bg-emerald-50 border-emerald-100"}`}>
          <div className={`text-xl font-black ${shortfall > 0 ? "text-red-600" : "text-emerald-600"}`}>
            {shortfall > 0 ? `-${fmt(shortfall)}` : "✓"}
          </div>
          <div className="text-xs text-slate-400 mt-0.5">Shortfall</div>
        </div>
        <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
          <div className="text-xl font-black text-slate-800">{shortfallSkus}</div>
          <div className="text-xs text-slate-400 mt-0.5">SKUs short</div>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   ACCOUNT PILL SELECTOR
============================================================ */
function AccountSelector({ selected, onChange }) {
  return (
    <div className="flex gap-2 flex-wrap">
      {ACCOUNTS.map(acc => (
        <button
          key={acc}
          onClick={() => onChange(acc)}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
            selected === acc
              ? "bg-slate-900 text-white shadow-sm"
              : "bg-white text-slate-500 border border-slate-200 hover:border-slate-400"
          }`}
        >
          {acc}
        </button>
      ))}
    </div>
  );
}

/* ============================================================
   MAIN DASHBOARD
============================================================ */
export default function Dashboard() {
  const [account, setAccount] = useState("NEXLEV");
  const [replData, setReplData] = useState([]);
  const [fcData, setFcData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fcAccount = ACCOUNT_FC_MAP[account];

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      getReplenishment(SALES_WINDOW, REPLENISH_WEEKS, account),
      getFCFinal(REPLENISH_WEEKS, "All", fcAccount),
    ])
      .then(([repl, fc]) => {
        setReplData(Array.isArray(repl) ? repl : []);
        setFcData(Array.isArray(fc) ? fc : []);
        setLastUpdated(new Date());
      })
      .finally(() => setLoading(false));
  }, [account, fcAccount]);

  useEffect(() => { load(); }, [load]);

  /* ── REPLENISHMENT ANALYTICS ── */
  const analytics = useMemo(() => {
    const critical = replData.filter(r => weeksOfCover(r.amazon_inventory, r.sales_velocity) < 1);
    const lowCover = replData.filter(r => {
      const w = weeksOfCover(r.amazon_inventory, r.sales_velocity);
      return w >= 1 && w < REPLENISH_WEEKS;
    });
    const healthy = replData.filter(r => weeksOfCover(r.amazon_inventory, r.sales_velocity) >= REPLENISH_WEEKS);

    const totalAMPM = replData.reduce((s, r) => s + (r.ampm_inventory || 0), 0);
    const totalDemand = replData.reduce((s, r) => s + (r.replenishment_qty || 0), 0);
    const shortfallSkus = replData.filter(r => r.warehouse_shortfall > 0).length;
    const totalShortfall = replData.reduce((s, r) => s + (r.warehouse_shortfall || 0), 0);

    // Sort critical by urgency (lowest cover first)
    const criticalSorted = [...critical].sort((a, b) =>
      weeksOfCover(a.amazon_inventory, a.sales_velocity) -
      weeksOfCover(b.amazon_inventory, b.sales_velocity)
    );

    // Low cover sorted
    const lowCoverSorted = [...lowCover].sort((a, b) =>
      weeksOfCover(a.amazon_inventory, a.sales_velocity) -
      weeksOfCover(b.amazon_inventory, b.sales_velocity)
    );

    return { critical, lowCover, healthy, criticalSorted, lowCoverSorted, totalAMPM, totalDemand, shortfallSkus, totalShortfall };
  }, [replData]);

  /* ── FC ANALYTICS ── */
  const fcAnalytics = useMemo(() => {
    const byFC = {};
    fcData.forEach(row => {
      const fc = row.fulfillment_center || "Unknown";
      if (!byFC[fc]) byFC[fc] = { sendQty: 0, totalRequired: 0, shortRows: 0 };
      byFC[fc].sendQty += row.send_qty || 0;
      byFC[fc].totalRequired += row.expected_units || 0;
      if (row.velocity_flag === "SHORT_30%+") byFC[fc].shortRows++;
    });

    const fcList = Object.entries(byFC)
      .map(([fc, v]) => ({ fc, ...v }))
      .sort((a, b) => b.totalRequired - a.totalRequired);

    const totalSend = fcData.reduce((s, r) => s + (r.send_qty || 0), 0);
    const totalRequired = fcData.reduce((s, r) => s + (r.expected_units || 0), 0);
    const shortFCs = fcList.filter(f => pct(f.sendQty, f.totalRequired) < 70).length;
    const ixdUnits = fcData.filter(r => r.ixd_flag && !r.ixd_flag.toLowerCase().includes("non")).reduce((s, r) => s + (r.send_qty || 0), 0);

    return { fcList, totalSend, totalRequired, shortFCs, ixdUnits };
  }, [fcData]);

  /* ── TIME ── */
  const timeStr = lastUpdated
    ? lastUpdated.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
    : "—";

  return (
    <div className="space-y-6 pb-8">

      {/* ── HEADER ── */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">
            Morning Briefing
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Replenishment health across your inventory
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            {loading
              ? <span className="animate-pulse text-blue-500 font-medium">Refreshing…</span>
              : <span>Updated {timeStr}</span>
            }
            <button
              onClick={load}
              disabled={loading}
              className="px-3 py-1.5 bg-slate-900 text-white text-xs font-bold rounded-lg hover:bg-slate-700 transition disabled:opacity-40"
            >
              ↺ Refresh
            </button>
          </div>
          <AccountSelector selected={account} onChange={setAccount} />
        </div>
      </div>

      {/* ── TOP KPI STRIP ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Critical SKUs"
          value={analytics.critical.length}
          sub="< 1 week cover — act today"
          accent={analytics.critical.length > 0 ? "red" : "emerald"}
          pulse={analytics.critical.length > 0}
        />
        <StatCard
          label="Low Cover"
          value={analytics.lowCover.length}
          sub={`< ${REPLENISH_WEEKS} weeks — plan this week`}
          accent={analytics.lowCover.length > 0 ? "amber" : "emerald"}
        />
        <StatCard
          label="AMPM Coverage"
          value={`${pct(analytics.totalAMPM, analytics.totalDemand)}%`}
          sub={`${fmt(analytics.totalShortfall)} units shortfall`}
          accent={pct(analytics.totalAMPM, analytics.totalDemand) < 60 ? "red" : pct(analytics.totalAMPM, analytics.totalDemand) < 85 ? "amber" : "emerald"}
        />
        <StatCard
          label="FC Fill Rate"
          value={`${pct(fcAnalytics.totalSend, fcAnalytics.totalRequired)}%`}
          sub={`${fcAnalytics.shortFCs} FC${fcAnalytics.shortFCs !== 1 ? "s" : ""} SHORT_30%+`}
          accent={fcAnalytics.shortFCs > 0 ? "amber" : "emerald"}
        />
      </div>

      {/* ── MAIN 3-COLUMN GRID ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* ── COL 1: CRITICAL SKUS ── */}
        <div className="lg:col-span-2 space-y-4">

          {/* Critical */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <SectionHeader
              title="Action Required Today"
              count={analytics.critical.length}
              countColor="bg-red-100 text-red-600"
            />
            <CriticalTable rows={analytics.criticalSorted.slice(0, 8)} />
          </div>

          {/* Low Cover */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <SectionHeader
              title="Plan This Week"
              count={analytics.lowCover.length}
              countColor="bg-amber-100 text-amber-600"
            />
            <CriticalTable rows={analytics.lowCoverSorted.slice(0, 6)} />
          </div>

        </div>

        {/* ── COL 2: RIGHT PANEL ── */}
        <div className="space-y-4">

          {/* AMPM Flow */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <SectionHeader title="AMPM Stock vs Demand" />
            <AMPMFlow
              totalAMPM={analytics.totalAMPM}
              totalDemand={analytics.totalDemand}
              shortfallSkus={analytics.shortfallSkus}
            />
          </div>

          {/* FC Status */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <SectionHeader
              title="FC Allocation Status"
              count={fcAnalytics.shortFCs > 0 ? `${fcAnalytics.shortFCs} SHORT` : undefined}
              countColor="bg-red-100 text-red-600"
            />
            {fcAnalytics.fcList.length === 0 ? (
              <div className="text-sm text-slate-400 py-4 text-center">No FC data</div>
            ) : (
              <div>
                {fcAnalytics.fcList.map(({ fc, sendQty, totalRequired, shortRows }) => (
                  <FCStatusRow
                    key={fc}
                    fc={fc}
                    sendQty={sendQty}
                    totalRequired={totalRequired}
                    shortCount={shortRows}
                  />
                ))}
                <div className="mt-3 pt-3 border-t border-slate-100 flex justify-between text-xs text-slate-400">
                  <span>Total send: <span className="font-bold text-slate-700">{fmt(fcAnalytics.totalSend)}</span></span>
                  <span>IXD units: <span className="font-bold text-slate-700">{fmt(fcAnalytics.ixdUnits)}</span></span>
                </div>
              </div>
            )}
          </div>

          {/* Inventory health summary */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <SectionHeader title="Inventory Health" />
            <div className="space-y-3">
              {[
                { label: "Critical", count: analytics.critical.length, color: "bg-red-500", total: replData.length },
                { label: "Low Cover", count: analytics.lowCover.length, color: "bg-amber-400", total: replData.length },
                { label: "Healthy", count: analytics.healthy.length, color: "bg-emerald-500", total: replData.length },
              ].map(({ label, count, color, total }) => (
                <div key={label} className="flex items-center gap-3">
                  <div className="w-20 text-xs font-semibold text-slate-500">{label}</div>
                  <div className="flex-1">
                    <FillBar pct={pct(count, total)} color={color} />
                  </div>
                  <div className="w-8 text-right text-xs font-bold text-slate-700 tabular-nums">{count}</div>
                </div>
              ))}
              <div className="text-xs text-slate-400 pt-1">{replData.length} total SKUs · {REPLENISH_WEEKS}w target</div>
            </div>
          </div>

        </div>
      </div>

    </div>
  );
}