import { useEffect, useMemo, useState, useRef } from "react";
import { logUsage } from "../auth/usage";

/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function CBReplenishment() {

  const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";

  /* STATE */

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [selectedBrand, setSelectedBrand] = useState("All");

  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek, setToWeek] = useState(null);
  const [coverWeeks, setCoverWeeks] = useState(8);
  // "max" = max(selected window, last-2wk) [default]; "window" = selected
  // window only. Kept in lockstep with Replenishment + FC Allocation.
  const [velocityMode, setVelocityMode] = useState("max");
  const [availableWeeks, setAvailableWeeks] = useState([]);

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  const [currentPage, setCurrentPage] = useState(1);
const rowsPerPage = 50;
const remarkTimerRef = useRef(null);

// Both dropdowns show same available weeks from API
const validFromWeeks = availableWeeks;
const validToWeeks = availableWeeks;

// Week-scoped Working column + remarks save state
const [weekStart, setWeekStart] = useState(null); // null = current
const [currentWeekMeta, setCurrentWeekMeta] = useState(null);
const [pastWeekMeta, setPastWeekMeta] = useState(null);
const [savedWeeks, setSavedWeeks] = useState([]);
const [workingValues, setWorkingValues] = useState({}); // {model: text}
const [remarksValues, setRemarksValues] = useState({}); // {model: text}
const [savingMap, setSavingMap] = useState({}); // {model: "saving"|"saved"|"error"}
const saveTimersRef = useRef({}); // {model: timeoutId}
const isReadOnly = weekStart !== null;
const isLocked = isReadOnly || !!currentWeekMeta?.locked;

// Excel-style per-column filters
const [columnFilters, setColumnFilters] = useState({});
const [openFilter, setOpenFilter] = useState(null);

// SOP help modal
const [sopOpen, setSopOpen] = useState(false);

// Team export modal state
const [exportOpen, setExportOpen] = useState(false);
const [exportRows, setExportRows] = useState([]);
const [exportWeekLabel, setExportWeekLabel] = useState("");
const [exportLoading, setExportLoading] = useState(false);

async function openCBTeamExport() {
  const ws = weekStart || currentWeekMeta?.week_start;
  const label = pastWeekMeta?.label || currentWeekMeta?.label || "Week";
  if (!ws) {
    alert("No working week available.");
    return;
  }
  setExportLoading(true);
  try {
    const res = await fetch(
      `${BASE}/api/cb-replenishment/saved-week-data?week_start=${ws}`
    ).then(r => r.json());
    const all = (res.rows || []).filter(
      r => String(r.working_value || "").trim() !== ""
    );
    // Sort: Audio Array first, Tonor second, alphabetic within brand
    const brandOrder = { "Audio Array": 0, "Tonor": 1 };
    all.sort((a, b) => {
      const ba = brandOrder[a.brand] ?? 99;
      const bb = brandOrder[b.brand] ?? 99;
      if (ba !== bb) return ba - bb;
      return String(a.model || "").localeCompare(String(b.model || ""));
    });
    setExportRows(all);
    setExportWeekLabel(label);
    setExportOpen(true);
    logUsage("export", "cb-replenishment", { rows: all.length });
  } catch (e) {
    alert("Failed to load export: " + e.message);
  } finally {
    setExportLoading(false);
  }
}

const cbCols = [
  "model", "asin", "sku", "china_in_transit", "final_cb_qty",
  "ampm_inventory", "cb_3m_sales", "cambium_3m_sales", "avg_weekly_sales",
  "estimated_qty", "deficiency", "open_po", "in_transit",
  "asin_sort_details", "po_requirement", "working_value", "remarks",
];

function cbColLabel(col) {
  const map = {
    model: "MODEL",
    asin: "ASIN",
    sku: "SKU",
    china_in_transit: "CHINA IT",
    final_cb_qty: "CB SOH",
    ampm_inventory: "AMPM",
    cb_3m_sales: "CB SALES",
    cambium_3m_sales: "AMZ SALES",
    avg_weekly_sales: "AVG/WK",
    estimated_qty: "EST QTY",
    deficiency: "SHORTFALL",
    open_po: "OPEN PO",
    in_transit: "IN-TRANSIT",
    asin_sort_details: "ASIN SORT",
    po_requirement: "PO REQ",
    working_value: "WORKING",
    remarks: "REMARKS",
  };
  return map[col] || col.toUpperCase();
}

function cbRowVal(row, col) {
  let v;
  if (col === "working_value") {
    v = workingValues[row.model] ?? row.working_value ?? row.po_requirement;
  } else if (col === "remarks") {
    v = remarksValues[row.model] ?? row.remarks;
  } else {
    v = row[col];
  }
  return v == null || v === "" ? "(blank)" : String(v);
}

// Unique values for a column, filtered by all OTHER active filters (cascade)
function cbUniqueValuesForCol(col) {
  const q = search.toLowerCase();
  const others = Object.entries(columnFilters).filter(
    ([c, s]) => c !== col && s && s.size > 0
  );
  const seen = new Set();
  for (const row of data) {
    if (selectedBrand !== "All" && row.brand !== selectedBrand) continue;
    if (q && !String(row.model || "").toLowerCase().includes(q)) continue;
    let pass = true;
    for (const [c, allowed] of others) {
      if (!allowed.has(cbRowVal(row, c))) { pass = false; break; }
    }
    if (!pass) continue;
    seen.add(cbRowVal(row, col));
  }
  return [...seen].sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" })
  );
}

const cbActiveFilterCount = Object.values(columnFilters).filter(s => s && s.size > 0).length;
function cbClearAllFilters() { setColumnFilters({}); }

// Outside-click closes the filter popover
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

// Debounced auto-save for a single row's working_value + remarks
function scheduleAutoSave(row, nextWorking, nextRemarks) {
  if (isLocked) return;
  const model = row.model;
  if (!model) return;
  if (saveTimersRef.current[model]) clearTimeout(saveTimersRef.current[model]);
  setSavingMap(prev => ({ ...prev, [model]: "saving" }));
  saveTimersRef.current[model] = setTimeout(async () => {
    try {
      const res = await fetch(`${BASE}/api/cb-replenishment/save-working`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          working_value: nextWorking ?? "",
          remarks:       nextRemarks ?? "",
          snapshot:      row,
        }),
      });
      const j = await res.json();
      setSavingMap(prev => ({
        ...prev,
        [model]: j.status === "saved" ? "saved" : "error",
      }));
      if (j.status === "saved") {
        logUsage("save", "cb-replenishment", { model });
      }
      setTimeout(
        () => setSavingMap(prev => { const n = { ...prev }; delete n[model]; return n; }),
        1500
      );
    } catch {
      setSavingMap(prev => ({ ...prev, [model]: "error" }));
    }
  }, 500);
}

  /* ============================================================
     LOAD DATA
  ============================================================ */

  // Load week meta + past saved weeks
  useEffect(() => {
    fetch(`${BASE}/api/cb-replenishment/saved-weeks`)
      .then(res => res.json())
      .then(res => {
        setCurrentWeekMeta(res.current_week || null);
        setSavedWeeks(res.saved_weeks || []);
      })
      .catch(() => {});
  }, []);

  // Load replenishment data — branches on whether viewing current or past week
  useEffect(() => {
    setLoading(true);
    setPastWeekMeta(null);

    const seedFromRows = (rows) => {
      const wv = {}, rk = {};
      rows.forEach(r => {
        if (!r.model) return;
        if (r.working_value !== undefined && r.working_value !== null && String(r.working_value).trim() !== "") {
          wv[r.model] = String(r.working_value);
        }
        if (r.remarks !== undefined && r.remarks !== null && String(r.remarks).trim() !== "") {
          rk[r.model] = String(r.remarks);
        }
      });
      setWorkingValues(wv);
      setRemarksValues(rk);
    };

    const loadCurrent = () => {
      const params = new URLSearchParams({ cover_weeks: coverWeeks, velocity_mode: velocityMode });
      if (fromWeek) params.append("from_week", fromWeek);
      if (toWeek) params.append("to_week", toWeek);
      return fetch(`${BASE}/api/cb-replenishment/?${params}`)
        .then(res => res.json())
        .then(res => {
          const rows = res.data || [];
          setData(rows);
          seedFromRows(rows);
          if (res.available_weeks?.length) {
            const weeks = res.available_weeks;
            setAvailableWeeks(weeks);
            if (!fromWeek) setFromWeek(weeks[0]);
            if (!toWeek) setToWeek(weeks[weeks.length - 1]);
          }
        });
    };

    const loadPast = (ws) =>
      fetch(`${BASE}/api/cb-replenishment/saved-week-data?week_start=${ws}`)
        .then(res => res.json())
        .then(j => {
          const rows = Array.isArray(j.rows) ? j.rows : [];
          setData(rows);
          setPastWeekMeta({ week_start: j.week_start, week_end: j.week_end, label: j.label });
          seedFromRows(rows);
        });

    const p = weekStart ? loadPast(weekStart) : loadCurrent();
    p.finally(() => setLoading(false));
  }, [fromWeek, toWeek, coverWeeks, weekStart, velocityMode]);

  /* ============================================================
     FILTER
  ============================================================ */

  const filteredData = useMemo(() => {
    const activeCols = Object.entries(columnFilters).filter(([, s]) => s && s.size > 0);
    return data
      .filter((row) => selectedBrand === "All" || row.brand === selectedBrand)
      .filter((row) =>
        row.model?.toLowerCase().includes(search.toLowerCase())
      )
      .filter((row) => {
        for (const [col, allowed] of activeCols) {
          if (!allowed.has(cbRowVal(row, col))) return false;
        }
        return true;
      });
  }, [data, search, selectedBrand, columnFilters]);

  /* ============================================================
     CALCULATIONS
     avg_weekly_sales is recalculated from cb_3m_sales using
     the selected sales window (fromWeek → toWeek).
     coverWeeks remains a separate control for estimated_qty.
  ============================================================ */

  // Backend handles all calculations using from_week, to_week, cover_weeks.
  // Frontend just passes filtered data through unchanged.
  const calculatedData = filteredData;

  /* ============================================================
     SORT
  ============================================================ */

  const sortedData = useMemo(() => {

    if (!sortConfig.key) return calculatedData;

    const direction = sortConfig.direction === "asc" ? 1 : -1;

    return [...calculatedData].sort((a, b) => {

      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];

      if (aVal == null) return 1;
      if (bVal == null) return -1;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return (aVal - bVal) * direction;
      }

      return aVal.toString().localeCompare(bVal.toString()) * direction;

    });

  }, [calculatedData, sortConfig]);

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
     KPI
  ============================================================ */

  const kpis = useMemo(() => {

    const totalRequired = sortedData.reduce(
      (sum, r) => sum + (r.deficiency || 0),
      0
    );

    const avgVelocity =
      sortedData.reduce((sum, r) => sum + (r.avg_weekly_sales || 0), 0) /
      (sortedData.length || 1);

    return {
      totalRequired,
      avgVelocity,
      models: sortedData.length,
    };

  }, [sortedData]);

  /* ============================================================
     EXPORT
  ============================================================ */

  function exportCSV() {
    if (!sortedData.length) return;

    const exportColumns = [
      "model", "asin", "sku",
      "china_in_transit", "final_cb_qty", "ampm_inventory",
      "cb_3m_sales", "cambium_3m_sales", "avg_weekly_sales",
      "estimated_qty", "deficiency", "open_po", "in_transit",
      "asin_sort_details", "po_requirement", "working_value", "remarks"
    ];

    const labelMap = {
      model:             "MODEL",
      asin:              "ASIN",
      sku:               "SKU",
      china_in_transit:  "CHINA IN-TRANSIT",
      final_cb_qty:      "CB SOH",
      ampm_inventory:    "MOTHER WAREHOUSE",
      cb_3m_sales:       "CB SALES",
      cambium_3m_sales:  "CAMBIUM SALES",
      avg_weekly_sales:  "AVG WEEKLY SALES",
      estimated_qty:     "ESTIMATED QTY",
      deficiency:        "STOCK SHORTFALL",
      open_po:           "OPEN PO",
      in_transit:        "IN-TRANSIT",
      asin_sort_details: "ASIN SORT DETAILS",
      po_requirement:    "PO REQUIREMENT",
      working_value:     "WORKING",
      remarks:           "REMARKS",
    };

    const roundCols = ["avg_weekly_sales", "estimated_qty", "deficiency"];

    const headers = exportColumns.map(k => labelMap[k] || k).join(",");
    const rows = sortedData.map(row =>
      exportColumns.map(key => {
        let val;
        if (key === "working_value") {
          val = workingValues[row.model] ?? row.working_value ?? row.po_requirement ?? "";
        } else if (key === "remarks") {
          val = remarksValues[row.model] ?? row.remarks ?? "";
        } else {
          val = row[key];
        }
        const out = roundCols.includes(key) ? Math.round(val ?? 0) : (val ?? "");
        return `"${out}"`;
      }).join(",")
    ).join("\n");

    const blob = new Blob([headers + "\n" + rows], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "cb_replenishment.csv";
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
          <h1 className="text-lg font-semibold">CB Replenishment Intelligence</h1>
          <p className="text-slate-300 text-xs">Cambium / CB Inventory Planning</p>
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
      <CBSOPModal open={sopOpen} onClose={() => setSopOpen(false)} />

      {/* KPI */}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <MetricCard title="Units Required" value={Math.round(kpis.totalRequired)} />
        <MetricCard title="Avg Weekly Sales" value={kpis.avgVelocity?.toFixed(2)} />
        <MetricCard title="Models" value={kpis.models} />
      </div>

      {/* SALES WINDOW + COVER WEEKS */}

      <div className="card grid grid-cols-1 md:grid-cols-2 gap-3 py-3">

        {/* Sales Window */}
        <div>
          <label className="text-xs uppercase text-slate-400">
            Sales Window (Range)
          </label>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">From</div>
              <select
                value={fromWeek}
                onChange={(e) => {
                  setCurrentPage(1);
                  setFromWeek(Number(e.target.value));
                }}
                className="w-full px-4 py-2 border rounded-lg"
              >
                {validFromWeeks.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div className="text-xs text-slate-400 mb-1">To</div>
              <select
                value={toWeek}
                onChange={(e) => {
                  setCurrentPage(1);
                  setToWeek(Number(e.target.value));
                }}
                className="w-full px-4 py-2 border rounded-lg"
              >
                {validToWeeks.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Cover Weeks */}
        <div>
          <label className="text-xs uppercase tracking-wider text-slate-400">
            Cover Weeks
          </label>
          <div className="grid grid-cols-1 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">&nbsp;</div>
              <select
                value={coverWeeks}
                onChange={(e) => {
                  setCurrentPage(1);
                  setCoverWeeks(Number(e.target.value));
                }}
                className="w-full px-4 py-2 border border-slate-200 rounded-lg"
              >
                {[4,5,6,7,8,9,10,11,12].map(w => (
                  <option key={w} value={w}>
                    {w} Week{w > 1 ? "s" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Velocity basis — same choice as Replenishment + FC Allocation. */}
        <div>
          <label className="text-sm font-medium text-slate-600">
            Velocity Basis
          </label>
          <div className="grid grid-cols-1 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">&nbsp;</div>
              <select
                value={velocityMode}
                onChange={(e) => {
                  setCurrentPage(1);
                  setVelocityMode(e.target.value);
                }}
                title="Higher-of: max(selected window, last-2wk). Window only: ignore the 2-week burst."
                className="w-full px-4 py-2 border border-slate-200 rounded-lg"
              >
                <option value="max">Higher of window / 2wk</option>
                <option value="window">Selected window only</option>
              </select>
            </div>
          </div>
        </div>

      </div>

      {/* WORKING WEEK SELECTOR */}
      <div className="card grid grid-cols-1 md:grid-cols-2 gap-3 py-3">
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
        <div className="flex flex-col justify-end">
          {isLocked ? (
            <div className="text-xs text-slate-500 italic px-1 py-2">
              {isReadOnly
                ? `Viewing ${pastWeekMeta?.label ?? "past week"} — read only`
                : "Current week locked"}
            </div>
          ) : (
            <div className="text-xs text-slate-500 italic px-1 py-2">
              Working column auto-saves on each edit. Locks Saturday 11:59 PM IST.
            </div>
          )}
        </div>
      </div>

      {/* FILTER */}

      <div className="flex gap-4">

        <select
          value={selectedBrand}
          onChange={(e) => setSelectedBrand(e.target.value)}
          className="px-4 py-2 border rounded-lg"
        >
          <option value="All">All</option>
          <option>Audio Array</option>
          <option>Tonor</option>
        </select>

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search model..."
          className="px-4 py-2 border rounded-lg w-64"
        />

        {cbActiveFilterCount > 0 && (
          <button
            onClick={cbClearAllFilters}
            className="px-3 py-1 text-xs rounded-full border border-blue-300 text-blue-600 hover:bg-blue-50"
          >
            {cbActiveFilterCount} column filter{cbActiveFilterCount > 1 ? "s" : ""} · Clear all
          </button>
        )}

        <button
          onClick={exportCSV}
          className="ml-auto px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition"
        >
          Export CSV
        </button>

        <button
          onClick={openCBTeamExport}
          disabled={exportLoading}
          className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition disabled:opacity-50"
          title="Brand-wise PO Qty export for the team (Audio Array + Tonor)"
        >
          {exportLoading ? "Loading…" : "Team Export"}
        </button>

        <button
          onClick={async () => {
            if (!window.confirm("Reset all saved PO requirements and remarks? Fresh calculations will show.")) return;
            await fetch(`${BASE}/api/cb-replenishment/reset`, { method: "POST" });
            window.location.reload();
          }}
          className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition"
        >
          Reset
        </button>

      </div>

      {/* TABLE */}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-auto max-h-[82vh]">

          <table className="w-full text-[11px] table-auto">

            <thead className="bg-slate-100 text-[10px] uppercase sticky top-0 z-20">
              <tr>
                {cbCols.map((col) => {
                  const hasFilter = columnFilters[col] && columnFilters[col].size > 0;
                  return (
                    <th key={col} className="px-2 py-2 whitespace-nowrap font-semibold tracking-tight">
                      <div className="flex items-center gap-1">
                        <span
                          className="cursor-pointer select-none flex items-center gap-1"
                          onClick={() => toggleSort(col)}
                        >
                          {cbColLabel(col)}
                          <span className="text-slate-400 ml-0.5">
                            {sortConfig.key === col ? (sortConfig.direction === "asc" ? "▲" : "▼") : "↕"}
                          </span>
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

              {paginatedData.map((row, i) => (

                <tr key={i} className="hover:bg-slate-50">

                  <td className="px-2 py-1.5 font-medium">
                    {row.model}
                  </td>

                  <td className="px-2 py-1.5 text-slate-500">
                    {row.asin || "-"}
                  </td>

                  <td className="px-2 py-1.5 font-mono text-slate-500">
                    {row.sku || "-"}
                  </td>

                  <td className="px-2 py-1.5">
                    {row.china_in_transit ?? 0}
                  </td>

                  <td className="px-2 py-1.5">
                    {row.final_cb_qty}
                  </td>

                  <td className="px-2 py-1.5">
                    {row.ampm_inventory ?? 0}
                  </td>

                  <td className="px-2 py-1.5">
                    {row.cb_3m_sales}
                  </td>

                  <td className="px-2 py-1.5">
                    {row.cambium_3m_sales}
                  </td>

                  <td className="px-2 py-1.5">
                    {Math.round(row.avg_weekly_sales)}
                  </td>

                  <td className="px-2 py-1.5 font-semibold text-indigo-700">
                    {Math.round(row.estimated_qty)}
                  </td>

                  <td className="px-2 py-1.5 text-red-600 font-semibold">
                    {Math.round(row.deficiency)}
                  </td>

                  <td className="px-2 py-1.5">
                    {row.open_po}
                  </td>

                  <td className="px-2 py-1.5">
                    {row.in_transit}
                  </td>

                  <td className="px-2 py-1.5">
                    {row.asin_sort_details || "-"}
                  </td>

                  <td className="px-2 py-1.5 font-semibold text-indigo-700">
                    {Math.round(row.po_requirement ?? 0)}
                  </td>

                  <td className="px-2 py-1.5 bg-amber-50">
                    {isLocked ? (
                      <span className="font-medium">
                        {workingValues[row.model] ?? row.working_value ?? ""}
                      </span>
                    ) : (
                      <input
                        type="text"
                        value={workingValues[row.model] ?? String(row.po_requirement ?? "")}
                        onChange={(e) => {
                          const v = e.target.value;
                          setWorkingValues(prev => ({ ...prev, [row.model]: v }));
                          scheduleAutoSave(row, v, remarksValues[row.model] ?? row.remarks ?? "");
                        }}
                        className="border border-amber-300 px-1.5 py-0.5 rounded w-16 bg-white text-[11px]"
                      />
                    )}
                    {savingMap[row.model] && (
                      <div className={`text-[10px] mt-1 ${
                        savingMap[row.model] === "saved" ? "text-emerald-600"
                          : savingMap[row.model] === "error" ? "text-red-600"
                          : "text-slate-400"
                      }`}>
                        {savingMap[row.model] === "saving" ? "saving…"
                          : savingMap[row.model] === "saved" ? "✓ saved"
                          : "× error"}
                      </div>
                    )}
                  </td>

                  <td className="px-2 py-1.5">
                    {isLocked ? (
                      <span>{remarksValues[row.model] ?? row.remarks ?? ""}</span>
                    ) : (
                      <input
                        type="text"
                        value={remarksValues[row.model] ?? row.remarks ?? ""}
                        onChange={(e) => {
                          const v = e.target.value;
                          setRemarksValues(prev => ({ ...prev, [row.model]: v }));
                          scheduleAutoSave(
                            row,
                            workingValues[row.model] ?? String(row.po_requirement ?? ""),
                            v
                          );
                        }}
                        className="border rounded px-1.5 py-0.5 w-full text-[11px]"
                      />
                    )}
                  </td>

                </tr>

              ))}

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

      {/* TEAM EXPORT MODAL */}
      <CBTeamExportModal
        open={exportOpen}
        rows={exportRows}
        weekLabel={exportWeekLabel}
        onClose={() => setExportOpen(false)}
      />

      {/* COLUMN FILTER POPOVER */}
      {openFilter && (
        <HeaderFilterPopover
          column={openFilter.col}
          columnLabel={cbColLabel(openFilter.col)}
          allValues={cbUniqueValuesForCol(openFilter.col)}
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

/* ============================================================
   COMPONENTS
============================================================ */

function CBTeamExportModal({ open, onClose, rows, weekLabel }) {
  const [copied, setCopied] = useState(false);
  if (!open) return null;

  const cols = ["MODEL", "ASIN", "SKU", "PO QTY", "REMARKS"];

  const tableRows = rows.map(r => [
    r.model || "",
    r.asin || "",
    r.sku || "",
    r.working_value || "",
    r.remarks || "",
  ]);

  const total = rows.reduce(
    (s, r) => s + (parseFloat(r.working_value) || 0),
    0
  );
  const totalRow = ["Total", "", "", total || "", ""];

  function escHTML(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function buildTSV() {
    const header = cols.join("\t");
    const lines = tableRows.map(r => r.join("\t"));
    return [header, ...lines, totalRow.join("\t")].join("\n");
  }

  function buildHTMLTable() {
    const CELL_BASE =
      "text-align:center;vertical-align:middle;border:1px solid #94a3b8;" +
      "padding:6px;word-wrap:break-word;white-space:normal;";
    const HEAD = `background:#e2e8f0;font-weight:bold;${CELL_BASE}`;
    const BODY = CELL_BASE;
    const FOOT = `background:#f1f5f9;font-weight:bold;${CELL_BASE}`;

    const head =
      "<tr>" +
      cols.map(c => `<th style="${HEAD}">${escHTML(c)}</th>`).join("") +
      "</tr>";
    const body = tableRows
      .map(r =>
        "<tr>" +
        r.map(v => `<td style="${BODY}">${escHTML(v)}</td>`).join("") +
        "</tr>"
      )
      .join("");
    const foot =
      "<tr>" +
      totalRow.map(v => `<td style="${FOOT}">${escHTML(v)}</td>`).join("") +
      "</tr>";
    return `<table style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:12px;"><thead>${head}</thead><tbody>${body}${foot}</tbody></table>`;
  }

  async function copy() {
    const tsv = buildTSV();
    const html = buildHTMLTable();
    try {
      if (navigator.clipboard && window.ClipboardItem) {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/plain": new Blob([tsv], { type: "text/plain" }),
            "text/html":  new Blob([html], { type: "text/html" }),
          }),
        ]);
      } else {
        await navigator.clipboard.writeText(tsv);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      try {
        await navigator.clipboard.writeText(tsv);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        alert("Copy failed: " + e.message);
      }
    }
  }

  function download() {
    const doc =
      `<html xmlns:o="urn:schemas-microsoft-com:office:office" ` +
      `xmlns:x="urn:schemas-microsoft-com:office:excel"><head>` +
      `<meta charset="utf-8"></head><body>${buildHTMLTable()}</body></html>`;
    const blob = new Blob([doc], { type: "application/vnd.ms-excel;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cb_team_export_${weekLabel.replace(/\s/g, "_")}.xls`;
    a.click();
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              CB Team Export — {weekLabel}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Audio Array + Tonor · {rows.length} row{rows.length !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={copy}
              disabled={rows.length === 0}
              className="px-3 py-1.5 bg-blue-600 text-white text-xs font-semibold rounded hover:bg-blue-700 disabled:opacity-40"
            >
              {copied ? "Copied!" : "Copy to clipboard"}
            </button>
            <button
              onClick={download}
              disabled={rows.length === 0}
              className="px-3 py-1.5 bg-slate-900 text-white text-xs font-semibold rounded hover:bg-slate-800 disabled:opacity-40"
            >
              Download Excel
            </button>
            <button
              onClick={onClose}
              className="px-3 py-1.5 bg-slate-100 text-slate-700 text-xs rounded hover:bg-slate-200"
            >
              Close
            </button>
          </div>
        </div>

        {rows.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <p className="text-sm">No rows to export.</p>
            <p className="text-xs mt-2">
              Type Working values for Audio Array and/or Tonor for this week first.
            </p>
          </div>
        ) : (
          <div className="overflow-auto flex-1">
            <table className="w-full text-xs border-collapse">
              <thead className="bg-slate-200 sticky top-0">
                <tr>
                  {cols.map(c => (
                    <th
                      key={c}
                      className="px-3 py-2 text-center align-middle font-bold uppercase tracking-wide text-slate-700 border border-slate-400 break-words"
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableRows.map((r, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    {r.map((v, j) => (
                      <td
                        key={j}
                        className="px-3 py-1.5 text-center align-middle border border-slate-300 break-words"
                      >
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
                <tr className="bg-slate-100 font-bold">
                  {totalRow.map((v, j) => (
                    <td
                      key={j}
                      className="px-3 py-2 text-center align-middle border border-slate-400 break-words"
                    >
                      {v}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
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
      if (next.has(v)) next.delete(v); else next.add(v);
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
  function clearFilter() { onApply(null); onClose(); }

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
          <label key={v} className="flex items-center gap-2 px-3 py-1 text-xs hover:bg-slate-50 cursor-pointer">
            <input type="checkbox" checked={draft.has(v)} onChange={() => toggleValue(v)} />
            <span className="truncate text-slate-700" title={v}>{v}</span>
          </label>
        ))}
      </div>
      <div className="flex gap-2 p-2 border-t border-slate-200 bg-slate-50">
        <button onClick={apply} className="flex-1 px-3 py-1.5 bg-blue-600 text-white text-xs font-semibold rounded hover:bg-blue-700">
          Apply
        </button>
        <button onClick={clearFilter} className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 text-xs rounded hover:bg-slate-100">
          Clear
        </button>
        <button onClick={onClose} className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 text-xs rounded hover:bg-slate-100">
          Cancel
        </button>
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

function CBSOPModal({ open, onClose }) {
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
              How CB Replenishment is Calculated
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Brands covered: Audio Array + Tonor
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
            Tells you how many units to ship from the <b>Mother Warehouse</b> to <b>CB (Cambium)</b> for each model, based on CB's recent sales and what's already on order.
          </p>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Top controls</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>Sales Window (From / To)</b> — Range from the last 12 available weeks (default: full last 12)</li>
              <li><b>Cover Weeks</b> — Weeks of stock you want at CB (default 8)</li>
              <li><b>Working Week</b> — Active save week. Past weeks view-only.</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Columns</h3>
            <table className="w-full text-xs border-collapse">
              <tbody>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium w-36">CB SALES</td><td className="border border-slate-300 px-2 py-1">Units sold via <b>1p Sales</b> channel in the window</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">AMZ SALES</td><td className="border border-slate-300 px-2 py-1">Units sold via <b>Amazon</b> channel in the window (Cambium's Amazon)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">AVG/WK</td><td className="border border-slate-300 px-2 py-1">(CB Sales + AMZ Sales) ÷ window weeks</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">EST QTY</td><td className="border border-slate-300 px-2 py-1">Target stock at CB = AVG/WK × Cover Weeks</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">CB SOH</td><td className="border border-slate-300 px-2 py-1">Current CB stock (1P channel from inventory snapshots)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">AMPM (Mother WH)</td><td className="border border-slate-300 px-2 py-1">Stock at your warehouse — what you can ship to CB</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">CHINA IT</td><td className="border border-slate-300 px-2 py-1">Pipeline rows from inventory snapshot (units coming from China)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">OPEN PO</td><td className="border border-slate-300 px-2 py-1">Open POs already raised (status = Open PO)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">IN-TRANSIT</td><td className="border border-slate-300 px-2 py-1">In-transit PO units (status = In-Transit)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">SHORTFALL</td><td className="border border-slate-300 px-2 py-1">EST QTY − CB SOH (≥ 0). The gap to fill.</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">PO REQ</td><td className="border border-slate-300 px-2 py-1">Shortfall − (Open PO + In-Transit), then <b>capped at Mother Warehouse stock</b>. Read-only.</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium bg-amber-50">WORKING</td><td className="border border-slate-300 px-2 py-1 bg-amber-50">Editable. Pre-fills from PO REQ. Your final call. Auto-saves.</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">REMARKS</td><td className="border border-slate-300 px-2 py-1">Free-form notes, also week-scoped</td></tr>
              </tbody>
            </table>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Filter rules</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li>Brands counted: <b>Audio Array + Tonor</b> only</li>
              <li>Sales channels counted: <b>1p Sales + Amazon</b> only (B2B, Blinkit, D2C, BI Worldwide, CRED, Flipkart, POP — all excluded ~18% of sales)</li>
              <li>Inventory channels read: <code>1p</code> → CB SOH, <code>ampm</code> → Mother Warehouse, <code>pipeline</code> → China In-Transit</li>
              <li>PO file rows used: <b>Open PO</b> and <b>In-Transit</b> delivery statuses</li>
              <li>Master models with bundle names like <code>UB-01 (AI-04...)</code> match by base <code>UB-01</code></li>
              <li>Models in sales but missing from master are dropped (current known drops: zero — TC40S and AM-Mix8 were added recently)</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Example</h3>
            <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
              ETC-04: sold 60 units over 12 weeks → AVG/WK = 5 →
              8-week target (EST QTY) = 40 → CB has 10 → SHORTFALL = 30 →
              Open PO 5 + In-Transit 10 → PO REQ = 30 − 15 = <b>15</b>
              (Mother WH has 50, no cap kicks in).
              <br/>
              <span className="text-slate-500">If Mother WH only had 8, PO REQ would be capped at 8.</span>
            </p>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Working column</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li>Auto-saves as you type</li>
              <li>Week runs Sun → Sat; <b>locks at Saturday 11:59 PM IST</b></li>
              <li>Past weeks are view-only via the dropdown</li>
              <li>The full row at save time is frozen (SKU, ASIN, Model, every number)</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Filters &amp; Team Export</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li>Click <b>▽</b> on any column header to filter like Excel</li>
              <li>Green <b>Team Export</b> button → brand-wise paste-ready table (Model · ASIN · SKU · PO Qty · Remarks). Audio Array rows first, then Tonor, with total. Bold + center align carries over to Sheets/Excel.</li>
            </ul>
          </section>

        </div>
      </div>
    </div>
  );
}
