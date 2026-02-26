import { useEffect, useMemo, useState } from "react";

/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function ChinaReorder() {

  /* ============================================================
     STATE
  ============================================================ */

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [selectedBrand, setSelectedBrand] = useState("Nexlev"); // 👈 ADD HERE
  const [selectedMonths, setSelectedMonths] = useState(3);

  const [search, setSearch] = useState("");
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  /* Pagination */
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 15;

  /* ============================================================
     DATA LOAD
  ============================================================ */

  useEffect(() => {
    setLoading(true);

    fetch(`https://am-replenishment.onrender.com/china-reorder/?brand=${selectedBrand}&months=${selectedMonths}`)
      .then((res) => res.json())
      .then((res) => {
        setData(Array.isArray(res) ? res : []);
      })
      .finally(() => setLoading(false));
  }, [selectedBrand, selectedMonths]);

  /* ============================================================
     FILTER
  ============================================================ */

  const filteredData = useMemo(() => {
    return data.filter((row) =>
      row.model?.toLowerCase().includes(search.toLowerCase())
    );
  }, [data, search]);

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
    if (row.suggested_reorder > 500) return "CRITICAL";
    if (row.weeks_cover < 8) return "LOW COVER";
    return "STABLE";
  }

  function getRowColor(status) {
    if (status === "CRITICAL") return "bg-red-50";
    if (status === "LOW COVER") return "bg-yellow-50";
    return "bg-emerald-50/40";
  }

  function getStatusBadge(status) {
    if (status === "CRITICAL")
      return "bg-red-100 text-red-700";
    if (status === "LOW COVER")
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
    <div className="space-y-10">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-indigo-900 via-indigo-800 to-indigo-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          China Reorder Intelligence
        </h1>
        <p className="text-indigo-200 mt-2 text-sm">
          12-Week Sales vs Inventory Based Production Planning
        </p>
      </div>

      {/* KPI SECTION */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <MetricCard title="Total Units to Reorder" value={Math.round(kpis.totalReorder)} />
        <MetricCard title="Avg Weeks Cover" value={kpis.avgCover?.toFixed(2)} />
        <MetricCard title="Total Models" value={kpis.models} />
      </div>

      {/* SEARCH + EXPORT */}
      <select
  value={selectedBrand}
  onChange={(e) => {
    setCurrentPage(1);
    setSelectedBrand(e.target.value);
  }}
      className="px-4 py-2 border rounded-lg mr-4"
      >
      <option value="Nexlev">Nexlev</option>
      <option value="Audio Array">Audio Array</option>
      <option value="Tonor">Tonor</option>
      <option value="White Mulberry">White Mulberry</option>
      </select>
      <select
      value={selectedMonths}
      onChange={(e) => {
        setCurrentPage(1);
        setSelectedMonths(Number(e.target.value));
        }}
        className="px-4 py-2 border rounded-lg"
        >
        <option value={1}>1 Month</option>
        <option value={2}>2 Months</option>
        <option value={3}>3 Months</option>
        <option value={4}>4 Months</option>
        <option value={5}>5 Months</option>
        <option value={6}>6 Months</option>
        </select>
      <div className="flex justify-between items-center">
        <input
          value={search}
          onChange={(e) => {
            setCurrentPage(1);
            setSearch(e.target.value);
          }}
          placeholder="Search model..."
          className="px-4 py-2 border rounded-lg w-64"
        />

        <button
          onClick={exportCSV}
          className="px-4 py-2 bg-indigo-900 text-white rounded-lg"
        >
          Export CSV
        </button>
      </div>

      {/* TABLE */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-auto max-h-[65vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-xs uppercase sticky top-0">
              <tr>
                {["model", "last_12w_sales", "avg_weekly_sales", "current_inventory", "weeks_cover", "suggested_reorder"]
                  .map((col) => (
                    <th
                      key={col}
                      onClick={() => toggleSort(col)}
                      className="px-4 py-3 cursor-pointer"
                    >
                      {col} {getSortArrow(col)}
                    </th>
                  ))}
                <th>Status</th>
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
                    <td className="px-4 py-3">{row.weeks_cover?.toFixed(1)}</td>
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
          >
            Previous
          </button>

          <div>
            Page {currentPage} of {totalPages}
          </div>

          <button
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage((p) => p + 1)}
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
    <div className="p-6 bg-white rounded-xl shadow-sm border">
      <div className="text-xs uppercase text-slate-400">{title}</div>
      <div className="text-3xl font-semibold mt-3">{value}</div>
    </div>
  );
}