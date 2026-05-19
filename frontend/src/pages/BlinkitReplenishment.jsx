import { useEffect, useMemo, useState } from "react";
import { logUsage } from "../auth/usage";

export default function BlinkitReplenishment() {

  const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // View mode — toggle between per-SKU and per-State
  const [viewMode, setViewMode] = useState("sku");   // "sku" | "state"

  const [coverWeeks, setCoverWeeks] = useState(8);
  const coverWeeksOptions = [2, 4, 6, 8, 10, 12];

  // Sales window — populated from API response. The available weeks are
  // different per view (weekly snapshot for SKU view, ISO weeks from monthly
  // order exports for State view), so we reset when viewMode flips.
  const [availableWeeks, setAvailableWeeks] = useState([]);
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek,   setToWeek]   = useState(null);
  const [windowSize, setWindowSize] = useState(12);

  const [search, setSearch] = useState("");
  const [selectedBrand, setSelectedBrand] = useState("All");

  const [sortConfig, setSortConfig] = useState({ key: null, direction: "asc" });
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;

  // Reset week selectors when the view mode flips (different week sets)
  useEffect(() => {
    setFromWeek(null);
    setToWeek(null);
    setAvailableWeeks([]);
  }, [viewMode]);

  // ─── LOAD ─────────────────────────────────────────────────────────────
  useEffect(() => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ cover_weeks: coverWeeks });
    if (fromWeek != null) params.append("from_week", fromWeek);
    if (toWeek   != null) params.append("to_week",   toWeek);

    const endpoint = viewMode === "state"
      ? `${BASE}/api/blinkit-replenishment/statewise?${params}`
      : `${BASE}/api/blinkit-replenishment/?${params}`;

    fetch(endpoint)
      .then((res) => res.json())
      .then((res) => {
        if (res.error) {
          setError(res.error);
          setData([]);
        } else {
          setData(res.data || []);
        }
        // Hydrate the week dropdowns from the response on first load
        if (Array.isArray(res.available_weeks) && res.available_weeks.length) {
          // API returns descending — sort ascending for the dropdowns
          const weeksAsc = [...res.available_weeks].sort((a, b) => a - b);
          setAvailableWeeks(weeksAsc);
          if (fromWeek == null || toWeek == null) {
            // Default: last 12 available weeks (most recent at the top)
            const sortedDesc = [...res.available_weeks].sort((a, b) => b - a);
            const last12 = sortedDesc.slice(0, 12);
            setFromWeek(Math.min(...last12));
            setToWeek(Math.max(...last12));
          }
        }
        if (res.selected_window?.weeks_in_window) {
          setWindowSize(res.selected_window.weeks_in_window);
        }
      })
      .catch((e) => {
        setError(e.message || "Failed to load");
        setData([]);
      })
      .finally(() => setLoading(false));
  }, [viewMode, coverWeeks, fromWeek, toWeek]);

  // ─── DERIVED ─────────────────────────────────────────────────────────
  const brands = useMemo(() => {
    const b = [...new Set(data.map((r) => r.brand).filter(Boolean))];
    return ["All", ...b.sort()];
  }, [data]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return data
      .filter((r) => selectedBrand === "All" || r.brand === selectedBrand)
      .filter((r) => {
        if (!q) return true;
        return (
          (r.model || "").toLowerCase().includes(q) ||
          (r.sku || "").toLowerCase().includes(q) ||
          (r.customer_state || "").toLowerCase().includes(q) ||
          String(r.item_id || "").toLowerCase().includes(q) ||
          String(r.product_id || "").toLowerCase().includes(q)
        );
      });
  }, [data, search, selectedBrand]);

  const sorted = useMemo(() => {
    if (!sortConfig.key) return filtered;
    const dir = sortConfig.direction === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = a[sortConfig.key];
      const bv = b[sortConfig.key];
      if (av == null || av === "") return 1;
      if (bv == null || bv === "") return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [filtered, sortConfig]);

  function toggleSort(col) {
    setSortConfig((prev) => ({
      key: col,
      direction: prev.key === col && prev.direction === "asc" ? "desc" : "asc",
    }));
  }

  const totalPages = Math.max(1, Math.ceil(sorted.length / rowsPerPage));
  const paginated = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return sorted.slice(start, start + rowsPerPage);
  }, [sorted, currentPage]);

  const kpis = useMemo(() => {
    if (viewMode === "state") {
      const totalReq = sorted.reduce((s, r) => s + (Number(r.state_required) || 0), 0);
      const totalDef = sorted.reduce((s, r) => s + (Number(r.state_deficiency) || 0), 0);
      const skus     = new Set(sorted.map((r) => r.sku)).size;
      const states   = new Set(sorted.map((r) => r.customer_state)).size;
      return { totalReq, totalDef, skus, states };
    }
    const totalDef    = sorted.reduce((s, r) => s + (Number(r.deficiency) || 0), 0);
    const totalSend   = sorted.reduce((s, r) => s + (Number(r.send_qty) || 0), 0);
    const totalShortf = sorted.reduce((s, r) => s + (Number(r.warehouse_shortfall) || 0), 0);
    const avgVel      = sorted.length
      ? sorted.reduce((s, r) => s + (Number(r.avg_weekly_sales) || 0), 0) / sorted.length
      : 0;
    return {
      totalDef, totalSend, totalShortf, avgVel: Math.round(avgVel * 10) / 10,
      skus: sorted.length,
    };
  }, [sorted, viewMode]);

  // ─── EXPORT ──────────────────────────────────────────────────────────
  function exportCSV() {
    if (!sorted.length) return;
    const headers = Object.keys(sorted[0]).join(",");
    const rows = sorted
      .map((row) =>
        Object.values(row)
          .map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`)
          .join(",")
      )
      .join("\n");
    const blob = new Blob([headers + "\n" + rows], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `blinkit_${viewMode === "state" ? "statewise_" : ""}replenishment_${coverWeeks}w.csv`;
    link.click();
    logUsage("export", "blinkit-replenishment", { rows: sorted.length });
  }

  // ─── COLUMN DEFS ─────────────────────────────────────────────────────
  const skuColumns = [
    { key: "brand",                label: "Brand" },
    { key: "model",                label: "Model" },
    { key: "sku",                  label: "SKU" },
    { key: "item_id",              label: "Item ID" },
    { key: "product_id",           label: "Product ID" },
    { key: "expansion_level",      label: "Expansion" },
    { key: "category_l1",          label: "Category" },
    { key: "master_carton",        label: "Carton", numeric: true },
    { key: "blinkit_soh",          label: "Blinkit SOH", numeric: true },
    { key: "ampm_inv",             label: "AMPM Inv", numeric: true },
    { key: "total_sales_window",   label: `Sales (${windowSize}w)`, numeric: true },
    { key: "avg_weekly_sales",     label: "Avg Wk Sales", numeric: true },
    { key: "required_units",       label: "Required", numeric: true, highlight: true },
    { key: "deficiency",           label: "Deficiency", numeric: true, highlight: true },
    { key: "send_qty",             label: "Send Qty", numeric: true, highlight: "primary" },
    { key: "warehouse_shortfall",  label: "WH Shortfall", numeric: true },
  ];

  const stateColumns = [
    { key: "brand",                label: "Brand" },
    { key: "model",                label: "Model" },
    { key: "sku",                  label: "SKU" },
    { key: "customer_state",       label: "State", highlight: true },
    { key: "state_sales",          label: `Sales (${windowSize}w)`, numeric: true },
    { key: "state_share_pct",      label: "Share %", numeric: true },
    { key: "state_avg_weekly",     label: "Avg Wk Sales", numeric: true },
    { key: "state_required",       label: "Required", numeric: true, highlight: true },
    { key: "blinkit_soh",          label: "Blinkit SOH (Total)", numeric: true },
    { key: "state_soh_estimate",   label: "State SOH (est.)", numeric: true },
    { key: "state_deficiency",     label: "Deficiency", numeric: true, highlight: "primary" },
    { key: "ampm_inv",             label: "AMPM Inv", numeric: true },
  ];

  const columns = viewMode === "state" ? stateColumns : skuColumns;

  return (
    <div className="space-y-4">

      {/* HEADER */}
      <div className="rounded-xl px-5 py-3 bg-gradient-to-r from-emerald-900 via-slate-800 to-slate-900 text-white shadow flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold">Blinkit Replenishment Intelligence</h1>
          <p className="text-slate-300 text-xs">
            {viewMode === "state"
              ? "Per-state demand split across 11 customer states"
              : "Per-SKU replenishment across 17 dark stores"}
          </p>
        </div>
      </div>

      {/* KPI CARDS — different metrics per view */}
      {viewMode === "state" ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiTile label="SKUs Selling"            value={kpis.skus} />
          <KpiTile label="States Covered"          value={kpis.states} />
          <KpiTile label="Total Required Units"    value={kpis.totalReq} />
          <KpiTile label="Total Deficiency"        value={kpis.totalDef} tone="amber" />
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KpiTile label="Active SKUs"          value={kpis.skus} />
          <KpiTile label="Total Deficiency"     value={kpis.totalDef}    tone="amber" />
          <KpiTile label="Send Qty (capped)"    value={kpis.totalSend}   tone="emerald" />
          <KpiTile label="Warehouse Shortfall"  value={kpis.totalShortf} tone="red" />
          <KpiTile label={`Avg Weekly Sales`}   value={kpis.avgVel} />
        </div>
      )}

      {/* CONTROL ROW — view toggle + sales window + cover weeks + filters + export */}
      <div className="flex flex-wrap gap-3 items-center px-3 py-2 bg-white border border-slate-200 rounded-lg">

        {/* View toggle */}
        <div className="inline-flex rounded-md border border-slate-200 overflow-hidden">
          <button
            onClick={() => { setCurrentPage(1); setViewMode("sku"); }}
            className={`px-3 py-1.5 text-xs font-medium transition ${
              viewMode === "sku"
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            Per-SKU
          </button>
          <button
            onClick={() => { setCurrentPage(1); setViewMode("state"); }}
            className={`px-3 py-1.5 text-xs font-medium transition ${
              viewMode === "state"
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            Per-State
          </button>
        </div>

        {/* Sales Window */}
        <div className="flex items-center gap-2">
          <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Sales Window</label>
          <select
            value={fromWeek ?? ""}
            onChange={(e) => { setCurrentPage(1); setFromWeek(Number(e.target.value)); }}
            disabled={!availableWeeks.length}
            className="px-2.5 py-1.5 text-sm border border-slate-200 rounded-md bg-white disabled:opacity-50"
          >
            {availableWeeks.map((w) => <option key={`f-${w}`} value={w}>Week {w}</option>)}
          </select>
          <span className="text-slate-400 text-xs">→</span>
          <select
            value={toWeek ?? ""}
            onChange={(e) => { setCurrentPage(1); setToWeek(Number(e.target.value)); }}
            disabled={!availableWeeks.length}
            className="px-2.5 py-1.5 text-sm border border-slate-200 rounded-md bg-white disabled:opacity-50"
          >
            {availableWeeks.map((w) => <option key={`t-${w}`} value={w}>Week {w}</option>)}
          </select>
        </div>

        {/* Cover Weeks */}
        <div className="flex items-center gap-2">
          <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Cover Weeks</label>
          <select
            value={coverWeeks}
            onChange={(e) => { setCurrentPage(1); setCoverWeeks(Number(e.target.value)); }}
            className="px-2.5 py-1.5 text-sm border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-400"
          >
            {coverWeeksOptions.map((w) => (
              <option key={w} value={w}>{w} Week{w > 1 ? "s" : ""}</option>
            ))}
          </select>
        </div>

        {/* Brand */}
        <select
          value={selectedBrand}
          onChange={(e) => { setCurrentPage(1); setSelectedBrand(e.target.value); }}
          className="px-2.5 py-1.5 text-sm border border-slate-200 rounded-md bg-white"
        >
          {brands.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>

        {/* Search */}
        <input
          value={search}
          onChange={(e) => { setCurrentPage(1); setSearch(e.target.value); }}
          placeholder={viewMode === "state"
            ? "Search model / SKU / State..."
            : "Search model / SKU / Item ID / Product ID..."}
          className="px-3 py-1.5 text-sm border border-slate-200 rounded-md w-64"
        />

        {/* Export — right side */}
        <button
          onClick={exportCSV}
          className="ml-auto px-4 py-1.5 text-sm bg-slate-900 text-white rounded-md hover:bg-slate-800 transition"
        >
          Export CSV
        </button>
      </div>

      {/* ERROR */}
      {error && (
        <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500 flex-shrink-0"></span>
          {error}
        </div>
      )}

      {/* TABLE */}
      <div className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
        <div className="overflow-auto max-h-[68vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-[10px] uppercase tracking-wider text-slate-600 sticky top-0 z-10">
              <tr>
                {columns.map((c) => (
                  <th
                    key={c.key}
                    onClick={() => toggleSort(c.key)}
                    className={`px-3 py-2.5 font-semibold cursor-pointer select-none whitespace-nowrap ${
                      c.numeric ? "text-right" : "text-left"
                    }`}
                  >
                    {c.label}
                    {sortConfig.key === c.key && (
                      <span className="ml-1 text-slate-400">{sortConfig.direction === "asc" ? "▲" : "▼"}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-slate-400 text-xs">Loading…</td></tr>
              )}
              {!loading && paginated.length === 0 && (
                <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-slate-400 text-xs">No rows match the current filters.</td></tr>
              )}
              {!loading && paginated.map((row, i) => (
                <tr key={`${row.sku}-${i}`} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
                  {columns.map((c) => {
                    const v = row[c.key];
                    const isHighlight = c.highlight === true;
                    const isPrimary   = c.highlight === "primary";
                    return (
                      <td
                        key={c.key}
                        className={`px-3 py-2 whitespace-nowrap ${
                          c.numeric ? "text-right tabular-nums" : ""
                        } ${
                          isPrimary  ? "font-semibold text-emerald-700" :
                          isHighlight ? "font-medium text-slate-900" :
                          "text-slate-700"
                        }`}
                      >
                        {v === null || v === undefined || v === "" ? "-" : v}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {sorted.length > rowsPerPage && (
          <div className="flex items-center justify-between px-3 py-2 bg-slate-50/50 border-t border-slate-200 text-xs">
            <div className="text-slate-500">
              Showing <span className="font-semibold text-slate-700">{(currentPage - 1) * rowsPerPage + 1}–{Math.min(currentPage * rowsPerPage, sorted.length)}</span> of {sorted.length}
            </div>
            <div className="flex gap-1">
              <button
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="px-2.5 py-1 rounded border border-slate-200 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Prev
              </button>
              <span className="px-2.5 py-1 text-slate-600">Page {currentPage} / {totalPages}</span>
              <button
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className="px-2.5 py-1 rounded border border-slate-200 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function KpiTile({ label, value, tone = "slate" }) {
  const map = {
    slate:   "bg-white border-slate-200 text-slate-900",
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-800",
    amber:   "bg-amber-50 border-amber-200 text-amber-800",
    red:     "bg-red-50 border-red-200 text-red-800",
  };
  return (
    <div className={`border rounded-lg px-3 py-2 ${map[tone] || map.slate}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-70 font-semibold">{label}</div>
      <div className="text-xl font-semibold tabular-nums mt-0.5">{value}</div>
    </div>
  );
}
