import { useEffect, useMemo, useState } from "react";

export default function WMReplenishment() {

  const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [coverWeeks, setCoverWeeks] = useState(8);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: "asc" });
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek, setToWeek] = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);
  const [sopOpen, setSopOpen] = useState(false);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ cover_weeks: coverWeeks });
    if (fromWeek) params.append("from_week", fromWeek);
    if (toWeek) params.append("to_week", toWeek);
    fetch(`${BASE}/api/wm-replenishment/?${params}`)
      .then((res) => res.json())
      .then((res) => {
        setData(res.data || []);
        if (res.available_weeks?.length) {
          const weeks = res.available_weeks;
          setAvailableWeeks(weeks);
          if (!fromWeek) setFromWeek(weeks[0]);
          if (!toWeek) setToWeek(weeks[weeks.length - 1]);
        }
      })
      .finally(() => setLoading(false));
  }, [fromWeek, toWeek, coverWeeks]);

  const categories = useMemo(() => {
    const cats = [...new Set(data.map(r => r.category).filter(Boolean))];
    return ["All", ...cats.sort()];
  }, [data]);

  const filteredData = useMemo(() => {
    return data
      .filter((row) => selectedCategory === "All" || row.category === selectedCategory)
      .filter((row) => row.model?.toLowerCase().includes(search.toLowerCase()));
  }, [data, search, selectedCategory]);

  const calculatedData = filteredData;

  const sortedData = useMemo(() => {
    if (!sortConfig.key) return calculatedData;
    const direction = sortConfig.direction === "asc" ? 1 : -1;
    return [...calculatedData].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === "number" && typeof bVal === "number") return (aVal - bVal) * direction;
      return aVal.toString().localeCompare(bVal.toString()) * direction;
    });
  }, [calculatedData, sortConfig]);

  function toggleSort(column) {
    setSortConfig((prev) => ({
      key: column,
      direction: prev.key === column && prev.direction === "asc" ? "desc" : "asc",
    }));
  }

  const totalPages = Math.ceil(sortedData.length / rowsPerPage);

  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return sortedData.slice(start, start + rowsPerPage);
  }, [sortedData, currentPage]);

  const kpis = useMemo(() => {
    const totalRequired = sortedData.reduce((sum, r) => sum + (r.deficiency || 0), 0);
    const avgVelocity = sortedData.reduce((sum, r) => sum + (r.avg_weekly_sales || 0), 0) / (sortedData.length || 1);
    return { totalRequired, avgVelocity, models: sortedData.length };
  }, [sortedData]);

  function exportCSV() {
    if (!sortedData.length) return;
    const headers = Object.keys(sortedData[0]).join(",");
    const rows = sortedData
      .map((row) => Object.values(row).map((val) => `"${String(val).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([headers + "\n" + rows], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "wm_replenishment.csv";
    link.click();
  }

  return (
    <div className="space-y-4">

      {/* HEADER */}
      <div className="rounded-xl px-5 py-3 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold">Clicktech Replenishment Intelligence</h1>
          <p className="text-slate-300 text-xs">Clicktech / WM Inventory Planning</p>
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
      <WMSOPModal open={sopOpen} onClose={() => setSopOpen(false)} />

      {/* KPI */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <MetricCard title="Units Required" value={Math.round(kpis.totalRequired)} />
        <MetricCard title="Avg Weekly Sales" value={kpis.avgVelocity?.toFixed(2)} />
        <MetricCard title="Models" value={kpis.models} />
      </div>

      {/* SALES WINDOW + COVER WEEKS */}
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
        <div>
          <label className="text-xs uppercase tracking-wider text-slate-400">Cover Weeks</label>
          <div className="grid grid-cols-1 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">&nbsp;</div>
              <select
                value={coverWeeks}
                onChange={(e) => { setCurrentPage(1); setCoverWeeks(Number(e.target.value)); }}
                className="w-full px-4 py-2 border border-slate-200 rounded-lg"
              >
                {[4,5,6,7,8,9,10,11,12].map(w => (
                  <option key={w} value={w}>{w} Week{w > 1 ? "s" : ""}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* FILTER */}
      <div className="flex gap-4">
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className="px-4 py-2 border rounded-lg"
        >
          {categories.map(c => <option key={c}>{c}</option>)}
        </select>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search model..."
          className="px-4 py-2 border rounded-lg w-64"
        />
        <button onClick={exportCSV} className="px-4 py-2 bg-slate-900 text-white rounded-lg">
          Export CSV
        </button>
        <button
          onClick={async () => {
            if (!window.confirm("Reset all saved PO requirements and remarks? Fresh calculations will show.")) return;
            await fetch(`${BASE}/api/wm-replenishment/reset`, { method: "POST" });
            window.location.reload();
          }}
          className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition"
        >
          Reset
        </button>
      </div>

      {/* TABLE */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-auto max-h-[75vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-xs uppercase sticky top-0">
              <tr>
                {[
                  "model","category","hazmat_type","final_cb_qty","ampm_inventory",
                  "cb_3m_sales","amazon_3m_sales","avg_weekly_sales",
                  "estimated_qty","deficiency","open_po","in_transit",
                  "po_requirement","remarks"
                ].map((col) => (
                  <th key={col} onClick={() => toggleSort(col)} className="px-4 py-3 cursor-pointer">
                    {{
                      "final_cb_qty": "Clicktech QTY",
                      "cb_3m_sales": "Clicktech 3M Sales",
                      "amazon_3m_sales": "Amazon 3M Sales",
                      "ampm_inventory": "Mother Warehouse",
                      "hazmat_type": "Hazmat Type",
                      "avg_weekly_sales": "Avg Weekly Sales",
                      "estimated_qty": "Estimated QTY",
                      "deficiency": "Deficiency",
                      "open_po": "Open PO",
                      "in_transit": "In Transit",
                      "po_requirement": "PO Requirement",
                      "remarks": "Remarks",
                      "model": "Model"
                    }[col] || col}
                    {sortConfig.key === col ? (sortConfig.direction === "asc" ? " ▲" : " ▼") : " ↕"}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paginatedData.map((row, i) => (
                <tr key={i} className="hover:bg-slate-50 border-b">
                  <td className="px-4 py-3 font-medium">{row.model}</td>
                  <td className="px-4 py-3">{row.category || "-"}</td>
                  <td className="px-4 py-3">{row.hazmat_type || "-"}</td>
                  <td className="px-4 py-3">{row.final_cb_qty ?? 0}</td>
                  <td className="px-4 py-3">{row.ampm_inventory ?? 0}</td>
                  <td className="px-4 py-3">{row.cb_3m_sales ?? 0}</td>
                  <td className="px-4 py-3">{row.amazon_3m_sales ?? 0}</td>
                  <td className="px-4 py-3">{row.avg_weekly_sales?.toFixed(2)}</td>
                  <td className="px-4 py-3 font-semibold text-slate-700">{Math.round(row.estimated_qty)}</td>
                  <td className="px-4 py-3 text-red-600 font-semibold">{Math.round(row.deficiency)}</td>
                  <td className="px-4 py-3">{row.open_po ?? 0}</td>
                  <td className="px-4 py-3">{row.in_transit ?? 0}</td>
                  <td className="px-4 py-3">
                    <input
                      type="number"
                      value={row.po_requirement || 0}
                      onChange={(e) => {
                        const value = Number(e.target.value);
                        setData(data.map(d => d.model === row.model ? { ...d, po_requirement: value } : d));
                        fetch(`${BASE}/api/wm-replenishment/save`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ model: row.model, po_requirement: value, remarks: row.remarks || "" })
                        });
                      }}
                      className="border rounded px-2 py-1 w-24"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      value={row.remarks ?? ""}
                      onBlur={(e) => {
                        const value = e.target.value;
                        fetch(`${BASE}/api/wm-replenishment/save`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ model: row.model, po_requirement: row.po_requirement || 0, remarks: value })
                        });
                      }}
                      className="border rounded px-2 py-1 w-full"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* PAGINATION */}
        <div className="flex justify-between items-center p-4 border-t">
          <button disabled={currentPage === 1} onClick={() => setCurrentPage((p) => p - 1)} className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50">Previous</button>
          <div>Page {currentPage} of {totalPages}</div>
          <button disabled={currentPage === totalPages} onClick={() => setCurrentPage((p) => p + 1)} className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50">Next</button>
        </div>
      </div>

    </div>
  );
}

function MetricCard({ title, value }) {
  return (
    <div className="px-3 py-2 bg-white rounded-lg shadow-sm border border-slate-100">
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{title}</div>
      <div className="text-base font-semibold text-slate-800">{value ?? "-"}</div>
    </div>
  );
}

function WMSOPModal({ open, onClose }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              How Clicktech (WM) Replenishment is Calculated
            </h2>
            <p className="text-xs text-slate-500 mt-1">Brand covered: White Mulberry</p>
          </div>
          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-slate-100 text-slate-700 text-xs rounded hover:bg-slate-200"
          >
            Close
          </button>
        </div>

        <div className="overflow-auto p-5 text-sm text-slate-700 space-y-4 leading-relaxed">

          <p className="text-slate-600">
            Tells you how many units to ship from the <b>Mother Warehouse</b> to <b>Clicktech</b> for each White Mulberry model.
          </p>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Top controls</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>Sales Window (From / To)</b> — Range from the last 12 available weeks (default: full last 12)</li>
              <li><b>Cover Weeks</b> — Weeks of stock you want at Clicktech (default 8)</li>
              <li><b>Category</b> filter and <b>Search</b> by model</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Columns</h3>
            <table className="w-full text-xs border-collapse">
              <tbody>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium w-36">Clicktech 3M Sales</td><td className="border border-slate-300 px-2 py-1">Units sold via <b>1p Sales</b> channel in the window</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Amazon 3M Sales</td><td className="border border-slate-300 px-2 py-1">Units sold via <b>Amazon</b> channel in the window</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Avg Weekly Sales</td><td className="border border-slate-300 px-2 py-1">(Clicktech + Amazon Sales) ÷ window weeks</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Estimated QTY</td><td className="border border-slate-300 px-2 py-1">Target at Clicktech = Avg Weekly × Cover Weeks</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Clicktech QTY</td><td className="border border-slate-300 px-2 py-1">Current Clicktech stock (1P channel from inventory snapshot)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Mother Warehouse</td><td className="border border-slate-300 px-2 py-1">Stock at your warehouse — what you can ship to Clicktech</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Open PO</td><td className="border border-slate-300 px-2 py-1">Open POs already raised (status = Open PO)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">In Transit</td><td className="border border-slate-300 px-2 py-1">In-transit PO units (status = In-Transit)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Deficiency</td><td className="border border-slate-300 px-2 py-1">Estimated − Clicktech QTY (≥ 0). The gap to fill.</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">PO Requirement</td><td className="border border-slate-300 px-2 py-1">Deficiency − (Open PO + In-Transit), <b>capped at Mother Warehouse stock</b></td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Remarks</td><td className="border border-slate-300 px-2 py-1">Free-form notes</td></tr>
              </tbody>
            </table>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Filter rules</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li>Brand counted: <b>White Mulberry</b> only</li>
              <li>Sales channels counted: <b>1p Sales + Amazon</b> only (other channels excluded)</li>
              <li>Inventory channels read: <code>1p</code> → Clicktech QTY, <code>ampm</code> → Mother Warehouse</li>
              <li>PO file rows used: <b>Open PO</b> and <b>In-Transit</b> delivery statuses</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Example</h3>
            <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
              FBA79175: sold 96 units over 12 weeks → AVG/WK = 8 →
              8-week target = 64 → Clicktech has 20 → Deficiency = 44 →
              Open PO 0 + In-Transit 10 → PO Req = 44 − 10 = 34 →
              Mother WH has 100 → <b>PO Req = 34</b>.
              <br/>
              <span className="text-slate-500">If Mother WH only had 20, PO Req would be capped at 20.</span>
            </p>
          </section>

        </div>
      </div>
    </div>
  );
}