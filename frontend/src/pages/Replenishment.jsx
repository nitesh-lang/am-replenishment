import React, { useEffect, useMemo, useState } from "react";
import { getReplenishment, getKPIs } from "../api/replenishment";


/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function Replenishment() {

  const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

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
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [selectedListingStatuses, setSelectedListingStatuses] = useState([]);
  const [expandedRow, setExpandedRow] = useState(null);
  const [masterCartons, setMasterCartons] = useState({});

  // Working-week save state (Nexlev only for now)
  const [weekStart, setWeekStart] = useState(null); // null = current working week
  const [currentWeekMeta, setCurrentWeekMeta] = useState(null);
  const [pastWeekMeta, setPastWeekMeta] = useState(null);
  const [savedWeeks, setSavedWeeks] = useState([]);
  const [workingValues, setWorkingValues] = useState({}); // { [sku]: text }
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const isNexlev = account === "NEXLEV";
  const isReadOnly = weekStart !== null;

  // Excel-style per-column filters
  // columnFilters[col] = Set<string> of allowed values, or undefined for "no filter"
  const [columnFilters, setColumnFilters] = useState({});
  const [openFilter, setOpenFilter] = useState(null); // { col, rect }

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  /* Pagination */
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;

  /* ============================================================
     DATA LOAD
  ============================================================ */

  // Load week metadata + list of past saved weeks (per account)
  useEffect(() => {
    fetch(`${BASE}/replenishment/saved-weeks?account=${account}`)
      .then(res => res.json())
      .then(res => {
        setCurrentWeekMeta(res.current_week || null);
        setSavedWeeks(res.saved_weeks || []);
      })
      .catch(() => {});
  }, [account]);

  // Load replenishment data — branches on whether viewing current or past week
  useEffect(() => {
    setLoading(true);
    setPastWeekMeta(null);

    const loadCurrent = () => Promise.all([
      getKPIs(fromWeek, toWeek),
      getReplenishment(toWeek - fromWeek + 1, replenishWeeks, account),
    ]).then(([kpiRes, replRes]) => {
      setKpis(kpiRes);
      const data = Array.isArray(replRes) ? replRes : [];
      data.forEach(r => {
        r.master_carton = masterCartons[r.model] ?? r.master_carton ?? "";
      });
      setReplenishment(data);
      const wv = {};
      data.forEach(r => { if (r.sku && r.working_value) wv[r.sku] = r.working_value; });
      setWorkingValues(wv);
      setDirty(false);
    });

    const loadPast = (ws) => fetch(
      `${BASE}/replenishment/saved-week-data?account=${account}&week_start=${ws}`
    )
      .then(res => res.json())
      .then(j => {
        const data = Array.isArray(j.rows) ? j.rows : [];
        setReplenishment(data);
        setPastWeekMeta({
          week_start: j.week_start,
          week_end: j.week_end,
          label: j.label,
        });
        const wv = {};
        data.forEach(r => { if (r.sku && r.working_value) wv[r.sku] = r.working_value; });
        setWorkingValues(wv);
        setDirty(false);
        setKpis(null);
      });

    const p = weekStart ? loadPast(weekStart) : loadCurrent();
    p.finally(() => setLoading(false));
  }, [fromWeek, toWeek, replenishWeeks, account, weekStart]);

  async function saveWeek() {
    if (saving) return;
    setSaving(true);
    setSaveMsg("");
    try {
      const rows = replenishment.map(r => ({
        ...r,
        working_value: workingValues[r.sku] ?? r.working_value ?? "",
      }));
      const res = await fetch(`${BASE}/replenishment/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account, rows }),
      });
      const j = await res.json();
      if (j.status === "saved") {
        setSaveMsg(`Saved ${j.rows} rows · ${j.label}`);
        setDirty(false);
        // refresh saved-weeks list so the new save shows up immediately
        fetch(`${BASE}/replenishment/saved-weeks?account=${account}`)
          .then(res => res.json())
          .then(res => setSavedWeeks(res.saved_weeks || []))
          .catch(() => {});
      } else if (j.status === "locked") {
        setSaveMsg(j.error || "Week is locked. Cannot save.");
      } else {
        setSaveMsg(`Error: ${j.error || "unknown"}`);
      }
    } catch (e) {
      setSaveMsg(`Error: ${e.message}`);
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(""), 6000);
    }
  }


  /* ============================================================
     COLUMNS
  ============================================================ */

  const categories = useMemo(() => {
    const cats = [...new Set(replenishment.map(r => r.category).filter(Boolean))];
    return cats.sort();
  }, [replenishment]);

  const listingStatuses = useMemo(() => {
    const statuses = [...new Set(replenishment.map(r => r.listing_status).filter(Boolean))];
    return statuses.sort();
  }, [replenishment]);

  const baseColumns = useMemo(() => {
    if (!replenishment.length) return [];
    return Object.keys(replenishment[0]);
  }, [replenishment]);

  const tableColumns = useMemo(() => {
    const cols = [
      "model",
      "category",
      "asin",
      "sku",
      "sales_velocity",
      "total_units_sold",
      "amazon_inventory",
      "inbound_inventory",
      "ampm_inventory",
      "required_units",
      "replenishment_qty",
    ];
    if (isNexlev) cols.push("working_value");
    cols.push(
      "recommended_qty",
      "cartons_needed",
      "warehouse_shortfall",
      "ixd_type",
      "hazmat_type",
      "master_carton",
    );
    return cols;
  }, [isNexlev]);

  // Header label resolver (shared by thead + filter popover)
  function colLabel(col) {
    const map = {
      recommended_qty: "RECOMMENDED QTY",
      cartons_needed: "CARTONS",
      sales_velocity: "AVG WEEKLY SALES",
      total_units_sold: "TOTAL SOLD",
      ampm_inventory: "MOTHER WAREHOUSE",
      amazon_inventory: "AMAZON INVENTORY",
      inbound_inventory: "INBOUND INVENTORY",
      replenishment_qty: "REPLENISHMENT QTY",
      required_units: "REQUIRED UNITS",
      warehouse_shortfall: "WAREHOUSE SHORTFALL",
      working_value: "WORKING",
    };
    return map[col] || col.toUpperCase();
  }

  function rowValueForFilter(row, col) {
    const v = row[col];
    return v == null || v === "" ? "(blank)" : String(v);
  }

  // For a column's filter dropdown: return unique values from rows that
  // already pass all OTHER active filters. Excludes the column being edited
  // so the user can re-check values they've previously unchecked.
  function uniqueValuesForCol(col) {
    const q = search.toLowerCase();
    const others = Object.entries(columnFilters).filter(
      ([c, s]) => c !== col && s && s.size > 0
    );
    const seen = new Set();
    for (const row of replenishment) {
      if (selectedCategories.length > 0 && !selectedCategories.includes(row.category)) continue;
      if (selectedListingStatuses.length > 0 && !selectedListingStatuses.includes(row.listing_status)) continue;
      if (q && !(
        row.model?.toLowerCase().includes(q) ||
        row.asin?.toLowerCase().includes(q) ||
        row.sku?.toLowerCase().includes(q)
      )) continue;
      let pass = true;
      for (const [c, allowed] of others) {
        if (!allowed.has(rowValueForFilter(row, c))) { pass = false; break; }
      }
      if (!pass) continue;
      seen.add(rowValueForFilter(row, col));
    }
    return [...seen].sort((a, b) =>
      a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" })
    );
  }

  function clearAllColumnFilters() {
    setColumnFilters({});
  }
  const activeFilterCount = Object.values(columnFilters).filter(s => s && s.size > 0).length;

  // Outside-click closes the open filter popover
  useEffect(() => {
    if (!openFilter) return;
    const handler = (e) => {
      if (!e.target.closest("[data-filter-popover]")) setOpenFilter(null);
    };
    const id = setTimeout(() => document.addEventListener("mousedown", handler), 0);
    return () => {
      clearTimeout(id);
      document.removeEventListener("mousedown", handler);
    };
  }, [openFilter]);

  /* ============================================================
     FILTER
  ============================================================ */

  const filteredData = useMemo(() => {
    const q = search.toLowerCase();
    const activeCols = Object.entries(columnFilters).filter(([, s]) => s && s.size > 0);
    return replenishment
      .filter((row) => selectedCategories.length === 0 || selectedCategories.includes(row.category))
      .filter((row) => selectedListingStatuses.length === 0 || selectedListingStatuses.includes(row.listing_status))
      .filter((row) =>
        !q ||
        row.model?.toLowerCase().includes(q) ||
        row.asin?.toLowerCase().includes(q) ||
        row.sku?.toLowerCase().includes(q)
      )
      .filter((row) => {
        for (const [col, allowed] of activeCols) {
          if (!allowed.has(rowValueForFilter(row, col))) return false;
        }
        return true;
      });
  }, [replenishment, search, selectedCategories, selectedListingStatuses, columnFilters]);

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

  // Start from tableColumns, remove listing_status temporarily
  const exportColumns = tableColumns.filter(c => c !== "listing_status").reduce((acc, c) => {
    if (!acc.includes(c)) acc.push(c);
    return acc;
  }, []);

  // Re-insert listing_status after category
  const catIdx = exportColumns.indexOf("category");
  exportColumns.splice(catIdx + 1, 0, "listing_status");

  // Append carton intelligence columns not in tableColumns
  ["excess_units", "carton_break_flag"].forEach(c => {
    if (!exportColumns.includes(c)) exportColumns.push(c);
  });

  const columnLabels = {
    model: "MODEL",
    category: "CATEGORY",
    asin: "ASIN",
    sku: "SKU",
    listing_status: "LISTING STATUS",
    sales_velocity: "AVG WEEKLY SALES",
    total_units_sold: "TOTAL SOLD",
    amazon_inventory: "AMAZON INVENTORY",
    inbound_inventory: "INBOUND INVENTORY",
    ampm_inventory: "Mother Warehouse",
    required_units: "REQUIRED UNITS",
    replenishment_qty: "REPLENISHMENT QTY",
    recommended_qty: "RECOMMENDED QTY",
    cartons_needed: "CARTONS NEEDED",
    warehouse_shortfall: "WAREHOUSE SHORTFALL",
    ixd_type: "IXD TYPE",
    hazmat_type: "HAZMAT TYPE",
    master_carton: "MASTER CARTON",
    excess_units: "EXCESS UNITS",
    carton_break_flag: "CARTON BREAK",
    working_value: "WORKING",
  };

  const headers = exportColumns.map(c => columnLabels[c] || c.toUpperCase()).join(",");

  const rows = sortedData
    .map(row =>
      exportColumns
        .map(col => {
          const val = col === "master_carton"
            ? (masterCartons[row.model] ?? row.master_carton ?? "")
            : col === "working_value"
            ? (workingValues[row.sku] ?? row.working_value ?? "")
            : (row[col] ?? "");
          return `"${String(val).replace(/"/g, '""')}"`;
        })
        .join(",")
    )
    .join("\n");

  const blob = new Blob([headers + "\n" + rows], {
    type: "text/csv;charset=utf-8;"
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
    <div className="space-y-4">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          Nexlev Replenishment Intelligence
        </h1>
        <p className="text-slate-300 mt-2 text-sm">
          Advanced replenishment & coverage analytics
        </p>
      </div>

    <div className={`card grid grid-cols-1 ${isNexlev ? "md:grid-cols-3" : ""} gap-3 py-3`}>
      <div>
        <label className="text-xs uppercase text-slate-400">Account</label>
        <select
          value={account}
          onChange={(e) => { setAccount(e.target.value); setWeekStart(null); }}
          className="mt-2 w-full px-4 py-2 border rounded-lg"
        >
          <option value="NEXLEV">Nexlev</option>
          <option value="VIOMI">Viomi</option>
          <option value="AUDIO ARRAY">Audio Array</option>
          <option value="WHITE MULBERRY">White Mulberry</option>
        </select>
      </div>

      {isNexlev && (
      <div>
        <label className="text-xs uppercase text-slate-400">Working Week</label>
        <select
          value={weekStart ?? ""}
          onChange={(e) => setWeekStart(e.target.value || null)}
          className="mt-2 w-full px-4 py-2 border rounded-lg"
        >
          <option value="">
            {currentWeekMeta
              ? `${currentWeekMeta.label} (${currentWeekMeta.week_start} → ${currentWeekMeta.week_end})${currentWeekMeta.locked ? " — locked" : " — active"}`
              : "Current week"}
          </option>
          {savedWeeks.map(w => (
            <option key={w.week_start} value={w.week_start}>
              {w.label} ({w.week_start} → {w.week_end}) — view only
            </option>
          ))}
        </select>
      </div>
      )}

      {isNexlev && (
      <div className="flex flex-col justify-end">
        {!isReadOnly && !currentWeekMeta?.locked && (
          <button
            onClick={saveWeek}
            disabled={saving}
            className={`px-4 py-2 rounded-lg text-white text-sm font-semibold transition ${
              dirty
                ? "bg-blue-600 hover:bg-blue-700"
                : "bg-slate-700 hover:bg-slate-800"
            } disabled:opacity-50`}
          >
            {saving
              ? "Saving…"
              : dirty
              ? `Save ${currentWeekMeta?.label ?? "Week"} *`
              : `Save ${currentWeekMeta?.label ?? "Week"}`}
          </button>
        )}
        {(isReadOnly || currentWeekMeta?.locked) && (
          <div className="text-xs text-slate-500 italic px-1 py-2">
            {isReadOnly
              ? `Viewing ${pastWeekMeta?.label ?? "past week"} — read only`
              : "Current week locked"}
          </div>
        )}
        {saveMsg && (
          <div className="text-xs text-slate-600 mt-1 px-1">{saveMsg}</div>
        )}
      </div>
      )}
    </div>

    {/* SALES WINDOW + REPLENISH WEEKS FILTER */}
<div className="card grid grid-cols-1 md:grid-cols-2 gap-3 py-3">
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
      {/* EXPORT + SEARCH */}
      <div className="flex justify-between items-center gap-4 flex-wrap">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search model, ASIN or SKU..."
          className="px-4 py-2 border rounded-lg min-w-[240px]"
        />
        <div className="flex flex-wrap gap-2 items-center">
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
        {activeFilterCount > 0 && (
          <button
            onClick={clearAllColumnFilters}
            className="px-3 py-1 text-xs rounded-full border border-blue-300 text-blue-600 hover:bg-blue-50"
          >
            {activeFilterCount} column filter{activeFilterCount > 1 ? "s" : ""} · Clear all
          </button>
        )}
        <button
          onClick={exportCSV}
          className="px-4 py-2 bg-slate-900 text-white rounded-lg"
        >
          Export CSV
        </button>
        <button
          onClick={async () => {
            if (!window.confirm("Reset all saved master carton values? Fresh values from input sheet will show.")) return;
            await fetch(`${BASE}/reset-master-cartons`, { method: "POST" });
            setMasterCartons({});
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
            <thead className="bg-slate-100 text-xs uppercase sticky top-0 z-20">
              <tr>
                {tableColumns.map((col) => {
                  const hasFilter = columnFilters[col] && columnFilters[col].size > 0;
                  return (
                    <th
                      key={col}
                      className="px-4 py-3 whitespace-nowrap"
                    >
                      <div className="flex items-center gap-1">
                        <span
                          className="cursor-pointer select-none flex items-center gap-1"
                          onClick={() => toggleSort(col)}
                        >
                          {colLabel(col)}
                          {col === "recommended_qty" && (
                            <span
                              className="text-slate-400 cursor-help"
                              title="Replenishment qty rounded to nearest master carton. ⚠ = carton break recommended."
                            >ⓘ</span>
                          )}
                          <span className="text-slate-400 ml-0.5">{getSortArrow(col)}</span>
                        </span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            const rect = e.currentTarget.getBoundingClientRect();
                            setOpenFilter(prev =>
                              prev && prev.col === col ? null : { col, rect }
                            );
                          }}
                          className={`ml-auto px-1 rounded hover:bg-slate-200 ${
                            hasFilter ? "text-blue-600" : "text-slate-400"
                          }`}
                          title={hasFilter ? "Filter active — click to edit" : "Filter"}
                        >
                          {hasFilter ? "▼" : "▽"}
                        </button>
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>

            <tbody>
              {paginatedData.map((row, i) => {
                const status = getRowStatus(row);
                return (
                  <React.Fragment key={i}>
                    <tr
                      key={i}
                      className={`${getRowColor(status)} hover:bg-slate-50`}
                      onClick={() => setExpandedRow(i === expandedRow ? null : i)}
                    >
                      {tableColumns.map((col) => {
                        if (col === "listing_status") {
                          const ls = row.listing_status ?? "-";
                          const badgeStyle =
                            ls === "Active" ? "bg-green-100 text-green-700" :
                            ls === "EOL"    ? "bg-red-100 text-red-700" :
                                             "bg-slate-100 text-slate-500";
                          return (
                            <td key={col} className="px-4 py-3">
                              <span className={`px-2 py-1 text-xs rounded ${badgeStyle}`}>{ls}</span>
                            </td>
                          );
                        }

                        if (col === "required_units" && row[col] > 0)
                          return (
                            <td key={col} className="px-4 py-3 font-bold text-red-600">
                              {row[col]}
                            </td>
                          );

                        if (col === "ixd_type")
                          return <td key={col} className="px-4 py-3">{row.ixd_type}</td>;

                        if (col === "hazmat_type")
                          return <td key={col} className="px-4 py-3">{row.hazmat_type}</td>;

                        if (col === "master_carton")
                          return (
                            <td key={col} className="px-4 py-3">
                              <input
                                type="text"
                                value={masterCartons[row.model] ?? row.master_carton ?? ""}
                                onChange={async (e) => {
                                  const value = e.target.value;
                                  setMasterCartons(prev => ({ ...prev, [row.model]: value }));
                                  await fetch(`${BASE}/save-master-carton`, {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ model: row.model, master_carton: value })
                                  });
                                }}
                                onClick={e => e.stopPropagation()}
                                className="border px-2 py-1 rounded w-20"
                              />
                            </td>
                          );

                        /* ── RECOMMENDED QTY ────────────────────────────── */
                        if (col === "recommended_qty") {
                          const recQty = row.recommended_qty ?? row.replenishment_qty ?? 0;
                          const rawQty = row.replenishment_qty ?? 0;
                          const breakFlag = row.carton_break_flag ?? false;
                          const noCarton = !row.master_carton || row.master_carton === 0;

                          if (rawQty === 0)
                            return <td key={col} className="px-4 py-3 text-slate-300">—</td>;

                          if (noCarton)
                            return (
                              <td key={col} className="px-4 py-3 text-slate-400 text-xs italic">
                                No carton set
                              </td>
                            );

                          return (
                            <td key={col} className="px-4 py-3">
                              <span
                                className={`font-semibold ${breakFlag ? "text-orange-600" : row.ixd_type === "IXD" ? "text-blue-700" : "text-slate-700"}`}
                                title={`Raw replenishment: ${rawQty} → Rounded up to ${recQty}`}
                              >
                                {recQty}
                              </span>
                              {breakFlag && (
                                <span
                                  className="ml-1 text-orange-500 cursor-help"
                                  title={`Excess ${row.excess_units} units (>${Math.round((row.excess_units / (row.master_carton || 1)) * 100)}% of carton) — consider breaking carton`}
                                >⚠</span>
                              )}
                            </td>
                          );
                        }

                        /* ── CARTONS NEEDED ──────────────────────────────── */
                        if (col === "cartons_needed") {
                          const cartons = row.cartons_needed ?? 0;
                          const rawQty = row.replenishment_qty ?? 0;
                          const noCarton = !row.master_carton || row.master_carton === 0;

                          if (rawQty === 0)
                            return <td key={col} className="px-4 py-3 text-slate-300">—</td>;

                          if (noCarton)
                            return <td key={col} className="px-4 py-3 text-slate-300">—</td>;

                          return (
                            <td key={col} className="px-4 py-3">
                              <span
                                className={`px-2 py-0.5 text-xs rounded-full ${row.ixd_type === "IXD" ? "bg-blue-50 text-blue-600" : "bg-slate-100 text-slate-500"}`}
                                title={row.ixd_type === "IXD" ? "IXD — full cartons mandatory" : "Non-IXD — carton break allowed"}
                              >
                                {cartons} carton{cartons !== 1 ? "s" : ""}
                              </span>
                            </td>
                          );
                        }
                        /* ── END CARTON COLUMNS ──────────────────────────── */

                        if (col === "working_value") {
                          const val = workingValues[row.sku] ?? row.working_value ?? "";
                          if (isReadOnly || currentWeekMeta?.locked) {
                            return (
                              <td key={col} className="px-4 py-3 bg-amber-50 font-medium">
                                {val || <span className="text-slate-300">—</span>}
                              </td>
                            );
                          }
                          return (
                            <td key={col} className="px-4 py-3 bg-amber-50">
                              <input
                                type="text"
                                value={val}
                                onChange={(e) => {
                                  const v = e.target.value;
                                  setWorkingValues(prev => ({ ...prev, [row.sku]: v }));
                                  setDirty(true);
                                }}
                                onClick={(e) => e.stopPropagation()}
                                placeholder="—"
                                className="border border-amber-300 px-2 py-1 rounded w-24 bg-white"
                              />
                            </td>
                          );
                        }

                        return <td key={col} className="px-4 py-3">{row[col]}</td>;
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
                            {/* ── Carton Intelligence Detail (NEW) ── */}
                            {row.master_carton > 0 && row.replenishment_qty > 0 && (
                              <>
                                <div>
                                  <strong>MC Rounded Qty:</strong>{" "}
                                  {row.recommended_qty}
                                  {row.ixd_type === "IXD"
                                    ? " (IXD — full cartons mandatory)"
                                    : " (Non-IXD — carton break allowed)"}
                                </div>
                                <div>
                                  <strong>Cartons Needed:</strong> {row.cartons_needed}
                                </div>
                                <div>
                                  <strong>Excess Units:</strong>{" "}
                                  <span className={row.carton_break_flag ? "text-orange-600 font-semibold" : ""}>
                                    {row.excess_units}
                                    {row.carton_break_flag ? " ⚠ Break recommended" : ""}
                                  </span>
                                </div>
                              </>
                            )}
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

      {/* COLUMN FILTER POPOVER */}
      {openFilter && (
        <HeaderFilterPopover
          column={openFilter.col}
          columnLabel={colLabel(openFilter.col)}
          allValues={uniqueValuesForCol(openFilter.col)}
          activeSet={columnFilters[openFilter.col]}
          anchorRect={openFilter.rect}
          onApply={(set) =>
            setColumnFilters(prev => {
              const next = { ...prev };
              if (set === null) delete next[openFilter.col];
              else next[openFilter.col] = set;
              return next;
            })
          }
          onClose={() => setOpenFilter(null)}
        />
      )}

    </div>
  );
}

function HeaderFilterPopover({ column, columnLabel, allValues, activeSet, anchorRect, onApply, onClose }) {
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState(
    activeSet && activeSet.size > 0 ? new Set(activeSet) : new Set(allValues)
  );

  const filtered = useMemo(() => {
    if (!search) return allValues;
    const q = search.toLowerCase();
    return allValues.filter(v => v.toLowerCase().includes(q));
  }, [allValues, search]);

  const allChecked = filtered.length > 0 && filtered.every(v => draft.has(v));

  function toggleValue(v) {
    setDraft(prev => {
      const next = new Set(prev);
      if (next.has(v)) next.delete(v);
      else next.add(v);
      return next;
    });
  }

  function toggleAllVisible() {
    setDraft(prev => {
      const next = new Set(prev);
      if (allChecked) filtered.forEach(v => next.delete(v));
      else filtered.forEach(v => next.add(v));
      return next;
    });
  }

  function apply() {
    if (draft.size === allValues.length) onApply(null);
    else onApply(new Set(draft));
    onClose();
  }

  function clearFilter() {
    onApply(null);
    onClose();
  }

  // Position the popover near the filter icon, clamped to viewport
  const POPOVER_W = 280;
  const POPOVER_H = 380;
  let top = anchorRect ? anchorRect.bottom + 4 : 100;
  let left = anchorRect ? anchorRect.left : 100;
  if (typeof window !== "undefined") {
    if (left + POPOVER_W > window.innerWidth) left = window.innerWidth - POPOVER_W - 8;
    if (top + POPOVER_H > window.innerHeight) top = Math.max(8, window.innerHeight - POPOVER_H - 8);
    if (left < 8) left = 8;
  }

  return (
    <div
      data-filter-popover
      style={{ position: "fixed", top, left, width: POPOVER_W, zIndex: 1000 }}
      className="bg-white border border-slate-300 shadow-2xl rounded-lg flex flex-col"
    >
      <div className="px-3 py-2 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
        Filter: {columnLabel}
      </div>
      <div className="p-2 border-b border-slate-200">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search values..."
          className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded focus:ring-2 focus:ring-blue-500 outline-none"
          autoFocus
        />
      </div>
      <div className="px-3 py-2 border-b border-slate-200 bg-slate-50">
        <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
          <input
            type="checkbox"
            checked={allChecked}
            onChange={toggleAllVisible}
            ref={el => { if (el) el.indeterminate = !allChecked && filtered.some(v => draft.has(v)); }}
          />
          <span className="font-medium text-slate-700">(Select All{search ? " Visible" : ""})</span>
        </label>
      </div>
      <div className="flex-1 overflow-auto" style={{ maxHeight: 240 }}>
        {filtered.length === 0 && (
          <div className="text-xs text-slate-400 px-3 py-3">No matches.</div>
        )}
        {filtered.map(v => (
          <label
            key={v}
            className="flex items-center gap-2 px-3 py-1 text-xs hover:bg-slate-50 cursor-pointer"
          >
            <input
              type="checkbox"
              checked={draft.has(v)}
              onChange={() => toggleValue(v)}
            />
            <span className="truncate text-slate-700" title={v}>{v}</span>
          </label>
        ))}
      </div>
      <div className="flex gap-2 p-2 border-t border-slate-200 bg-slate-50">
        <button
          onClick={apply}
          className="flex-1 px-3 py-1.5 bg-blue-600 text-white text-xs font-semibold rounded hover:bg-blue-700"
        >
          Apply
        </button>
        <button
          onClick={clearFilter}
          className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 text-xs rounded hover:bg-slate-100"
        >
          Clear
        </button>
        <button
          onClick={onClose}
          className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 text-xs rounded hover:bg-slate-100"
        >
          Cancel
        </button>
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
    <div className="p-4 bg-white rounded-xl shadow-sm border">
      <div className="text-xs uppercase text-slate-400">{title}</div>
      <div className="text-2xl font-semibold mt-1">{display}</div>
    </div>
  );
}

function HealthCard({ label, value, color }) {
  return (
    <div className={`p-4 rounded-xl bg-${color}-50 border border-${color}-200`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}
