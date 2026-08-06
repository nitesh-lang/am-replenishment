import { useEffect, useMemo, useState } from "react";

/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function ChinaReorder() {

  const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";

  /* ============================================================
     STATE
  ============================================================ */

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const BRAND_OPTIONS = ["Nexlev", "Audio Array", "Tonor", "White Mulberry"];
  const [selectedBrands, setSelectedBrands] = useState(["Nexlev"]);
  const [selectedMonths, setSelectedMonths] = useState(3);
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek, setToWeek] = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);
  const [selectedL0, setSelectedL0] = useState("");
  const [selectedL1, setSelectedL1] = useState("");


  // 👇 ADD HERE
  const [search, setSearch] = useState("");
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  /* Pagination */
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;

  const [sopOpen, setSopOpen] = useState(false);

  const l0Options = useMemo(() => {
    return [...new Set(data.map(r => r.category_l0).filter(Boolean))].sort();
  }, [data]);

  const l1Options = useMemo(() => {
    if (!selectedL0) return [];
    return [...new Set(
      data.filter(r => r.category_l0 === selectedL0).map(r => r.category_l1).filter(Boolean)
    )].sort();
  }, [data, selectedL0]);

  /* ============================================================
     DATA LOAD
  ============================================================ */

  useEffect(() => {
    if (selectedBrands.length === 0) {
      setData([]);
      return;
    }
    setLoading(true);
    const params = new URLSearchParams({ months: selectedMonths });
    selectedBrands.forEach((b) => params.append("brand", b));
    if (fromWeek) params.append("from_week", fromWeek);
    if (toWeek) params.append("to_week", toWeek);
    fetch(`${BASE}/china-reorder/?${params}`)
      .then((res) => res.json())
      .then((res) => {
        setData(Array.isArray(res.data) ? res.data : []);
        if (res.available_weeks?.length) {
          const weeks = res.available_weeks;
          setAvailableWeeks(weeks);
          if (!fromWeek) setFromWeek(weeks[0]);
          if (!toWeek) setToWeek(weeks[weeks.length - 1]);
        }
      })
      .finally(() => setLoading(false));
  }, [selectedBrands, selectedMonths, fromWeek, toWeek]);

  /* ============================================================
     FILTER
  ============================================================ */
  const filteredData = useMemo(() => {
  return data
    .filter((row) => row.model?.toLowerCase().includes(search.toLowerCase()))
    .filter((row) => {
      return true;
    })
    .filter((row) => !selectedL0 || row.category_l0 === selectedL0)
    .filter((row) => !selectedL1 || row.category_l1 === selectedL1);
}, [data, search, selectedL0, selectedL1]);

  /* ============================================================
     SORT
  ============================================================ */

  const sortedData = useMemo(() => {
    if (!sortConfig.key) return filteredData;

    const direction = sortConfig.direction === "asc" ? 1 : -1;

    return [...filteredData].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];

      if (aVal == null) return 1;
      if (bVal == null) return -1;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return (aVal - bVal) * direction;
      }

      return aVal.toString().localeCompare(bVal.toString()) * direction;
    });
  }, [filteredData, sortConfig]);

  function toggleSort(column) {
    setSortConfig((prev) => ({
      key: column,
      direction:
        prev.key === column && prev.direction === "asc"
          ? "desc"
          : "asc",
    }));
  }

  function getSortArrow(column) {
    if (sortConfig.key !== column) return "";
    return sortConfig.direction === "asc" ? "▲" : "▼";
  }

  /* ============================================================
     HEALTH LOGIC
  ============================================================ */

 function getStatus(row) {
  const cover = row.weeks_cover || 0;

  if (cover < 12) return "CRITICAL";
  if (cover >= 12 && cover <= 16) return "MODERATE";
  return "NO REORDER";
}

 function getRowColor(status) {
  if (status === "CRITICAL") return "bg-red-50";
  if (status === "MODERATE") return "bg-yellow-50";
  return "bg-emerald-50/40";
}

  function getStatusBadge(status) {
  if (status === "CRITICAL")
    return "bg-red-100 text-red-700";

  if (status === "MODERATE")
    return "bg-yellow-100 text-yellow-700";

  return "bg-emerald-100 text-emerald-700";
}

  /* ============================================================
     PAGINATION
  ============================================================ */

  const totalPages = Math.ceil(sortedData.length / rowsPerPage);

  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return sortedData.slice(start, start + rowsPerPage);
  }, [sortedData, currentPage]);

  /* ============================================================
     KPI CALCULATION
  ============================================================ */

  const kpis = useMemo(() => {
    const totalReorder = sortedData.reduce(
      (sum, r) => sum + (r.suggested_reorder || 0),
      0
    );

    const avgCover =
      sortedData.reduce((sum, r) => sum + (r.weeks_cover || 0), 0) /
      (sortedData.length || 1);

    return {
      totalReorder,
      avgCover,
      models: sortedData.length,
    };
  }, [sortedData]);

  /* ============================================================
     CSV EXPORT
  ============================================================ */

  function exportCSV() {
    if (!sortedData.length) return;

    const headers = Object.keys(sortedData[0]).join(",");
    const rows = sortedData
      .map((row) =>
        Object.values(row)
          .map((val) => `"${val}"`)
          .join(",")
      )
      .join("\n");

    const blob = new Blob([headers + "\n" + rows], {
      type: "text/csv;charset=utf-8;",
    });

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "china_reorder_export.csv";
    link.click();
  }

  /* ============================================================
     RENDER
  ============================================================ */

  return (
    <div className="space-y-4">

      {/* HEADER */}
      <div className="rounded-xl px-5 py-3 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold">Reorder Intelligence</h1>
          <p className="text-indigo-200 text-xs">12-week sales vs inventory based production planning</p>
        </div>
        <button
          onClick={() => setSopOpen(true)}
          className="px-3 py-1 text-xs bg-white/10 hover:bg-white/20 border border-white/20 rounded transition flex items-center gap-1.5"
          title="Read the SOP for this page"
        >
          📘 How is this calculated?
        </button>
      </div>

      {/* SOP MODAL */}
      <ChinaReorderSOPModal open={sopOpen} onClose={() => setSopOpen(false)} />

      {/* KPI SECTION */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <MetricCard title="Total Units to Reorder" value={Math.round(kpis.totalReorder)} />
        <MetricCard title="Avg Weeks Cover" value={kpis.avgCover?.toFixed(2)} />
        <MetricCard title="Total Models" value={kpis.models} />
      </div>

      {/* SALES WINDOW */}
      <div className="card grid grid-cols-1 md:grid-cols-2 gap-3 py-3">
        <div>
          <label className="text-xs uppercase text-slate-400">Sales Window (Range)</label>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">From</div>
              <select
                value={fromWeek || ""}
                onChange={(e) => { setCurrentPage(1); setFromWeek(Number(e.target.value)); }}
                className="w-full px-4 py-2 border rounded-lg"
              >
                {availableWeeks.map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
            </div>
            <div>
              <div className="text-xs text-slate-400 mb-1">To</div>
              <select
                value={toWeek || ""}
                onChange={(e) => { setCurrentPage(1); setToWeek(Number(e.target.value)); }}
                className="w-full px-4 py-2 border rounded-lg"
              >
                {availableWeeks.map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* FILTERS */}
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <div className="flex flex-wrap gap-3 items-center">
          {/* Multi-select brand pills */}
          <div className="flex flex-wrap gap-1.5 items-center">
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mr-1">Brands</span>
            {BRAND_OPTIONS.map((b) => {
              const active = selectedBrands.includes(b);
              return (
                <button
                  key={b}
                  onClick={() => {
                    setCurrentPage(1);
                    setSelectedBrands((prev) => {
                      const next = prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b];
                      return next;
                    });
                    // Reset week + category filters when brand mix changes
                    setFromWeek(null);
                    setToWeek(null);
                    setAvailableWeeks([]);
                    setSelectedL0("");
                    setSelectedL1("");
                  }}
                  className={`px-2.5 py-1.5 text-xs rounded-md border transition ${
                    active
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                  }`}
                >
                  {b}
                </button>
              );
            })}
            {selectedBrands.length > 0 && (
              <button
                onClick={() => { setCurrentPage(1); setSelectedBrands([]); }}
                className="text-xs text-slate-500 hover:text-slate-900 ml-1"
                title="Clear all brand selections"
              >
                clear
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <select
              value={selectedMonths}
              onChange={(e) => { setCurrentPage(1); setSelectedMonths(Number(e.target.value)); }}
              className="px-4 py-2 border rounded-lg"
            >
              {[1,2,3,4,5,6].map(m => (
                <option key={m} value={m}>{m} Month{m > 1 ? "s" : ""}</option>
              ))}
            </select>
          </div>

          {l0Options.length > 0 && (
            <select
              value={selectedL0}
              onChange={(e) => { setCurrentPage(1); setSelectedL0(e.target.value); setSelectedL1(""); }}
              className="px-4 py-2 border rounded-lg"
            >
              <option value="">All Categories</option>
              {l0Options.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          )}

          {selectedL0 && l1Options.length > 0 && (
            <select
              value={selectedL1}
              onChange={(e) => { setCurrentPage(1); setSelectedL1(e.target.value); }}
              className="px-4 py-2 border rounded-lg"
            >
              <option value="">All Sub-categories</option>
              {l1Options.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          )}

          <input
            value={search}
            onChange={(e) => { setCurrentPage(1); setSearch(e.target.value); }}
            placeholder="Search model..."
            className="px-4 py-2 border rounded-lg w-48"
          />
        </div>

        <button
          onClick={exportCSV}
          className="px-4 py-2 bg-slate-900 text-white rounded-lg"
        >
          Export CSV
        </button>
      </div>

      {/* TABLE */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-auto max-h-[75vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-xs uppercase sticky top-0">
              <tr>
                {["model", "sku", "asin", "last_12w_sales", "avg_weekly_sales", "current_inventory", "open_order_qty", "pipeline_qty", "suggested_reorder", "avg_rating", "rating_count", "returns_pct", "net_margin_inr", "net_margin_pct"]
                  .map((col) => (
                    <th
                      key={col}
                      onClick={() => toggleSort(col)}
                      className="px-4 py-3 cursor-pointer whitespace-nowrap"
                    >
                      {{
                        "sku":              "SKU",
                        "asin":             "ASIN",
                        "open_order_qty":   "PO Yet to Pickup",
                        "pipeline_qty":     "PO Picked Up",
                        "avg_rating":       "Rating",
                        "rating_count":     "# Ratings",
                        "returns_pct":      "Returns %",
                        "net_margin_inr":   "Net Margin ₹",
                        "net_margin_pct":   "Net Margin %",
                      }[col] || col} {getSortArrow(col)}
                    </th>
                  ))}
                <th onClick={() => toggleSort("status")} className="px-4 py-3 cursor-pointer">Status {getSortArrow("status")}</th>
              </tr>
            </thead>

            <tbody>
              {paginatedData.map((row, i) => {
                const status = getStatus(row);
                const ratingsCount = Number(row.rating_count) || 0;
                const returnsPct   = Number(row.returns_pct)  || 0;
                const netMarginInr = Number(row.net_margin_inr) || 0;
                const netMarginPct = Number(row.net_margin_pct) || 0;

                return (
                  <tr
                    key={i}
                    className={`${getRowColor(status)} hover:bg-slate-50`}
                  >
                    <td className="px-4 py-3 font-medium">{row.model}</td>
                    <td className="px-4 py-3 text-slate-600">{row.sku || "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{row.asin || "—"}</td>
                    <td className="px-4 py-3">{row.last_12w_sales}</td>
                    <td className="px-4 py-3">{row.avg_weekly_sales?.toFixed(2)}</td>
                    <td className="px-4 py-3">{row.current_inventory}</td>
                    <td className="px-4 py-3 font-medium text-indigo-600">{row.open_order_qty || 0}</td>
                    <td className="px-4 py-3 font-medium text-purple-600">{row.pipeline_qty || 0}</td>
                    <td className="px-4 py-3 font-semibold text-indigo-700">{Math.round(row.suggested_reorder)}</td>

                    {/* Reviews */}
                    <td className="px-4 py-3 tabular-nums">{row.avg_rating ? Number(row.avg_rating).toFixed(1) : "—"}</td>
                    <td className="px-4 py-3 tabular-nums text-slate-600">{ratingsCount ? ratingsCount.toLocaleString() : "—"}</td>

                    {/* Returns %  — colour amber if >10 %, red if >20 % */}
                    <td className={`px-4 py-3 tabular-nums font-medium ${
                      returnsPct >= 20 ? "text-red-700" :
                      returnsPct >= 10 ? "text-amber-700" : "text-slate-700"
                    }`}>
                      {returnsPct ? `${returnsPct.toFixed(1)}%` : "—"}
                    </td>

                    {/* Net Margin */}
                    <td className={`px-4 py-3 tabular-nums font-medium ${netMarginInr < 0 ? "text-red-700" : "text-slate-800"}`}>
                      {netMarginInr ? `₹${netMarginInr.toLocaleString()}` : "—"}
                    </td>
                    <td className={`px-4 py-3 tabular-nums ${netMarginPct < 0 ? "text-red-700" : "text-slate-700"}`}>
                      {netMarginPct ? `${netMarginPct.toFixed(2)}%` : "—"}
                    </td>

                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs rounded ${getStatusBadge(status)}`}>
                        {status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* PAGINATION */}
        <div className="flex justify-between items-center p-4 border-t">
          <button
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => p - 1)}
            className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50"
          >
            Previous
          </button>

          <div>
            Page {currentPage} of {totalPages}
          </div>

          <button
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage((p) => p + 1)}
            className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   COMPONENTS
============================================================ */

function MetricCard({ title, value }) {
  return (
    <div className="px-3 py-2 bg-white rounded-lg shadow-sm border border-slate-100">
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{title}</div>
      <div className="text-base font-semibold text-slate-800">{value ?? "-"}</div>
    </div>
  );
}

function ChinaReorderSOPModal({ open, onClose }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[88vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              How China Reorder is Calculated
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Brands: Nexlev · Audio Array · Tonor · White Mulberry
            </p>
          </div>
          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-slate-100 text-slate-700 text-xs rounded hover:bg-slate-200"
          >
            Close
          </button>
        </div>

        <div className="overflow-auto flex-1 min-h-0 p-5 text-sm text-slate-700 space-y-4 leading-relaxed">

          <p className="text-slate-600">
            Tells you how many units to order from China for each model, based on recent weekly sales and what's already in inventory + on order + in pipeline.
          </p>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Top controls</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>Brand</b> — Nexlev / Audio Array / Tonor / White Mulberry (each uses its own inventory snapshot file)</li>
              <li><b>Months</b> — Cover horizon. Target weeks = Months × 4 (default 3 months → 12 weeks)</li>
              <li><b>Sales Window (From / To)</b> — Range from the last 12 available weeks</li>
              <li><b>Category L0 / L1</b> filters and Search</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Where the numbers come from</h3>
            <table className="w-full text-xs border-collapse">
              <tbody>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium w-44">Sales</td><td className="border border-slate-300 px-2 py-1"><code>weekly_sales_snapshot.csv</code> · filtered to the selected brand</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Nexlev inventory</td><td className="border border-slate-300 px-2 py-1"><code>inventory_snapshot_nexlev.xlsx</code></td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Audio Array inventory</td><td className="border border-slate-300 px-2 py-1"><code>Inventory_snapshot_audio_array.xlsx</code></td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Tonor inventory</td><td className="border border-slate-300 px-2 py-1"><code>Inventory_snapshot_tonor.xlsx</code></td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">White Mulberry inventory</td><td className="border border-slate-300 px-2 py-1"><code>Inventory_snapshot_WM.xlsx</code></td></tr>
              </tbody>
            </table>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Inventory split (by channel column)</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><code>open order</code> rows → <b>Open Order Qty</b></li>
              <li><code>pipeline</code> rows → <b>Pipeline Qty</b> (units already in transit from China)</li>
              <li>Everything else (AMPM / 1P / other) → <b>Current Inventory</b></li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Columns</h3>
            <table className="w-full text-xs border-collapse">
              <tbody>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium w-44">Last 12W Sales</td><td className="border border-slate-300 px-2 py-1">Total units sold in the selected window</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Avg Weekly Sales</td><td className="border border-slate-300 px-2 py-1">Last 12W Sales ÷ window weeks</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Current Inventory</td><td className="border border-slate-300 px-2 py-1">Sum of non-open-order, non-pipeline channel rows</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Open Order Qty</td><td className="border border-slate-300 px-2 py-1">Sum of <code>open order</code> rows</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Pipeline Qty</td><td className="border border-slate-300 px-2 py-1">Sum of <code>pipeline</code> rows (in-transit from China)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Weeks Cover</td><td className="border border-slate-300 px-2 py-1">Current Inventory ÷ Avg Weekly Sales (how long current stock lasts)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Target Stock</td><td className="border border-slate-300 px-2 py-1">Avg Weekly Sales × (Months × 4)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium bg-amber-50">Suggested Reorder</td><td className="border border-slate-300 px-2 py-1 bg-amber-50">max(0, Target Stock − Current Inventory − Open Order − Pipeline)</td></tr>
              </tbody>
            </table>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Other notes</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li>All sales channels are counted (no channel filter on this page)</li>
              <li>Model auto-normalization: <code>ETC-07-WH</code> matches <code>ETC-07</code> in inventory; bundle names like <code>UB-01 (AI-04...)</code> match by base <code>UB-01</code></li>
              <li>Available weeks: most recent 12 weeks in the sales file (older weeks ignored)</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Example</h3>
            <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
              AA-01: sold 240 units over 12 weeks → Avg Weekly = 20 →
              3-month target = 20 × 12 = 240 → Current Inventory = 80 →
              Open Order = 50, Pipeline = 30 → <b>Suggested Reorder = 240 − 80 − 50 − 30 = 80</b>.
            </p>
          </section>

        </div>
      </div>
    </div>
  );
}