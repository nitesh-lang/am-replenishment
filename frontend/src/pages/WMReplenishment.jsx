import { useEffect, useMemo, useState } from "react";

export default function WMReplenishment() {

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [coverWeeks, setCoverWeeks] = useState(8);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: "asc" });
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 15;
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek, setToWeek] = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ cover_weeks: coverWeeks });
    if (fromWeek) params.append("from_week", fromWeek);
    if (toWeek) params.append("to_week", toWeek);
    fetch(`https://am-replenishment.onrender.com/api/wm-replenishment/?${params}`)
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
    <div className="space-y-10">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow-xl">
                <h1 className="text-3xl font-semibold">Clicktech Replenishment Intelligence</h1>
                <p className="text-slate-300 mt-2 text-sm">Clicktech / WM Inventory Planning</p>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <MetricCard title="Units Required" value={Math.round(kpis.totalRequired)} />
        <MetricCard title="Avg Weekly Sales" value={kpis.avgVelocity?.toFixed(2)} />
        <MetricCard title="Models" value={kpis.models} />
      </div>

      {/* SALES WINDOW + COVER WEEKS */}
      <div className="card grid grid-cols-1 md:grid-cols-2 gap-6">
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
      </div>

      {/* TABLE */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-auto max-h-[65vh]">
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
                      "ampm_inventory": "AMPM Inventory",
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
                        fetch("https://am-replenishment.onrender.com/api/wm-replenishment/save", {
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
                      defaultValue={row.remarks ?? ""}
                      onBlur={(e) => {
                        const value = e.target.value;
                        fetch("https://am-replenishment.onrender.com/api/wm-replenishment/save", {
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
          <button disabled={currentPage === 1} onClick={() => setCurrentPage((p) => p - 1)}>Previous</button>
          <div>Page {currentPage} of {totalPages}</div>
          <button disabled={currentPage === totalPages} onClick={() => setCurrentPage((p) => p + 1)}>Next</button>
        </div>
      </div>

    </div>
  );
}

function MetricCard({ title, value }) {
  return (
    <div className="p-6 bg-white rounded-xl shadow-sm border">
      <div className="text-xs uppercase text-slate-400">{title}</div>
      <div className="text-3xl font-semibold mt-3">{value ?? "-"}</div>
    </div>
  );
}