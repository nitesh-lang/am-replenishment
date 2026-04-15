import { useEffect, useMemo, useState } from "react";

/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function ChinaReorder() {

  const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

  /* ============================================================
     STATE
  ============================================================ */

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [selectedBrand, setSelectedBrand] = useState("Nexlev");
  const [selectedMonths, setSelectedMonths] = useState(3);
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek, setToWeek] = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);
  const [selectedL0, setSelectedL0] = useState("");
  const [selectedL1, setSelectedL1] = useState("");


  // 👇 ADD HERE
  const [search, setSearch] = useState("");

  const [search, setSearch] = useState("");
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  /* Pagination */
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;

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
    setLoading(true);
    const params = new URLSearchParams({ brand: selectedBrand, months: selectedMonths });
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
  }, [selectedBrand, selectedMonths, fromWeek, toWeek]);

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
      <div className="rounded-2xl p-8 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          China Reorder Intelligence
        </h1>
        <p className="text-indigo-200 mt-2 text-sm">
          12-Week Sales vs Inventory Based Production Planning
        </p>
      </div>

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
          <select
            value={selectedBrand}
            onChange={(e) => {
              setCurrentPage(1);
              setSelectedBrand(e.target.value);
              setFromWeek(null);
              setToWeek(null);
              setAvailableWeeks([]);
              setSelectedL0("");
              setSelectedL1("");
            }}
            className="px-4 py-2 border rounded-lg"
          >
            <option value="Nexlev">Nexlev</option>
            <option value="Audio Array">Audio Array</option>
            <option value="Tonor">Tonor</option>
            <option value="White Mulberry">White Mulberry</option>
          </select>

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
                {["model", "last_12w_sales", "avg_weekly_sales", "current_inventory", "open_order_qty", "pipeline_qty", "suggested_reorder"]
                  .map((col) => (
                    <th
                      key={col}
                      onClick={() => toggleSort(col)}
                      className="px-4 py-3 cursor-pointer"
                    >
                      {{
                        "open_order_qty": "PO Yet to Pickup",
                        "pipeline_qty": "PO Picked Up",
                      }[col] || col} {getSortArrow(col)}
                    </th>
                  ))}
                <th onClick={() => toggleSort("status")} className="px-4 py-3 cursor-pointer">Status {getSortArrow("status")}</th>
              </tr>
            </thead>

            <tbody>
              {paginatedData.map((row, i) => {
                const status = getStatus(row);

                return (
                  <tr
                    key={i}
                    className={`${getRowColor(status)} hover:bg-slate-50`}
                  >
                    <td className="px-4 py-3 font-medium">{row.model}</td>
                    <td className="px-4 py-3">{row.last_12w_sales}</td>
                    <td className="px-4 py-3">
                      {row.avg_weekly_sales?.toFixed(2)}
                    </td>
                    <td className="px-4 py-3">{row.current_inventory}</td>
                    <td className="px-4 py-3 font-medium text-indigo-600">
                      {row.open_order_qty || 0}
                    </td>
                    <td className="px-4 py-3 font-medium text-purple-600">
                      {row.pipeline_qty || 0}
                    </td>
                    <td className="px-4 py-3 font-semibold text-indigo-700">
                      {Math.round(row.suggested_reorder)}
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
    <div className="p-5 bg-white rounded-xl shadow-sm border border-slate-100">
      <div className="text-xs uppercase tracking-wider text-slate-400">{title}</div>
      <div className="text-2xl font-semibold mt-1 text-slate-800">{value ?? "-"}</div>
    </div>
  );
}