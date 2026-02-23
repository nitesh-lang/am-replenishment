import { useEffect, useMemo, useState } from "react";
import { getReplenishment, getKPIs } from "../api/replenishment";

/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function Replenishment() {

  /* ============================================================
     STATE
  ============================================================ */

  const [fromWeek, setFromWeek] = useState(1);
  const [toWeek, setToWeek] = useState(8);
  const [replenishWeeks, setReplenishWeeks] = useState(8);
  const [account, setAccount] = useState("NEXLEV");

  const [kpis, setKpis] = useState(null);
  const [replenishment, setReplenishment] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [expandedRow, setExpandedRow] = useState(null);

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

    Promise.all([
      getKPIs(fromWeek, toWeek),
      getReplenishment(fromWeek, replenishWeeks, account),
    ])
      .then(([kpiRes, replRes]) => {
        setKpis(kpiRes);
        setReplenishment(Array.isArray(replRes) ? replRes : []);
      })
      .finally(() => setLoading(false));
  }, [fromWeek, toWeek, replenishWeeks, account]);

  /* ============================================================
     COLUMNS
  ============================================================ */

  const baseColumns = useMemo(() => {
    if (!replenishment.length) return [];
    return Object.keys(replenishment[0]);
  }, [replenishment]);

  const tableColumns = useMemo(() => {
    return ["status", ...baseColumns];
  }, [baseColumns]);

  /* ============================================================
     FILTER
  ============================================================ */

  const filteredData = useMemo(() => {
    return replenishment.filter((row) =>
      row.model?.toLowerCase().includes(search.toLowerCase())
    );
  }, [replenishment, search]);

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
    if (column === "status") return;

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

  function getRowStatus(row) {
    if (row.warehouse_shortfall > 0) return "CRITICAL";
    if (row.weeks_of_cover < replenishWeeks) return "LOW COVER";
    return "HEALTHY";
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
     HEALTH SUMMARY
  ============================================================ */

  const healthStats = useMemo(() => {
    let critical = 0;
    let low = 0;
    let healthy = 0;

    sortedData.forEach((row) => {
      const status = getRowStatus(row);
      if (status === "CRITICAL") critical++;
      else if (status === "LOW COVER") low++;
      else healthy++;
    });

    return { critical, low, healthy };
  }, [sortedData]);

  /* ============================================================
     CSV EXPORT
  ============================================================ */

  function exportCSV() {
    const headers = baseColumns.join(",");
    const rows = sortedData
      .map((row) =>
        baseColumns.map((col) => row[col]).join(",")
      )
      .join("\n");

    const blob = new Blob([headers + "\n" + rows], {
      type: "text/csv;charset=utf-8;",
    });

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "replenishment_export.csv";
    link.click();
  }

  /* ============================================================
     RENDER
  ============================================================ */

  return (
    <div className="space-y-10">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          Nexlev Replenishment Intelligence
        </h1>
        <p className="text-slate-300 mt-2 text-sm">
          Advanced replenishment & coverage analytics
        </p>
      </div>

    <div>
  <label className="text-xs uppercase text-slate-400">
    Account
  </label>
  <select
    value={account}
    onChange={(e) => setAccount(e.target.value)}
    className="mt-2 w-full px-4 py-2 border rounded-lg"
  >
    <option value="NEXLEV">Nexlev</option>
    <option value="VIOMI">Viomi</option>
  </select>
</div>

    {/* SALES WINDOW + REPLENISH WEEKS FILTER */}
<div className="card grid grid-cols-1 md:grid-cols-2 gap-6">
  <div>
  <label className="text-xs uppercase text-slate-400">
    Sales Window (Range)
  </label>

  <div className="grid grid-cols-2 gap-3 mt-2">
    <select
      value={fromWeek}
      onChange={(e) => {
        setCurrentPage(1);
        setFromWeek(Number(e.target.value));
      }}
      className="px-4 py-2 border rounded-lg"
    >
      {[...Array(12)].map((_, i) => (
        <option key={i+1} value={i+1}>
          From {i+1}
        </option>
      ))}
    </select>

    <select
      value={toWeek}
      onChange={(e) => {
        setCurrentPage(1);
        setToWeek(Number(e.target.value));
      }}
      className="px-4 py-2 border rounded-lg"
    >
      {[...Array(12)].map((_, i) => (
        <option key={i+1} value={i+1}>
          To {i+1}
        </option>
      ))}
    </select>
  </div>
</div>

  <div>
    <label className="text-xs uppercase tracking-wider text-slate-400">
      Replenish Weeks
    </label>
    <select
      value={replenishWeeks}
      onChange={(e) => {
        setCurrentPage(1);
        setReplenishWeeks(Number(e.target.value));
      }}
      className="mt-2 w-full px-4 py-2 border border-slate-200 rounded-lg"
    >
      {[1,2,3,4,5,6,7,8,9,10,11,12].map((w) => (
        <option key={w} value={w}>
          {w} Week{w > 1 ? "s" : ""}
        </option>
      ))}
    </select>
  </div>
</div>
      {/* KPI SECTION */}
      {kpis && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <AnimatedMetric
            title="Units to Replenish"
            value={kpis.total_units_to_replenish}
          />
          <AnimatedMetric
            title="Avg Weeks of Cover"
            value={kpis.avg_weeks_of_cover?.toFixed(2)}
          />
          <AnimatedMetric
            title="Filtered SKUs"
            value={sortedData.length}
          />
        </div>
      )}

      {/* HEALTH SUMMARY STRIP */}
      <div className="grid grid-cols-3 gap-6">
        <HealthCard label="Critical" value={healthStats.critical} color="red" />
        <HealthCard label="Low Cover" value={healthStats.low} color="yellow" />
        <HealthCard label="Healthy" value={healthStats.healthy} color="emerald" />
      </div>

      {/* EXPORT + SEARCH */}
      <div className="flex justify-between items-center">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search model..."
          className="px-4 py-2 border rounded-lg"
        />
        <button
          onClick={exportCSV}
          className="px-4 py-2 bg-slate-900 text-white rounded-lg"
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
                {tableColumns.map((col) => (
                  <th
                    key={col}
                    onClick={() => toggleSort(col)}
                    className="px-4 py-3 cursor-pointer"
                  >
                    {col} {getSortArrow(col)}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {paginatedData.map((row, i) => {
                const status = getRowStatus(row);
                return (
                  <>
                    <tr
                      key={i}
                      className={`${getRowColor(status)} hover:bg-slate-50`}
                      onClick={() => setExpandedRow(i === expandedRow ? null : i)}
                    >
                      {tableColumns.map((col) => {
                        if (col === "status")
                          return (
                            <td className="px-4 py-3">
                              <span className={`px-2 py-1 text-xs rounded ${getStatusBadge(status)}`}>
                                {status}
                              </span>
                            </td>
                          );

                        if (col === "required_units" && row[col] > 0)
                          return (
                            <td className="px-4 py-3 font-bold text-red-600">
                              {row[col]}
                            </td>
                          );

                        return <td className="px-4 py-3">{row[col]}</td>;
                      })}
                    </tr>

                    {/* EXPANDED ROW */}
                    {expandedRow === i && (
                      <tr>
                        <td colSpan={tableColumns.length} className="bg-slate-50 p-4 text-sm">
                          <div className="grid grid-cols-3 gap-6">
                            <div>
                              <strong>Warehouse Shortfall:</strong> {row.warehouse_shortfall}
                            </div>
                            <div>
                              <strong>Weeks of Cover:</strong> {row.weeks_of_cover}
                            </div>
                            <div>
                              <strong>Amazon Inventory:</strong> {row.amazon_inventory}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
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

function AnimatedMetric({ title, value }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    let start = 0;
    const end = Number(value) || 0;
    const duration = 800;
    const increment = end / (duration / 16);

    const timer = setInterval(() => {
      start += increment;
      if (start >= end) {
        setDisplay(end);
        clearInterval(timer);
      } else {
        setDisplay(Math.floor(start));
      }
    }, 16);

    return () => clearInterval(timer);
  }, [value]);

  return (
    <div className="p-6 bg-white rounded-xl shadow-sm border">
      <div className="text-xs uppercase text-slate-400">{title}</div>
      <div className="text-3xl font-semibold mt-3">{display}</div>
    </div>
  );
}

function HealthCard({ label, value, color }) {
  return (
    <div className={`p-6 rounded-xl bg-${color}-50 border border-${color}-200`}>
      <div className="text-sm text-slate-500">{label}</div>
      <div className="text-2xl font-semibold mt-2">{value}</div>
    </div>
  );
}