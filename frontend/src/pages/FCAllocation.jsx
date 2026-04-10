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
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [selectedListingStatuses, setSelectedListingStatuses] = useState([]);

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "desc",
  });

  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;

  const [expandedRow, setExpandedRow] = useState(null);

  /* ============================================================
     DATA LOAD
  ============================================================ */

  useEffect(() => {
    console.log("CALLING API WITH ACCOUNT:", account);  // 👈 ADD THIS

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
const categories = useMemo(() => {
  const cats = [...new Set(data.map(r => r.category).filter(Boolean))];
  return cats.sort();
}, [data]);

const listingStatuses = useMemo(() => {
  const statuses = [...new Set(data.map(r => r.listing_status).filter(Boolean))];
  return statuses.sort();
}, [data]);

const filteredData = useMemo(() => {
  const q = search.toLowerCase();
  return data
    .filter((row) => selectedCategories.length === 0 || selectedCategories.includes(row.category))
    .filter((row) => selectedListingStatuses.length === 0 || selectedListingStatuses.includes(row.listing_status))
    .filter((row) => !q || row.sku?.toLowerCase().includes(q) || row.model?.toLowerCase().includes(q) || row.asin?.toLowerCase().includes(q));
}, [data, search, selectedCategories, selectedListingStatuses]);

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
    "category",
    "sku",
    "asin",
    "listing_status",
    "weekly_velocity",
    "total_units_sold",
    "fc_inventory",
    "ampm_inventory",
    "target_cover_units",
    "expected_units",
    "send_qty",
    "fill_pct",
    "velocity_flag",
    "fulfillment_center",
    "hazmat_type",
    "master_carton",
    "post_transfer_stock",
    "coverage_gap_units",
    "transfer_in",
  ];

  const columnLabels = {
    model: "MODEL",
    category: "CATEGORY",
    sku: "SKU",
    asin: "ASIN",
    listing_status: "LISTING STATUS",
    weekly_velocity: "AVG WEEKLY SALES",
    total_units_sold: "TOTAL SOLD",
    fc_inventory: "LEDGER STOCK",
    ampm_inventory: account === "Fossil" ? "FOSSIL SOH" : "AMPM INVENTORY",
    target_cover_units: "TARGET COVER UNITS",
    expected_units: "ORIGINAL REQUIRED",
    send_qty: "SEND QTY",
    fill_pct: "FILL %",
    velocity_flag: "VELOCITY FLAG",
    fulfillment_center: "FC",
    hazmat_type: "HAZMAT TYPE",
    master_carton: "MASTER CARTON",
    post_transfer_stock: "POST TRANSFER STOCK",
    coverage_gap_units: "COVERAGE GAP UNITS",
    transfer_in: "TRANSFER IN",
  };

  const headerRow = headers.map(c => columnLabels[c] || c.toUpperCase()).join(",");

  const rows = sortedData
    .map(row =>
      headers.map(col => {
        const val = row[col] ?? "";
        return `"${String(val).replace(/"/g, '""')}"`;
      }).join(",")
    )
    .join("\n");

  const blob = new Blob(
    [headerRow + "\n" + rows],
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
    <div className="space-y-4">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          Nexlev FC Allocation Intelligence
        </h1>
        <p className="text-slate-300 mt-2 text-sm">
          Final distribution planning from AMPM to fulfillment centers
        </p>
      </div>

      {/* FILTER PANEL */}
      <div className="card grid grid-cols-1 md:grid-cols-4 gap-3 py-3">
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
            placeholder="Search model, ASIN or SKU..."
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
    onChange={(e) => {
    console.log("DROPDOWN CHANGED TO:", e.target.value);
  setAccount(e.target.value);
}}
    className="mt-2 w-full px-4 py-2 border rounded-lg"
  >
    <option value="Nexlev">Nexlev</option>
    <option value="Viomi">Viomi</option>
    <option value="White Mulberry">White Mulberry</option>
    <option value="Audio Array">Audio Array</option>
    <option value="Fossil">Fossil</option>
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

{/* CATEGORY + STATUS FILTER */}
<div className="flex flex-wrap gap-2 items-center px-1">
  <span className="text-xs text-slate-400 uppercase">Category:</span>
  {categories.map(cat => (
    <button
      key={cat}
      onClick={() => setSelectedCategories(prev =>
        prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
      )}
      className={`px-3 py-1 text-xs rounded-full border transition ${
        selectedCategories.includes(cat)
          ? "bg-slate-900 text-white border-slate-900"
          : "bg-white text-slate-600 border-slate-300 hover:border-slate-600"
      }`}
    >
      {cat}
    </button>
  ))}
  {selectedCategories.length > 0 && (
    <button
      onClick={() => setSelectedCategories([])}
      className="px-3 py-1 text-xs rounded-full border border-red-300 text-red-500 hover:bg-red-50"
    >
      Clear
    </button>
  )}

  <span className="text-xs text-slate-300 mx-1">|</span>

  <span className="text-xs text-slate-400 uppercase">Status:</span>
  {listingStatuses.map(ls => {
    const activeStyle =
      ls === "Active" ? "bg-green-600 text-white border-green-600" :
      ls === "EOL"    ? "bg-red-600 text-white border-red-600" :
                       "bg-slate-900 text-white border-slate-900";
    const inactiveStyle =
      ls === "Active" ? "bg-white text-green-700 border-green-300 hover:border-green-600" :
      ls === "EOL"    ? "bg-white text-red-600 border-red-300 hover:border-red-500" :
                       "bg-white text-slate-600 border-slate-300 hover:border-slate-600";
    return (
      <button
        key={ls}
        onClick={() => setSelectedListingStatuses(prev =>
          prev.includes(ls) ? prev.filter(s => s !== ls) : [...prev, ls]
        )}
        className={`px-3 py-1 text-xs rounded-full border transition ${
          selectedListingStatuses.includes(ls) ? activeStyle : inactiveStyle
        }`}
      >
        {ls}
      </button>
    );
  })}
  {selectedListingStatuses.length > 0 && (
    <button
      onClick={() => setSelectedListingStatuses([])}
      className="px-3 py-1 text-xs rounded-full border border-red-300 text-red-500 hover:bg-red-50"
    >
      Clear
    </button>
  )}
</div>

      {/* KPI STRIP */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
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
          <div className="overflow-auto max-h-[75vh]">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 sticky top-0 z-20">
  <tr>
    <th onClick={() => toggleSort("model")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      Model {getSortArrow("model")}
    </th>
    <th onClick={() => toggleSort("category")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Category {getSortArrow("category")}</th>
    <th onClick={() => toggleSort("sku")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      SKU {getSortArrow("sku")}
    </th>
    <th onClick={() => toggleSort("asin")} className="px-4 py-3 cursor-pointer whitespace-nowrap">ASIN {getSortArrow("asin")}</th>
    <th onClick={() => toggleSort("weekly_velocity")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      Avg Weekly Sales {getSortArrow("weekly_velocity")}
    </th>
    <th onClick={() => toggleSort("total_units_sold")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Total Sold {getSortArrow("total_units_sold")}</th>
    <th onClick={() => toggleSort("fc_inventory")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      Ledger Stock {getSortArrow("fc_inventory")}
    </th>
    <th onClick={() => toggleSort("ampm_inventory")} className="px-4 py-3 cursor-pointer whitespace-nowrap">{account === "Fossil" ? "Fossil SOH" : "AMPM Inventory"} {getSortArrow("ampm_inventory")}</th>
    <th onClick={() => toggleSort("target_cover_units")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      Target Cover Units {getSortArrow("target_cover_units")}
    </th>
    <th onClick={() => toggleSort("expected_units")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      Original Required {getSortArrow("expected_units")}
    </th>
    <th onClick={() => toggleSort("send_qty")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      Send Qty {getSortArrow("send_qty")}
    </th>
    <th onClick={() => toggleSort("fill_pct")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      Fill % {getSortArrow("fill_pct")}
    </th>
    <th onClick={() => toggleSort("velocity_flag")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Velocity Flag {getSortArrow("velocity_flag")}</th>
    <th onClick={() => toggleSort("fulfillment_center")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      FC {getSortArrow("fulfillment_center")}
    </th>
    <th onClick={() => toggleSort("hazmat_type")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Hazmat Type {getSortArrow("hazmat_type")}</th>
    <th onClick={() => toggleSort("master_carton")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Master Carton {getSortArrow("master_carton")}</th>
  </tr>
</thead>

              <tbody>
                {paginatedData.map((row, i) => {
                  return (
                    <React.Fragment key={`${row.sku}-${row.fulfillment_center}-${i}`}>
                      <tr
                        key={i}
                        className={`border-b hover:bg-slate-50 transition cursor-pointer ${loadRowColor(getLoadStatus(row))}`}
                        onClick={() => setExpandedRow(i === expandedRow ? null : i)}
                      >
                        {/* Model */}
                        <td className="px-4 py-3">{row.model}</td>
                        {/* Category */}
                        <td className="px-4 py-3">{row.category || "-"}</td>
                        {/* SKU */}
                        <td className="px-4 py-3">{row.sku}</td>
                        {/* ASIN */}
                        <td className="px-4 py-3">{row.asin || "-"}</td>
                        {/* Avg Weekly Sales */}
                        <td className="px-4 py-3">{row.weekly_velocity ?? 0}</td>
                        {/* Total Sold */}
                        <td className="px-4 py-3">{row.total_units_sold ?? 0}</td>
                        {/* Ledger Stock */}
                        <td className="px-4 py-3">{row.fc_inventory ?? 0}</td>
                        {/* AMPM Inventory */}
                        <td className="px-4 py-3">{row.ampm_inventory ?? 0}</td>
                        {/* Target Cover Units */}
                        <td className="px-4 py-3">{row.target_cover_units ?? 0}</td>
                        {/* Original Required */}
                        <td className="px-4 py-3">{row.expected_units ?? 0}</td>
                        {/* Send Qty */}
                        <td className="px-4 py-3 font-semibold">{row.send_qty}</td>
                        {/* Fill % */}
                        <td className="px-4 py-3">{row.fill_pct ?? 0}%</td>
                        {/* Velocity Flag */}
                        <td className="px-4 py-3">
                          <span className={
                            row.velocity_flag === "SHORT_30%+"
                              ? "text-red-600 font-semibold"
                              : row.velocity_flag === "NO_REQUIREMENT"
                              ? "text-gray-500 font-semibold"
                              : "text-green-600"
                          }>
                            {row.velocity_flag || "NO_FLAG"}
                          </span>
                        </td>
                        {/* FC */}
                        <td className="px-4 py-3">{row.fulfillment_center}</td>
                        {/* Hazmat Type */}
                        <td className="px-4 py-3">{row.hazmat_type || "-"}</td>
                        {/* Master Carton */}
                        <td className="px-4 py-3">{row.master_carton || "-"}</td>
                      </tr>

                      {expandedRow === i && (
                        <tr>
                          <td colSpan="13" className="bg-slate-50 p-4 text-sm">
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
    <div className="p-5 bg-white border border-slate-100 rounded-xl shadow-sm hover:shadow-md transition">
      <div className="text-xs uppercase tracking-wider text-slate-400">
        {title}
      </div>
      <div className="text-2xl font-semibold mt-1 text-slate-800">
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
        {[1,2,3,4,5,6,7,8,9,10,11,12].map((w) => (
          <option key={w} value={w}>
            {w} Week{w > 1 ? "s" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}