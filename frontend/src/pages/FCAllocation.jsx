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
  // ISO-week numbers available under data/input/FBA Sales/Week N/ — populated from API.
  const [availableWeeks, setAvailableWeeks] = useState([]);
  // From/To pickers operate over actual ISO week numbers (e.g. 12..23).
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek, setToWeek]     = useState(null);
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

  // Fossil editable fields: keyed by "sku|fc"
  const [fossilEdits, setFossilEdits] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  // SOP help modal
  const [sopOpen, setSopOpen] = useState(false);

  const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

  // Fossil cluster mapping
  const FC_CLUSTER = {
    BLR5:"BLR", BLR7:"BLR", BLR8:"BLR",
    BOM4:"BOM", BOM5:"BOM", BOM7:"BOM", AMD2:"BOM", PNQ3:"BOM", ISK3:"BOM",
    MAA4:"TN",  CJB1:"TN",
    DEL2:"DEL", DEL4:"DEL", DEL5:"DEL", DED4:"DEL", LKO1:"DEL",
    HYD3:"TEL", HYD8:"TEL",
    CCX1:"WB",
  };

  function getFossilKey(row) { return `${row.sku}|${row.fulfillment_center}`; }

  function getFossilField(row, field) {
    const key = getFossilKey(row);
    return fossilEdits[key]?.[field] ?? row[field];
  }

  function setFossilField(row, field, value) {
    const key = getFossilKey(row);
    setFossilEdits(prev => ({
      ...prev,
      [key]: { ...prev[key], [field]: value }
    }));
  }

  async function saveFossilInputs() {
    setSaving(true);
    setSaveMsg("");
    try {
      // Save per-FC row data
      const rowPayload = sortedData.map(row => {
        const key = getFossilKey(row);
        const edits = fossilEdits[key] || {};
        return {
          sku: row.sku,
          fulfillment_center: row.fulfillment_center,
          po_requirement: parseInt(edits.send_qty ?? row.send_qty ?? 0) || 0,
          remarks: edits.remarks ?? row.remarks ?? "",
        };
      });
      await fetch(`${BASE}/fc-final-allocation/fossil-save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(rowPayload),
      });

      // Save cluster PO — collect unique sku+cluster combos across all visible rows
      const clusterMap = {};
      sortedData.forEach(row => {
        const cluster = FC_CLUSTER[row.fulfillment_center?.toUpperCase()] || "-";
        if (cluster === "-") return;
        const clusterKey = `${row.sku}|${cluster}`;
        if (!clusterMap[clusterKey]) {
          const val = fossilEdits[clusterKey]?.cluster_po ?? row.cluster_po ?? 0;
          clusterMap[clusterKey] = { sku: row.sku, cluster, cluster_po: parseInt(val) || 0 };
        }
      });

      const clusterPayload = Object.values(clusterMap);
      if (clusterPayload.length > 0) {
        await fetch(`${BASE}/fc-final-allocation/fossil-cluster-save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(clusterPayload),
        });
      }

      setSaveMsg(`✅ Saved`);
    } catch (e) {
      setSaveMsg("❌ Save failed");
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(""), 3000);
    }
  }

  /* ============================================================
     DATA LOAD
  ============================================================ */

  useEffect(() => {
    setLoading(true);
    setFossilEdits({});
    // Default sales-window fallback = number of weeks currently selected (or all loaded).
    const fallbackWindow = (fromWeek != null && toWeek != null)
      ? Math.abs(Number(toWeek) - Number(fromWeek)) + 1
      : (availableWeeks.length || 12);
    getFCFinal(replenishWeeks, channel, account, fallbackWindow, fromWeek, toWeek)
      .then((res) => {
        // Response shape: {data: [...], available_weeks: [12,13,...]}.
        // Tolerate older shapes (array-only, or number-valued available_weeks).
        const rows = Array.isArray(res) ? res : (res?.data ?? []);
        let availList = null;
        if (res && typeof res === "object") {
          if (Array.isArray(res.available_weeks)) {
            availList = res.available_weeks.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
          } else if (typeof res.available_weeks === "number") {
            // Backward-compat: server returned just the count → fabricate 1..N.
            availList = Array.from({ length: res.available_weeks }, (_, i) => i + 1);
          }
        }
        if (availList && availList.length) {
          setAvailableWeeks(availList);
          // Initialise/clamp From/To to the loaded range on first load or when out of bounds.
          const lo = availList[0];
          const hi = availList[availList.length - 1];
          if (fromWeek == null || !availList.includes(Number(fromWeek))) setFromWeek(lo);
          if (toWeek   == null || !availList.includes(Number(toWeek)))   setToWeek(hi);
        }
        setData(rows);

        // Pre-populate edits from DB values so inputs show saved data after refresh
        if (account === "Fossil" && rows.length > 0) {
          const preloaded = {};
          rows.forEach(row => {
            const key = `${row.sku}|${row.fulfillment_center}`;
            preloaded[key] = {
              send_qty:     row.send_qty ?? 0,
              remarks:      row.remarks ?? "",
            };
            // cluster PO
            const cluster = FC_CLUSTER[row.fulfillment_center?.toUpperCase()] || "-";
            if (cluster !== "-") {
              const clusterKey = `${row.sku}|${cluster}`;
              if (!preloaded[clusterKey]?.cluster_po) {
                preloaded[clusterKey] = {
                  ...preloaded[clusterKey],
                  cluster_po: row.cluster_po ?? 0,
                };
              }
            }
          });
          setFossilEdits(preloaded);
        }
      })
      .finally(() => setLoading(false));
  }, [replenishWeeks, channel, account, fromWeek, toWeek]);

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
  const fossilHeaders = [
    "model", "assortment", "sku", "asin",
    "fulfillment_center", "cluster",
    "fc_inventory", "ampm_inventory", "b2b_inventory",
    "weekly_velocity", "total_units_sold",
    "in_transit_qty", "open_po_qty",
    "send_qty", "cluster_po", "cluster_in_transit",
    "master_carton", "remarks",
  ];

  const defaultHeaders = [
    "model", "category", "sku", "asin", "listing_status",
    "weekly_velocity", "total_units_sold", "fc_inventory", "ampm_inventory", "b2b_inventory",
    "target_cover_units", "expected_units", "send_qty",
    "fill_pct", "velocity_flag", "fulfillment_center",
    "hazmat_type", "master_carton",
    "post_transfer_stock", "coverage_gap_units", "transfer_in",
  ];

  const headers = account === "Fossil" ? fossilHeaders : defaultHeaders;

  const columnLabels = {
    model: "MODEL",
    category: "CATEGORY",
    assortment: "ASSORTMENT",
    sku: "SKU",
    asin: "ASIN",
    listing_status: "LISTING STATUS",
    weekly_velocity: "AVG WEEKLY SALES",
    total_units_sold: "TOTAL SOLD",
    fc_inventory: "FC SOH",
    ampm_inventory: account === "Fossil" ? "FOSSIL SOH" : "Mother Warehouse",
    b2b_inventory: "B2B INVENTORY",
    target_cover_units: "TARGET COVER UNITS",
    expected_units: "ORIGINAL REQUIRED",
    send_qty: account === "Fossil" ? "PO REQUIREMENT" : "To Send QTY",
    fill_pct: "FILL %",
    velocity_flag: "VELOCITY FLAG",
    fulfillment_center: "FC",
    hazmat_type: "HAZMAT TYPE",
    master_carton: "MASTER CARTON",
    cluster: "CLUSTER",
    cluster_po: "CLUSTER PO",
    cluster_in_transit: "CLUSTER IN-TRANSIT",
    remarks: "REMARKS",
    in_transit_qty: "IN-TRANSIT QTY",
    open_po_qty: "OPEN PO QTY",
    coverage_gap_units: "COVERAGE GAP UNITS",
    transfer_in: "TRANSFER IN",
  };

  const headerRow = headers.map(c => columnLabels[c] || c.toUpperCase()).join(",");

  const rows = sortedData
    .map(row => {
      // For Fossil, pick up edits if present
      const getVal = (col) => {
        if (account === "Fossil") {
          const key = `${row.sku}|${row.fulfillment_center}`;
          const clusterKey = `${row.sku}|${FC_CLUSTER[row.fulfillment_center?.toUpperCase()] || "-"}`;
          if (col === "send_qty")    return fossilEdits[key]?.send_qty     ?? row[col] ?? "";
          if (col === "master_carton") return fossilEdits[key]?.master_carton ?? row[col] ?? 24;
          if (col === "remarks")     return fossilEdits[key]?.remarks      ?? row[col] ?? "";
          if (col === "cluster")     return FC_CLUSTER[row.fulfillment_center?.toUpperCase()] || "-";
          if (col === "cluster_po")  {
            if (row.cluster_po === null || row.cluster_po === undefined) return "";
            return fossilEdits[clusterKey]?.cluster_po ?? row[col] ?? 0;
          }
          if (col === "cluster_in_transit") return (row.cluster_in_transit === null || row.cluster_in_transit === undefined) ? "" : (row[col] ?? "");
          if (col === "cluster_total") return (row.cluster_total === null || row.cluster_total === undefined) ? "" : (row[col] ?? "");
        }
        return row[col] ?? "";
      };
      return headers.map(col => `"${String(getVal(col)).replace(/"/g, '""')}"`).join(",");
    })
    .join("\n");

  const blob = new Blob(
    [headerRow + "\n" + rows],
    { type: "text/csv;charset=utf-8;" }
  );

  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = account === "Fossil" ? "fossil_fc_allocation.csv" : "fc_allocation_full_export.csv";
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
          <h1 className="text-lg font-semibold">FC Allocation Intelligence</h1>
          <p className="text-slate-300 text-xs">Mother Warehouse → fulfillment centers</p>
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
      <FCAllocationSOPModal open={sopOpen} onClose={() => setSopOpen(false)} />

      {/* FILTER PANEL */}
      <div className="card grid grid-cols-1 md:grid-cols-5 gap-3 py-3">
        {/* Sales Window — From / To range over actual ISO week numbers loaded */}
        <div>
          <label className="text-xs uppercase text-slate-400">
            Sales Window (Range)
          </label>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <select
              value={fromWeek ?? ""}
              onChange={(e) => {
                setCurrentPage(1);
                setFromWeek(Number(e.target.value));
              }}
              className="px-2 py-2 border rounded-lg text-sm"
              disabled={!availableWeeks.length}
            >
              {availableWeeks.map((w) => (
                <option key={`from-${w}`} value={w}>From Wk {w}</option>
              ))}
            </select>
            <select
              value={toWeek ?? ""}
              onChange={(e) => {
                setCurrentPage(1);
                setToWeek(Number(e.target.value));
              }}
              className="px-2 py-2 border rounded-lg text-sm"
              disabled={!availableWeeks.length}
            >
              {availableWeeks.map((w) => (
                <option key={`to-${w}`} value={w}>To Wk {w}</option>
              ))}
            </select>
          </div>
        </div>
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
    <option value="Non-Amazon">D2C</option>
  </select>
</div>

<div className="flex items-end justify-end gap-2 md:col-span-5">
  <button
    onClick={exportCSV}
    className="px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition"
  >
    Export CSV
  </button>
  {account === "Fossil" && (
    <button
      onClick={saveFossilInputs}
      disabled={saving}
      className="px-4 py-2 bg-emerald-700 text-white rounded-lg disabled:opacity-50 hover:bg-emerald-800 transition"
    >
      {saving ? "Saving..." : "Save"}
    </button>
  )}
  {account === "Fossil" && (
    <button
      onClick={async () => {
        if (!window.confirm("Reset all saved PO requirements, cluster PO and remarks? Fresh calculations will show.")) return;
        await fetch(`${BASE}/fc-final-allocation/fossil-reset`, { method: "POST" });
        setFossilEdits({});
        setSaveMsg("✅ Reset complete");
        setTimeout(() => setSaveMsg(""), 3000);
        window.location.reload();
      }}
      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition"
    >
      Reset
    </button>
  )}
  {saveMsg && <span className="text-sm font-medium text-slate-600">{saveMsg}</span>}
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
    {account === "Fossil"
      ? <th onClick={() => toggleSort("assortment")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Assortment {getSortArrow("assortment")}</th>
      : <th onClick={() => toggleSort("category")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Category {getSortArrow("category")}</th>
    }
    <th onClick={() => toggleSort("sku")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      SKU {getSortArrow("sku")}
    </th>
    <th onClick={() => toggleSort("asin")} className="px-4 py-3 cursor-pointer whitespace-nowrap">ASIN {getSortArrow("asin")}</th>
    {account === "Fossil" && <th onClick={() => toggleSort("fulfillment_center")} className="px-4 py-3 cursor-pointer whitespace-nowrap">FC {getSortArrow("fulfillment_center")}</th>}
    {account === "Fossil" && <th onClick={() => toggleSort("cluster")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Cluster {getSortArrow("cluster")}</th>}
    <th onClick={() => toggleSort("fc_inventory")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      FC SOH {getSortArrow("fc_inventory")}
    </th>
    <th onClick={() => toggleSort("ampm_inventory")} className="px-4 py-3 cursor-pointer whitespace-nowrap">{account === "Fossil" ? "Fossil SOH" : "Mother Warehouse"} {getSortArrow("ampm_inventory")}</th>
    <th onClick={() => toggleSort("b2b_inventory")} className="px-4 py-3 cursor-pointer whitespace-nowrap">B2B Inv {getSortArrow("b2b_inventory")}</th>
    <th onClick={() => toggleSort("weekly_velocity")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      Avg Weekly Sales {getSortArrow("weekly_velocity")}
    </th>
    <th onClick={() => toggleSort("total_units_sold")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Total Sold {getSortArrow("total_units_sold")}</th>
    {account === "Fossil" && <th onClick={() => toggleSort("in_transit_qty")} className="px-4 py-3 cursor-pointer whitespace-nowrap text-amber-700">In-Transit {getSortArrow("in_transit_qty")}</th>}
    {account === "Fossil" && <th onClick={() => toggleSort("open_po_qty")} className="px-4 py-3 cursor-pointer whitespace-nowrap text-blue-700">Open PO {getSortArrow("open_po_qty")}</th>}
    <th onClick={() => toggleSort("target_cover_units")} className={`px-4 py-3 cursor-pointer whitespace-nowrap ${account === "Fossil" ? "hidden" : ""}`}>
      Target Cover Units {getSortArrow("target_cover_units")}
    </th>
    <th onClick={() => toggleSort("expected_units")} className={`px-4 py-3 cursor-pointer whitespace-nowrap ${account === "Fossil" ? "hidden" : ""}`}>
      Original Required {getSortArrow("expected_units")}
    </th>
    <th onClick={() => toggleSort("send_qty")} className="px-4 py-3 cursor-pointer whitespace-nowrap">
      {account === "Fossil" ? "PO Requirement" : "To Send QTY"} {getSortArrow("send_qty")}
    </th>
    {account === "Fossil" && <th onClick={() => toggleSort("cluster_po")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Cluster PO {getSortArrow("cluster_po")}</th>}
    <th onClick={() => toggleSort("fill_pct")} className={`px-4 py-3 cursor-pointer whitespace-nowrap ${account === "Fossil" ? "hidden" : ""}`}>
      Fill % {getSortArrow("fill_pct")}
    </th>
    <th onClick={() => toggleSort("velocity_flag")} className={`px-4 py-3 cursor-pointer whitespace-nowrap ${account === "Fossil" ? "hidden" : ""}`}>Velocity Flag {getSortArrow("velocity_flag")}</th>
    {account !== "Fossil" && <th onClick={() => toggleSort("fulfillment_center")} className="px-4 py-3 cursor-pointer whitespace-nowrap">FC {getSortArrow("fulfillment_center")}</th>}
    {account !== "Fossil" && <th onClick={() => toggleSort("hazmat_type")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Hazmat Type {getSortArrow("hazmat_type")}</th>}
    <th onClick={() => toggleSort("master_carton")} className="px-4 py-3 cursor-pointer whitespace-nowrap">Master Carton {getSortArrow("master_carton")}</th>
    {account === "Fossil" && <th className="px-4 py-3 whitespace-nowrap">Remarks</th>}
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
                        {/* Category or Assortment */}
                        {account === "Fossil"
                          ? <td className="px-4 py-3">{row.assortment || "-"}</td>
                          : <td className="px-4 py-3">{row.category || "-"}</td>
                        }
                        {/* SKU */}
                        <td className="px-4 py-3">{row.sku}</td>
                        {/* ASIN */}
                        <td className="px-4 py-3">{row.asin || "-"}</td>
                        {/* FC - Fossil shows here, others show later */}
                        {account === "Fossil" && <td className="px-4 py-3">{row.fulfillment_center}</td>}
                        {/* Cluster - Fossil only, after FC */}
                        {account === "Fossil" && (() => {
                          const cluster = FC_CLUSTER[row.fulfillment_center?.toUpperCase()] || row.cluster || "-";
                          const clusterKey = `${row.sku}|${cluster}`;
                          const clusterPo = fossilEdits[clusterKey]?.cluster_po ?? row.cluster_po ?? 0;
                          return (
                            <td className="px-4 py-3">
                              <span className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded text-xs font-bold">{cluster}</span>
                            </td>
                          );
                        })()}
                        {/* FC SOH */}
                        <td className="px-4 py-3">{row.fc_inventory ?? 0}</td>
                        {/* Mother Warehouse / Fossil SOH */}
                        <td className="px-4 py-3">{row.ampm_inventory ?? 0}</td>
                        {/* B2B Inventory (display only) */}
                        <td className="px-4 py-3">{row.b2b_inventory ?? 0}</td>
                        {/* Avg Weekly Sales */}
                        <td className="px-4 py-3">{row.weekly_velocity ?? 0}</td>
                        {/* Total Sold */}
                        <td className="px-4 py-3">{row.total_units_sold ?? 0}</td>
                        {/* In-Transit - Fossil only */}
                        {account === "Fossil" && <td className="px-4 py-3 text-amber-700 font-semibold text-center">{row.in_transit_qty ?? 0}</td>}
                        {/* Open PO - Fossil only */}
                        {account === "Fossil" && <td className="px-4 py-3 text-blue-700 font-semibold text-center">{row.open_po_qty ?? 0}</td>}
                        {/* Target Cover Units */}
                        {account !== "Fossil" && <td className="px-4 py-3">{row.target_cover_units ?? 0}</td>}
                        {/* Original Required */}
                        {account !== "Fossil" && <td className="px-4 py-3">{row.expected_units ?? 0}</td>}
                        {/* Send Qty / PO Requirement */}
                        <td className="px-4 py-3 font-semibold">
                          {account === "Fossil"
                            ? <input
                                type="number"
                                value={getFossilField(row, "send_qty")}
                                onChange={e => setFossilField(row, "send_qty", e.target.value)}
                                className="w-20 px-2 py-1 border border-slate-300 rounded text-sm text-center"
                              />
                            : row.send_qty
                          }
                        </td>
                        {/* Cluster PO - editable, Fossil only */}
                        {account === "Fossil" && (() => {
                          const cluster = FC_CLUSTER[row.fulfillment_center?.toUpperCase()] || row.cluster || "-";
                          const clusterKey = `${row.sku}|${cluster}`;
                          const clusterPo = fossilEdits[clusterKey]?.cluster_po ?? row.cluster_po ?? 0;
                          const clusterIt = row.cluster_in_transit ?? 0;
                          const isFirstRow = row.cluster_po !== "" && row.cluster_po !== null;
                          return (
                            <td className="px-4 py-3">
                              {isFirstRow ? (
                                <>
                                  <input
                                    type="number"
                                    value={clusterPo}
                                    onChange={e => {
                                      setFossilEdits(prev => ({
                                        ...prev,
                                        [clusterKey]: { ...prev[clusterKey], cluster_po: e.target.value }
                                      }));
                                    }}
                                    className="w-20 px-2 py-1 border border-blue-300 rounded text-sm text-center bg-blue-50"
                                  />
                                  {clusterIt !== "" && clusterIt > 0 && (
                                    <div className="text-xs text-amber-600 mt-0.5 text-center">↓ {clusterIt} in-transit</div>
                                  )}
                                </>
                              ) : (
                                <span className="text-slate-300 text-xs">—</span>
                              )}
                            </td>
                          );
                        })()}
                        {/* Fill % */}
                        {account !== "Fossil" && <td className="px-4 py-3">{row.fill_pct ?? 0}%</td>}
                        {/* Velocity Flag */}
                        {account !== "Fossil" && (
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
                        )}
                        {/* FC - non-Fossil shows here */}
                        {account !== "Fossil" && <td className="px-4 py-3">{row.fulfillment_center}</td>}
                        {/* Hazmat Type - hidden for Fossil */}
                        {account !== "Fossil" && <td className="px-4 py-3">{row.hazmat_type || "-"}</td>}
                        {/* Master Carton - always from input sheet */}
                        <td className="px-4 py-3">
                          {account === "Fossil"
                            ? <span className="text-slate-600">{row.master_carton ?? 24}</span>
                            : row.master_carton
                          }
                        </td>
                        {/* Remarks - Fossil only */}
                        {account === "Fossil" && (
                          <td className="px-4 py-3">
                            <input
                              type="text"
                              value={getFossilField(row, "remarks") ?? ""}
                              onChange={e => setFossilField(row, "remarks", e.target.value)}
                              placeholder="Add remark..."
                              className="w-36 px-2 py-1 border border-slate-300 rounded text-sm"
                            />
                          </td>
                        )}
                      </tr>

                      {expandedRow === i && (
                        <tr>
                          <td colSpan="16" className="bg-slate-50 p-4 text-sm">
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
    <strong>Final Allocated (To Send QTY):</strong>
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
    <div className="px-3 py-2 bg-white border border-slate-100 rounded-lg shadow-sm">
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{title}</div>
      <div className="text-base font-semibold text-slate-800">{value ?? "-"}</div>
    </div>
  );
}

function FCAllocationSOPModal({ open, onClose }) {
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
              How FC Allocation is Calculated
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              All 5 accounts — Nexlev, Viomi, Audio Array, White Mulberry, Fossil
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
            Tells you how many units to send to each Amazon FC for every SKU.
          </p>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Top controls</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>Account</b> — Nexlev / Viomi / Audio Array / White Mulberry / Fossil</li>
              <li><b>Sales Window</b> — last N weeks of FBA Sales used for velocity (default 12). If fewer weeks of data are available, the loader uses whatever's there.</li>
              <li><b>Replenish Weeks</b> — target weeks of cover at each FC (default 8)</li>
              <li><b>Channel</b> — sales channel filter for velocity (default All)</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Columns</h3>
            <table className="w-full text-xs border-collapse">
              <tbody>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium w-36">Model / SKU / ASIN</td><td className="border border-slate-300 px-2 py-1">Identifiers</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Velocity</td><td className="border border-slate-300 px-2 py-1">Avg units/week shipped to that FC</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">FC Inventory</td><td className="border border-slate-300 px-2 py-1">Current sellable stock at that FC (from ledger)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Transfer In</td><td className="border border-slate-300 px-2 py-1">Units coming from another FC's excess (same SKU)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Target Cover</td><td className="border border-slate-300 px-2 py-1">Velocity × Replenish Weeks</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Post-Transfer Stock</td><td className="border border-slate-300 px-2 py-1">FC Inventory + Transfer In</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Adjusted Shortfall</td><td className="border border-slate-300 px-2 py-1">Target − Post-Transfer Stock (≥ 0)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium bg-amber-50">Send Qty</td><td className="border border-slate-300 px-2 py-1 bg-amber-50">Final units to ship — IST governance applied for non-Fossil</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Fill %</td><td className="border border-slate-300 px-2 py-1">Send Qty ÷ Original Required × 100 (after governance)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Mother WH (AMPM)</td><td className="border border-slate-300 px-2 py-1">Display only — not used in this calc</td></tr>
              </tbody>
            </table>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Account rules</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>Nexlev / Viomi / Audio Array / White Mulberry</b> → IXD items shipped at <b>35%</b> of need (IST governance); Non-IXD at 100%. FC-to-FC transfers allowed.</li>
              <li><b>Fossil</b> → No IST cap. Send Qty also subtracts <b>In-Transit</b> (Packing List Qty) and <b>Open PO</b> (PO Qty). <b>No transfers</b> between FCs (direct dispatch). Cluster PO computed for 6 clusters (BLR, BOM, TN, DEL, TEL, WB).</li>
              <li>Velocity divisor = weeks actually loaded after the Sales Window filter (capped at the selected dropdown value, or fewer if not enough weeks of data exist).</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Flag values (non-Fossil)</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>NO_REQUIREMENT</b> — original required = 0</li>
              <li><b>SHORT_30%+</b> — Fill % ≤ 70 (i.e. you're shipping less than 70% of need)</li>
              <li><b>OK</b> — Fill % &gt; 70</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Example (Nexlev, IXD)</h3>
            <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
              SKU shipped 800 units over 12 weeks at MAA4 → Velocity ≈ 67/wk →
              8-week target = 533 → FC has 100 + Transfer-In 50 → Adjusted Shortfall = 383 →
              IXD governance × 0.35 → <b>Send 134</b>, Fill 35% → flagged SHORT_30%+
            </p>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Example (Fossil)</h3>
            <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
              Item shipped to DEL5 → Velocity 5/wk → 8-week target = 40 → FC has 10 →
              Adjusted Shortfall = 30 → minus In-Transit 5 and Open PO 10 →
              <b> Send 15</b> (no governance, no transfers).
            </p>
          </section>

        </div>
      </div>
    </div>
  );
}

function FilterSelect({ label, value, onChange, max = 12 }) {
  // Cap the dropdown options at `max` (default 12). Used to limit the
  // Sales Window to the number of week-folders actually loaded.
  const safeMax = Math.max(1, Math.min(52, Number(max) || 12));
  const opts = Array.from({ length: safeMax }, (_, i) => i + 1);
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
        {opts.map((w) => (
          <option key={w} value={w}>
            {w} Week{w > 1 ? "s" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}