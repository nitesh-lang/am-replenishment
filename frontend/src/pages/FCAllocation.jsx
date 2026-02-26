import React, { useEffect, useMemo, useState } from "react";
import { getFCFinal } from "../api/replenishment";

/* ============================================================
   FC ALLOCATION – SAAS VERSION
============================================================ */

export default function FCAllocation() {

  /* ============================================================
     STATE
  ============================================================ */

  const [replenishWeeks, setReplenishWeeks] = useState(8);
  const [channel, setChannel] = useState("All");
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [account, setAccount] = useState("Nexlev");

  const [search, setSearch] = useState("");

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "desc",
  });

  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 12;

  const [expandedRow, setExpandedRow] = useState(null);

  /* ============================================================
     DATA LOAD
  ============================================================ */

  useEffect(() => {
    setLoading(true);

    getFCFinal(replenishWeeks, channel, account)
      .then((res) => {
        console.log("FC API RESPONSE:", res);
        console.log("SAMPLE ROW:", res?.[0]);

        setData(Array.isArray(res) ? res : []);
        
      })
      .finally(() => setLoading(false));
  }, [replenishWeeks, channel, account]);

  /* ============================================================
     FILTER
  ============================================================ */
const filteredData = useMemo(() => {
  if (!search) return data;

  return data.filter((row) =>
    row.sku?.toLowerCase().includes(search.toLowerCase()) ||
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

    const totalUnits = filteredData.reduce(
      (sum, row) => sum + (row.send_qty || 0),
      0
    );

    const uniqueSKUs = new Set(filteredData.map((r) => r.sku)).size;
    const uniqueFCs = new Set(filteredData.map((r) => r.fulfillment_center)).size;

    const fcLoad = {};

    filteredData.forEach((row) => {
      const fc = row.fulfillment_center;
      fcLoad[fc] = (fcLoad[fc] || 0) + (row.send_qty || 0);
    });

    const topFC =
      Object.entries(fcLoad).sort((a, b) => b[1] - a[1])[0]?.[0] || "-";

    return { totalUnits, uniqueSKUs, uniqueFCs, topFC };

  }, [filteredData]);

  /* ============================================================
     LOAD STATUS LOGIC
  ============================================================ */

  function getLoadStatus(row) {
    if (row.send_qty > 500) return "HIGH LOAD";
    if (row.send_qty < 50) return "LOW LOAD";
    return "BALANCED";
  }

  function loadBadge(status) {
    if (status === "HIGH LOAD")
      return "bg-red-100 text-red-700";
    if (status === "LOW LOAD")
      return "bg-yellow-100 text-yellow-700";
    return "bg-emerald-100 text-emerald-700";
  }

  function loadRowColor(status) {
    if (status === "HIGH LOAD") return "bg-red-50";
    if (status === "LOW LOAD") return "bg-yellow-50";
    return "bg-emerald-50/40";
  }

  /* ============================================================
     EXPORT CSV
  ============================================================ */
function exportCSV() {
  const headers = [
    "model",
    "sku",
    "fulfillment_center",
    "weekly_velocity",
    "fc_inventory",
    "transfer_in",
    "target_cover_units",
    "post_transfer_stock",
    "coverage_gap_units",
    "send_qty",
    "expected_units",
    "velocity_fill_ratio",
    "fill_pct",
    "velocity_flag"
  ];

  const rows = filteredData
    .map(row =>
      headers.map(col => row[col]).join(",")
    )
    .join("\n");

  const blob = new Blob(
    [headers.join(",") + "\n" + rows],
    { type: "text/csv;charset=utf-8;" }
  );

  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "fc_allocation_full_export.csv";
  link.click();
}

  /* ============================================================
     RENDER
  ============================================================ */

  return (
    <div className="space-y-10">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          Nexlev FC Allocation Intelligence
        </h1>
        <p className="text-slate-300 mt-2 text-sm">
          Final distribution planning from AMPM to fulfillment centers
        </p>
      </div>

      {/* FILTER PANEL */}
      <div className="card grid grid-cols-1 md:grid-cols-4 gap-6">
        <FilterSelect
          label="Replenish Weeks"
          value={replenishWeeks}
          onChange={(v) => setReplenishWeeks(v)}
        />
        <div>
          <label className="text-xs uppercase text-slate-400">
            Search SKU/Model
          </label>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mt-2 w-full px-4 py-2 border rounded-lg"
          />
        </div>
        {/* Account */}
<div>
  <label className="text-xs uppercase text-slate-400">
    Account
  </label>
  <select
    value={account}
    onChange={(e) => setAccount(e.target.value)}
    className="mt-2 w-full px-4 py-2 border rounded-lg"
  >
    <option value="Nexlev">Nexlev</option>
    <option value="Viomi">Viomi</option>
  </select>
</div>

{/* Sales Channel */}
<div>
  <label className="text-xs uppercase text-slate-400">
    Sales Channel
  </label>
  <select
    value={channel}
    onChange={(e) => setChannel(e.target.value)}
    className="mt-2 w-full px-4 py-2 border rounded-lg"
  >
    <option value="All">All</option>
    <option value="amazon.in">Amazon.in</option>
    <option value="Non-Amazon">MCF (Non-Amazon)</option>
  </select>
</div>

<div className="flex items-end">
  <button
    onClick={exportCSV}
    className="px-4 py-2 bg-slate-900 text-white rounded-lg"
  >
    Export CSV
  </button>
</div>
</div>

      {/* KPI STRIP */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <MetricCard title="Total Units" value={kpis.totalUnits} />
        <MetricCard title="Unique SKUs" value={kpis.uniqueSKUs} />
        <MetricCard title="FC Count" value={kpis.uniqueFCs} />
        <MetricCard title="Top FC" value={kpis.topFC} />
      </div>

      {/* TABLE */}
      <div className="card p-0 overflow-hidden">

        {loading ? (
          <div className="p-8 text-slate-400">Loading data...</div>
        ) : (
          <div className="overflow-auto max-h-[65vh]">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 sticky top-0 z-20">
  <tr>
    <th className="px-4 py-3">Load</th>

    <th onClick={() => toggleSort("model")} className="px-4 py-3 cursor-pointer">
  Model {getSortArrow("model")}
</th>

    <th onClick={() => toggleSort("sku")} className="px-4 py-3 cursor-pointer">
      SKU {getSortArrow("sku")}
    </th>

    <th onClick={() => toggleSort("fulfillment_center")} className="px-4 py-3 cursor-pointer">
      FC {getSortArrow("fulfillment_center")}
    </th>

    <th onClick={() => toggleSort("send_qty")} className="px-4 py-3 cursor-pointer">
      Send Qty {getSortArrow("send_qty")}
    </th>

    <th onClick={() => toggleSort("weekly_velocity")} className="px-4 py-3 cursor-pointer">
      Avg Weekly Sales {getSortArrow("weekly_velocity")}
    </th>

    <th onClick={() => toggleSort("fc_inventory")} className="px-4 py-3 cursor-pointer">
      Ledger Stock {getSortArrow("fc_inventory")}
    </th>

    <th onClick={() => toggleSort("target_cover_units")} className="px-4 py-3 cursor-pointer">
      Target Cover Units {getSortArrow("target_cover_units")}
    </th>

    <th onClick={() => toggleSort("expected_units")} className="px-4 py-3 cursor-pointer">
      Expected Units {getSortArrow("expected_units")}
    </th>

    <th onClick={() => toggleSort("velocity_fill_ratio")} className="px-4 py-3 cursor-pointer">
      Fill %
    </th>

    <th className="px-4 py-3">
      Velocity Flag
    </th>
  </tr>
</thead>

              <tbody>
                {paginatedData.map((row, i) => {
                  const status = getLoadStatus(row);

                  return (
                    <React.Fragment key={`${row.sku}-${row.fulfillment_center}-${i}`}>
                      <tr
                        key={i}
                        className={`border-b hover:bg-slate-50 transition cursor-pointer ${loadRowColor(status)}`}
                        onClick={() =>
                          setExpandedRow(i === expandedRow ? null : i)
                        }
                      >
                        <td className="px-4 py-3">
                          <span
                            className={`px-2 py-1 text-xs rounded ${loadBadge(status)}`}
                          >
                            {status}
                          </span>
                        </td>
                        <td className="px-4 py-3">{row.model}</td>
                        <td className="px-4 py-3">{row.sku}</td>
                        <td className="px-4 py-3">{row.fulfillment_center}</td>
                        <td className="px-4 py-3 font-semibold">
                          {row.send_qty}
                        </td>
                        <td className="px-4 py-3">
  {row.weekly_velocity ?? 0}
</td>

<td className="px-4 py-3">
  {row.fc_inventory ?? 0}
</td>

<td className="px-4 py-3">
  {row.target_cover_units ?? 0}
</td>

<td className="px-4 py-3">
  {row.expected_units ?? 0}
</td>

<td className="px-4 py-3">
  {row.fill_pct ?? 0}%
</td>

<td className="px-4 py-3">
  <span className={
    row.velocity_flag === "SHORTFALL_30%+"
      ? "text-red-600 font-semibold"
      : row.velocity_flag === "NO_DEMAND"
      ? "text-gray-500 font-semibold"
      : "text-green-600"
  }>
    {row.velocity_flag || "NO_FLAG"}
  </span>
</td>
                      </tr>

                      {expandedRow === i && (
                        <tr>
                          <td colSpan="11" className="bg-slate-50 p-4 text-sm">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">

  <div>
    <strong>Shipment Planned:</strong>
    <div className="mt-1">{row.planned_shipment_qty ?? 0}</div>
  </div>

  <div>
    <strong>Inventory Ledger Balance:</strong>
    <div className="mt-1">{row.ledger_balance ?? 0}</div>
  </div>

  <div>
    <strong>Target Cover Units:</strong>
    <div className="mt-1">{row.target_cover_units ?? 0}</div>
  </div>

  <div>
    <strong>Final Allocated (Send Qty):</strong>
    <div className="mt-1 font-semibold">{row.send_qty}</div>
  </div>

</div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

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
    <div className="p-6 bg-white border rounded-xl shadow-sm hover:shadow-md transition">
      <div className="text-xs uppercase text-slate-400">
        {title}
      </div>
      <div className="text-2xl font-semibold mt-3">
        {value ?? "-"}
      </div>
    </div>
  );
}

function FilterSelect({ label, value, onChange }) {
  return (
    <div>
      <label className="text-xs uppercase text-slate-400">
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