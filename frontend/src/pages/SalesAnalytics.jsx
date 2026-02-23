import { useEffect, useMemo, useState } from "react";
import { getReplenishment } from "../api/replenishment";

/* ============================================================
   SALES ANALYTICS – SAAS VERSION
============================================================ */

export default function SalesAnalytics() {

  /* ============================================================
     STATE
  ============================================================ */

  const [salesWindow, setSalesWindow] = useState(4);
  const [replenishWeeks, setReplenishWeeks] = useState(8);

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "desc",
  });

  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 10;

  const [expandedRow, setExpandedRow] = useState(null);

  /* ============================================================
     DATA LOAD
  ============================================================ */

  useEffect(() => {
    setLoading(true);

    getReplenishment(salesWindow, replenishWeeks)
      .then((res) => {
        setData(Array.isArray(res) ? res : []);
      })
      .finally(() => setLoading(false));
  }, [salesWindow, replenishWeeks]);

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
      const aVal = a[sortConfig.key] || 0;
      const bVal = b[sortConfig.key] || 0;
      return (aVal - bVal) * direction;
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

  /* ============================================================
     PAGINATION
  ============================================================ */

  const totalPages = Math.ceil(sortedData.length / rowsPerPage);

  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return sortedData.slice(start, start + rowsPerPage);
  }, [sortedData, currentPage]);

  /* ============================================================
     KPI CALCULATIONS
  ============================================================ */

  const kpis = useMemo(() => {
    let totalSales = 0;
    let totalInventory = 0;

    filteredData.forEach((row) => {
      totalSales += row.sales_velocity || 0;
      totalInventory += row.amazon_inventory || 0;
    });

    const coverage =
      totalSales > 0
        ? (totalInventory / totalSales).toFixed(2)
        : 0;

    const topSKU =
      filteredData.sort(
        (a, b) => (b.sales_velocity || 0) - (a.sales_velocity || 0)
      )[0]?.model || "-";

    return { totalSales, totalInventory, coverage, topSKU };
  }, [filteredData]);

  /* ============================================================
     HEALTH LOGIC
  ============================================================ */

  function getHealth(row) {
    if ((row.amazon_inventory || 0) > (row.sales_velocity || 0) * 4)
      return "OVERSTOCK";

    if ((row.amazon_inventory || 0) < (row.sales_velocity || 0))
      return "RISK";

    return "BALANCED";
  }

  function healthBadge(status) {
    if (status === "OVERSTOCK")
      return "bg-blue-100 text-blue-700";

    if (status === "RISK")
      return "bg-red-100 text-red-700";

    return "bg-emerald-100 text-emerald-700";
  }

  /* ============================================================
     EXPORT
  ============================================================ */

  function exportCSV() {
    const headers = ["model", "sales_velocity", "amazon_inventory"];
    const rows = filteredData
      .map((row) =>
        headers.map((col) => row[col]).join(",")
      )
      .join("\n");

    const blob = new Blob(
      [headers.join(",") + "\n" + rows],
      { type: "text/csv;charset=utf-8;" }
    );

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "sales_analytics_export.csv";
    link.click();
  }

  /* ============================================================
     RENDER
  ============================================================ */

  return (
    <div className="space-y-10">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-indigo-900 via-slate-800 to-indigo-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          Nexlev Sales Intelligence
        </h1>
        <p className="text-slate-300 mt-2 text-sm">
          Sales velocity vs Amazon inventory performance analytics
        </p>
      </div>

      {/* FILTERS */}
      <div className="card grid grid-cols-1 md:grid-cols-3 gap-6">
        <FilterSelect
          label="Sales Window"
          value={salesWindow}
          onChange={(v) => setSalesWindow(v)}
        />
        <FilterSelect
          label="Replenish Weeks"
          value={replenishWeeks}
          onChange={(v) => setReplenishWeeks(v)}
        />
        <div>
          <label className="text-xs uppercase tracking-wider text-slate-400">
            Search Model
          </label>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mt-2 w-full px-4 py-2 border rounded-lg"
          />
        </div>
      </div>

      {/* KPI CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <MetricCard title="Total Sales" value={kpis.totalSales} />
        <MetricCard title="Total Inventory" value={kpis.totalInventory} />
        <MetricCard title="Coverage Ratio" value={kpis.coverage} />
        <MetricCard title="Top SKU" value={kpis.topSKU} />
      </div>

      {/* EXPORT BUTTON */}
      <div className="flex justify-end">
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
            <thead className="bg-slate-100 sticky top-0">
              <tr>
                <th className="px-4 py-3">Health</th>
                <th
                  className="px-4 py-3 cursor-pointer"
                  onClick={() => toggleSort("model")}
                >
                  Model
                </th>
                <th
                  className="px-4 py-3 cursor-pointer"
                  onClick={() => toggleSort("sales_velocity")}
                >
                  Sales
                </th>
                <th
                  className="px-4 py-3 cursor-pointer"
                  onClick={() => toggleSort("amazon_inventory")}
                >
                  Inventory
                </th>
              </tr>
            </thead>

            <tbody>
              {paginatedData.map((row, i) => {
                const health = getHealth(row);

                return (
                  <>
                    <tr
                      key={i}
                      className="border-b hover:bg-slate-50 cursor-pointer"
                      onClick={() =>
                        setExpandedRow(i === expandedRow ? null : i)
                      }
                    >
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-1 text-xs rounded ${healthBadge(
                            health
                          )}`}
                        >
                          {health}
                        </span>
                      </td>
                      <td className="px-4 py-3">{row.model}</td>
                      <td className="px-4 py-3 font-semibold">
                        {row.sales_velocity}
                      </td>
                      <td className="px-4 py-3">
                        {row.amazon_inventory}
                      </td>
                    </tr>

                    {expandedRow === i && (
                      <tr>
                        <td
                          colSpan="4"
                          className="bg-slate-50 p-4 text-sm"
                        >
                          <div className="grid grid-cols-3 gap-6">
                            <div>
                              <strong>Sales Velocity:</strong>{" "}
                              {row.sales_velocity}
                            </div>
                            <div>
                              <strong>Amazon Inventory:</strong>{" "}
                              {row.amazon_inventory}
                            </div>
                            <div>
                              <strong>Coverage Weeks:</strong>{" "}
                              {(
                                (row.amazon_inventory || 0) /
                                (row.sales_velocity || 1)
                              ).toFixed(2)}
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

function MetricCard({ title, value }) {
  return (
    <div className="p-6 bg-white border rounded-xl shadow-sm">
      <div className="text-xs uppercase text-slate-400">
        {title}
      </div>
      <div className="text-2xl font-semibold mt-3">
        {value}
      </div>
    </div>
  );
}

function FilterSelect({ label, value, onChange }) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-slate-400">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full px-4 py-2 border rounded-lg"
      >
        {[1,2,3,4,5,6,7,8].map((w) => (
          <option key={w} value={w}>
            {w} Week{w > 1 ? "s" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}