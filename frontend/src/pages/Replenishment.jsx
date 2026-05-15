import React, { useEffect, useMemo, useState } from "react";
import { getReplenishment, getKPIs } from "../api/replenishment";
import { logUsage } from "../auth/usage";


/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function Replenishment() {

  const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

  /* ============================================================
     STATE
  ============================================================ */

  const [fromWeek, setFromWeek] = useState(1);
  const [toWeek, setToWeek] = useState(12);
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
  const isReadOnly = weekStart !== null;

  // Excel-style per-column filters
  // columnFilters[col] = Set<string> of allowed values, or undefined for "no filter"
  const [columnFilters, setColumnFilters] = useState({});
  const [openFilter, setOpenFilter] = useState(null); // { col, rect }

  // SOP help modal
  const [sopOpen, setSopOpen] = useState(false);

  // Team export modal state
  const [exportOpen, setExportOpen] = useState(false);
  const [exportRows, setExportRows] = useState([]);
  const [exportFormat, setExportFormat] = useState("nexlev_viomi");
  const [exportWeekLabel, setExportWeekLabel] = useState("");
  const [exportLoading, setExportLoading] = useState(false);

  function teamExportFormat(acc) {
    if (acc === "NEXLEV" || acc === "VIOMI") return "nexlev_viomi";
    if (acc === "AUDIO ARRAY") return "audio_array";
    if (acc === "WHITE MULBERRY") return "white_mulberry";
    return "nexlev_viomi";
  }

  function teamExportButtonLabel(acc) {
    if (acc === "NEXLEV" || acc === "VIOMI") return "Team Export (NX+VM)";
    if (acc === "AUDIO ARRAY") return "Team Export (AA)";
    if (acc === "WHITE MULBERRY") return "Team Export (WM)";
    return "Team Export";
  }

  async function openTeamExport() {
    const ws = weekStart || currentWeekMeta?.week_start;
    const label = pastWeekMeta?.label || currentWeekMeta?.label || "Week";
    if (!ws) {
      alert("No working week available.");
      return;
    }
    setExportLoading(true);
    try {
      const fmt = teamExportFormat(account);
      let rows = [];

      const fetchAcc = (a) =>
        fetch(`${BASE}/replenishment/saved-week-data?account=${encodeURIComponent(a)}&week_start=${ws}`)
          .then(r => r.json());

      const onlyWithWorking = (list) =>
        (list || []).filter(r => String(r.working_value || "").trim() !== "");
      const bySku = (a, b) => String(a.sku || "").localeCompare(String(b.sku || ""));

      if (fmt === "nexlev_viomi") {
        const [nx, vm] = await Promise.all([fetchAcc("NEXLEV"), fetchAcc("VIOMI")]);
        const nxRows = onlyWithWorking(nx.rows).sort(bySku);
        const vmRows = onlyWithWorking(vm.rows).sort(bySku);
        rows = [
          ...nxRows.map(r => ({ ...r, _src: "nx" })),
          ...vmRows.map(r => ({ ...r, _src: "vm" })),
        ];
      } else if (fmt === "audio_array") {
        const res = await fetchAcc("AUDIO ARRAY");
        rows = onlyWithWorking(res.rows).sort(bySku);
      } else if (fmt === "white_mulberry") {
        const res = await fetchAcc("WHITE MULBERRY");
        rows = onlyWithWorking(res.rows).sort(bySku);
      }

      setExportFormat(fmt);
      setExportRows(rows);
      setExportWeekLabel(label);
      setExportOpen(true);
      logUsage("export", "replenishment", { account, format: fmt, rows: rows.length });
    } catch (e) {
      alert("Failed to load export: " + e.message);
    } finally {
      setExportLoading(false);
    }
  }

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
        logUsage("save", "replenishment", { account, rows: j.rows, week_start: j.week_start });
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

  const tableColumns = useMemo(() => [
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
    "working_value",
    "recommended_qty",
    "cartons_needed",
    "warehouse_shortfall",
    "ixd_type",
    "hazmat_type",
    "master_carton",
  ], []);

  // Header label resolver (shared by thead + filter popover)
  function colLabel(col) {
    const map = {
      recommended_qty: "REC QTY",
      cartons_needed: "CARTONS",
      sales_velocity: "AVG/WK",
      total_units_sold: "TOTAL",
      ampm_inventory: "MOTHER WH",
      amazon_inventory: "AZ INV",
      inbound_inventory: "INBOUND",
      replenishment_qty: "REPLEN",
      required_units: "REQ UNITS",
      warehouse_shortfall: "SHORTFALL",
      working_value: "WORKING",
      master_carton: "MC",
      ixd_type: "IXD",
      hazmat_type: "HAZMAT",
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
    // Subtle row tint — strong row colors were noisy across 50 rows.
    // Critical SKUs are already surfaced via SHORTFALL and required_units styling.
    if (status === "CRITICAL") return "bg-red-50/40";
    return "";
  }

  const NUMERIC_COLS = new Set([
    "sales_velocity", "total_units_sold", "amazon_inventory", "inbound_inventory",
    "ampm_inventory", "required_units", "replenishment_qty", "warehouse_shortfall",
  ]);

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
     HERO KPIS — the four numbers a planner actually cares about
  ============================================================ */
  const heroKpis = useMemo(() => {
    let toShip = 0;
    let chinaGap = 0;
    let modelsNeeding = 0;
    let totalCartons = 0;
    sortedData.forEach((r) => {
      const q = r.recommended_qty || r.replenishment_qty || 0;
      toShip += q;
      chinaGap += (r.warehouse_shortfall || 0);
      if (q > 0) modelsNeeding += 1;
      totalCartons += (r.cartons_needed || 0);
    });
    return { toShip, chinaGap, modelsNeeding, totalCartons };
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
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold shadow-sm shadow-indigo-500/20">R</div>
          <div>
            <h1 className="text-[15px] font-semibold text-zinc-900 tracking-tight leading-tight">Replenishment Intelligence</h1>
            <p className="text-[11px] text-zinc-500">Coverage &amp; replenishment analytics</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSopOpen(true)}
            className="px-2.5 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-md hover:bg-indigo-100 transition"
            title="Read the SOP for this page"
          >
            How is this calculated?
          </button>
        </div>
      </div>

      {/* HERO KPI ROW */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <KpiTile
          label="Units to Ship"
          value={heroKpis.toShip}
          accent="indigo"
          hint={`${heroKpis.modelsNeeding} model${heroKpis.modelsNeeding !== 1 ? "s" : ""} need stock`}
        />
        <KpiTile
          label="China PO Gap"
          value={heroKpis.chinaGap}
          accent="amber"
          hint={heroKpis.chinaGap > 0 ? "Raise a new China PO" : "Warehouse covers full need"}
        />
        <KpiTile
          label="Critical SKUs"
          value={healthStats.critical}
          accent="red"
          hint={healthStats.critical > 0 ? "Below 1-week cover" : "Nothing critical"}
        />
        <KpiTile
          label="Cartons Needed"
          value={heroKpis.totalCartons}
          accent="zinc"
          hint={`${healthStats.healthy} SKUs healthy`}
        />
      </div>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 px-3 py-2.5 bg-white border border-zinc-200 rounded-lg">
      <div>
        <label className="text-[10px] uppercase tracking-[0.08em] text-zinc-500 font-semibold">Account</label>
        <select
          value={account}
          onChange={(e) => { setAccount(e.target.value); setWeekStart(null); }}
          className="mt-1 w-full px-2.5 py-1.5 text-sm bg-white border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 hover:border-zinc-300 transition-colors"
        >
          <option value="NEXLEV">Nexlev</option>
          <option value="VIOMI">Viomi</option>
          <option value="AUDIO ARRAY">Audio Array</option>
          <option value="WHITE MULBERRY">White Mulberry</option>
        </select>
      </div>

      <div>
        <label className="text-[10px] uppercase tracking-[0.08em] text-zinc-500 font-semibold">Working Week</label>
        <select
          value={weekStart ?? ""}
          onChange={(e) => setWeekStart(e.target.value || null)}
          className="mt-1 w-full px-2.5 py-1.5 text-sm bg-white border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 hover:border-zinc-300 transition-colors"
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
        {!isReadOnly && !currentWeekMeta?.locked && (
          <button
            onClick={saveWeek}
            disabled={saving}
            className={`px-3 py-1.5 text-sm font-semibold rounded-md transition disabled:opacity-50 shadow-sm ${
              dirty
                ? "bg-indigo-600 text-white hover:bg-indigo-700 ring-2 ring-indigo-200"
                : "bg-white text-slate-700 border border-slate-200 hover:border-slate-400"
            }`}
          >
            {saving
              ? "Saving…"
              : dirty
              ? <>Save {currentWeekMeta?.label ?? "Week"} <span className="text-amber-300">●</span></>
              : `Save ${currentWeekMeta?.label ?? "Week"}`}
          </button>
        )}
        {(isReadOnly || currentWeekMeta?.locked) && (
          <div className="text-xs text-slate-400 italic">
            {isReadOnly
              ? `${pastWeekMeta?.label ?? "Past week"} — view only`
              : "Current week locked"}
          </div>
        )}
        {saveMsg && (
          <div className="text-[11px] text-slate-500 mt-1">{saveMsg}</div>
        )}
      </div>
    </div>

    {/* SALES WINDOW + REPLENISH WEEKS FILTER */}
<div className="grid grid-cols-1 md:grid-cols-2 gap-3 px-3 py-2.5 bg-white border border-zinc-200 rounded-lg">
  <div>
  <label className="text-[10px] uppercase tracking-[0.08em] text-zinc-500 font-semibold">
    Sales Window (Range)
  </label>

  <div className="grid grid-cols-2 gap-2 mt-1">
    <select
      value={fromWeek}
      onChange={(e) => {
        setCurrentPage(1);
        setFromWeek(Number(e.target.value));
      }}
      className="px-2.5 py-1.5 text-sm bg-white border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400"
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
      className="px-2.5 py-1.5 text-sm bg-white border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400"
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
    <label className="text-[10px] uppercase tracking-[0.08em] text-zinc-500 font-semibold">
      Replenish Weeks
    </label>
    <select
      value={replenishWeeks}
      onChange={(e) => {
        setCurrentPage(1);
        setReplenishWeeks(Number(e.target.value));
      }}
      className="mt-1 w-full px-2.5 py-1.5 text-sm bg-white border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400"
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
      <div className="flex justify-between items-center gap-3 flex-wrap px-3 py-2 bg-white border border-zinc-200 rounded-lg">
        <div className="relative min-w-[260px]">
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-400 pointer-events-none" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="7" cy="7" r="5"/><path d="m11 11 3 3"/></svg>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search model, ASIN or SKU…"
            className="w-full pl-8 pr-3 py-1.5 text-sm bg-zinc-50 border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 focus:bg-white transition-colors placeholder:text-zinc-400"
          />
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider font-medium">Category</span>
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCategories(prev =>
                prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
              )}
              className={`px-2.5 py-1 text-xs rounded-md border transition ${
                selectedCategories.includes(cat)
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
              }`}
            >
              {cat}
            </button>
          ))}
          {selectedCategories.length > 0 && (
            <button
              onClick={() => setSelectedCategories([])}
              className="text-xs text-slate-500 hover:text-slate-900 ml-1"
            >
              clear
            </button>
          )}

          <span className="text-slate-200 mx-1.5">·</span>

          <span className="text-[10px] text-slate-400 uppercase tracking-wider font-medium">Status</span>
          {listingStatuses.map(ls => {
            const dot =
              ls === "Active" ? "bg-emerald-500" :
              ls === "EOL"    ? "bg-red-500" :
                               "bg-slate-400";
            const isActive = selectedListingStatuses.includes(ls);
            return (
              <button
                key={ls}
                onClick={() => setSelectedListingStatuses(prev =>
                  prev.includes(ls) ? prev.filter(s => s !== ls) : [...prev, ls]
                )}
                className={`px-2.5 py-1 text-xs rounded-md border transition flex items-center gap-1.5 ${
                  isActive
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${dot}`}></span>
                {ls}
              </button>
            );
          })}
          {selectedListingStatuses.length > 0 && (
            <button
              onClick={() => setSelectedListingStatuses([])}
              className="text-xs text-slate-500 hover:text-slate-900 ml-1"
            >
              clear
            </button>
          )}
        </div>
        {activeFilterCount > 0 && (
          <button
            onClick={clearAllColumnFilters}
            className="px-2.5 py-1 text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-md hover:bg-indigo-100"
          >
            {activeFilterCount} column filter{activeFilterCount > 1 ? "s" : ""} · clear
          </button>
        )}
        <button
          onClick={exportCSV}
          className="px-3 py-1.5 text-sm font-medium bg-slate-900 text-white border border-slate-900 rounded-md hover:bg-slate-800 shadow-sm transition"
        >
          Export CSV
        </button>
        <button
          onClick={openTeamExport}
          disabled={exportLoading}
          className="px-3 py-1.5 text-sm font-semibold bg-emerald-600 text-white rounded-md hover:bg-emerald-700 shadow-sm transition disabled:opacity-50"
          title="Pre-formatted export of saved Working values for the current account"
        >
          {exportLoading ? "Loading…" : teamExportButtonLabel(account)}
        </button>
        <button
          onClick={async () => {
            if (!window.confirm("Reset all saved master carton values? Fresh values from input sheet will show.")) return;
            await fetch(`${BASE}/reset-master-cartons`, { method: "POST" });
            setMasterCartons({});
            window.location.reload();
          }}
          className="px-3 py-1.5 text-sm font-medium bg-white text-red-600 border border-red-200 rounded-md hover:bg-red-50 transition"
        >
          Reset
        </button>
      </div>

      {/* TABLE */}
      <div className="border border-zinc-200 rounded-lg overflow-hidden bg-white shadow-sm">
        <div className="overflow-auto max-h-[78vh]">
          <table className="w-full text-[11px] table-auto">
            <thead className="bg-zinc-50/80 backdrop-blur text-[10px] uppercase sticky top-0 z-20 border-b border-zinc-200">
              <tr>
                {tableColumns.map((col) => {
                  const hasFilter = columnFilters[col] && columnFilters[col].size > 0;
                  const isNum = NUMERIC_COLS.has(col) || col === "recommended_qty";
                  const isWorking = col === "working_value";
                  return (
                    <th
                      key={col}
                      className={`px-2 py-2 whitespace-nowrap font-semibold tracking-[0.06em] ${isWorking ? "text-amber-700 bg-amber-50/60 shadow-[inset_2px_0_0_0_theme(colors.amber.400)]" : "text-zinc-600"} ${isNum ? "text-right" : "text-left"}`}
                    >
                      <div className={`flex items-center gap-1 ${isNum ? "justify-end" : ""}`}>
                        <span
                          className="cursor-pointer select-none flex items-center gap-1 hover:text-zinc-900 transition-colors"
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
                          className={`ml-auto px-1 rounded hover:bg-zinc-200 transition-colors ${
                            hasFilter ? "text-indigo-600" : "text-zinc-400"
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
                      className={`border-b border-zinc-100 hover:bg-indigo-50/30 transition-colors ${
                        status === "CRITICAL"
                          ? "bg-red-50/50 shadow-[inset_3px_0_0_0_theme(colors.red.500)]"
                          : status === "LOW COVER"
                          ? "bg-amber-50/40 shadow-[inset_3px_0_0_0_theme(colors.amber.400)]"
                          : i % 2 === 1
                          ? "bg-zinc-50/40"
                          : ""
                      }`}
                      onClick={() => setExpandedRow(i === expandedRow ? null : i)}
                    >
                      {tableColumns.map((col) => {
                        if (col === "listing_status") {
                          const ls = row.listing_status ?? "-";
                          const badge =
                            ls === "Active" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                            ls === "EOL"    ? "bg-red-50 text-red-700 border-red-200" :
                                             "bg-slate-50 text-slate-500 border-slate-200";
                          return (
                            <td key={col} className="px-2 py-1.5">
                              <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium border rounded ${badge}`}>
                                {ls}
                              </span>
                            </td>
                          );
                        }

                        if (col === "required_units" && row[col] > 0)
                          return (
                            <td key={col} className="px-2 py-1.5 text-right tabular-nums font-medium text-slate-900">
                              {row[col]}
                            </td>
                          );

                        if (col === "replenishment_qty")
                          return (
                            <td key={col} className="px-2 py-1.5 text-right tabular-nums font-bold text-slate-900">
                              {row[col] > 0 ? row[col] : <span className="text-slate-300">—</span>}
                            </td>
                          );

                        if (col === "warehouse_shortfall")
                          return (
                            <td key={col} className={`px-2 py-1.5 text-right tabular-nums ${row[col] > 0 ? "font-semibold text-orange-600" : "text-slate-400"}`}>
                              {row[col] > 0 ? row[col] : "—"}
                            </td>
                          );

                        if (col === "ixd_type")
                          return <td key={col} className="px-2 py-1.5 text-slate-600">{row.ixd_type}</td>;

                        if (col === "hazmat_type")
                          return <td key={col} className="px-2 py-1.5 text-slate-600">{row.hazmat_type}</td>;

                        if (col === "master_carton")
                          return (
                            <td key={col} className="px-2 py-1.5 text-right">
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
                                className="w-12 px-1 py-0.5 text-[11px] text-right tabular-nums bg-transparent border-0 border-b border-transparent hover:border-slate-200 focus:border-slate-900 focus:bg-slate-50 focus:outline-none rounded-none"
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
                            return <td key={col} className="px-2 py-1.5 text-slate-300">—</td>;

                          if (noCarton)
                            return (
                              <td key={col} className="px-2 py-1.5 text-slate-400 text-xs italic">
                                No carton set
                              </td>
                            );

                          return (
                            <td key={col} className="px-2 py-1.5 text-right tabular-nums">
                              <span
                                className={`font-bold ${breakFlag ? "text-orange-600" : row.ixd_type === "IXD" ? "text-blue-700" : "text-slate-900"}`}
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
                            return <td key={col} className="px-2 py-1.5 text-slate-300">—</td>;

                          if (noCarton)
                            return <td key={col} className="px-2 py-1.5 text-slate-300">—</td>;

                          return (
                            <td key={col} className="px-2 py-1.5">
                              <span
                                className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium border rounded tabular-nums ${
                                  row.ixd_type === "IXD"
                                    ? "bg-blue-50 text-blue-700 border-blue-200"
                                    : "bg-slate-50 text-slate-600 border-slate-200"
                                }`}
                                title={row.ixd_type === "IXD" ? "IXD — full cartons mandatory" : "Non-IXD — carton break allowed"}
                              >
                                {cartons} {cartons !== 1 ? "ctns" : "ctn"}
                              </span>
                            </td>
                          );
                        }
                        /* ── END CARTON COLUMNS ──────────────────────────── */

                        if (col === "working_value") {
                          const val = workingValues[row.sku] ?? row.working_value ?? "";
                          const hasVal = String(val).trim() !== "";
                          if (isReadOnly || currentWeekMeta?.locked) {
                            return (
                              <td key={col} className="px-2 py-1.5 bg-amber-50/60 text-right tabular-nums font-semibold text-zinc-900 shadow-[inset_2px_0_0_0_theme(colors.amber.400)]">
                                {hasVal ? val : <span className="text-zinc-300 font-normal">—</span>}
                              </td>
                            );
                          }
                          return (
                            <td className="px-2 py-1 bg-amber-50/60 text-right shadow-[inset_2px_0_0_0_theme(colors.amber.400)]">
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
                                className={`w-16 px-1.5 py-1 text-[12px] text-right tabular-nums font-bold bg-white/70 border border-amber-200/70 rounded shadow-sm hover:border-amber-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 focus:bg-white focus:outline-none placeholder:text-zinc-300 placeholder:font-normal transition-colors ${hasVal ? "text-amber-900" : "text-zinc-400"}`}
                              />
                            </td>
                          );
                        }

                        if (NUMERIC_COLS.has(col)) {
                          return (
                            <td key={col} className="px-2 py-1.5 text-right tabular-nums text-slate-700">
                              {row[col]}
                            </td>
                          );
                        }

                        return <td key={col} className="px-2 py-1.5 text-slate-700">{row[col]}</td>;
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
        <div className="flex justify-between items-center px-3 py-2 border-t border-slate-200 bg-slate-50/50">
          <button
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => p - 1)}
            className="text-xs text-slate-600 hover:text-slate-900 disabled:text-slate-300 disabled:cursor-not-allowed transition"
          >
            ← Previous
          </button>
          <div className="text-xs text-slate-500 tabular-nums">
            <span className="text-slate-900 font-medium">{currentPage}</span>
            <span className="text-slate-300 mx-1.5">/</span>
            <span>{totalPages || 1}</span>
          </div>
          <button
            disabled={currentPage === totalPages || totalPages === 0}
            onClick={() => setCurrentPage((p) => p + 1)}
            className="text-xs text-slate-600 hover:text-slate-900 disabled:text-slate-300 disabled:cursor-not-allowed transition"
          >
            Next →
          </button>
        </div>
      </div>

      {/* SOP MODAL */}
      <ReplenishmentSOPModal open={sopOpen} onClose={() => setSopOpen(false)} />

      {/* TEAM EXPORT MODAL */}
      <TeamExportModal
        open={exportOpen}
        rows={exportRows}
        format={exportFormat}
        weekLabel={exportWeekLabel}
        onClose={() => setExportOpen(false)}
      />

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

function ReplenishmentSOPModal({ open, onClose }) {
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
              How Replenishment is Calculated
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Applies to all 4 accounts — Nexlev, Viomi, Audio Array, White Mulberry
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
            Tells you how many units to send from your <b>Mother Warehouse</b> to Amazon FBA. Math runs live on the latest files.
          </p>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Top controls</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>Sales Window</b> — recent weeks used to compute weekly sales. <b>Default 12 weeks · maximum 12 (system cap)</b>. Changing this is a business-wide call.</li>
              <li><b>Replenish Weeks</b> — weeks of stock you want at Amazon (default 8)</li>
              <li><b>Working Week</b> — active save week. Past weeks are view-only.</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Columns</h3>
            <table className="w-full text-xs border-collapse">
              <tbody>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium w-32">AVG/WK</td><td className="border border-slate-300 px-2 py-1">Avg units sold per week (Total ÷ weeks in window)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">TOTAL</td><td className="border border-slate-300 px-2 py-1">Units sold in the window</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">AZ INV</td><td className="border border-slate-300 px-2 py-1">Stock sitting at Amazon FBA (sellable)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">INBOUND</td><td className="border border-slate-300 px-2 py-1">Already shipped to Amazon, not yet received</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">MOTHER WH</td><td className="border border-slate-300 px-2 py-1">Stock at your warehouse — what you can ship</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">REQ UNITS</td><td className="border border-slate-300 px-2 py-1">Target stock at Amazon = AVG/WK × Replenish Weeks</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">REPLEN</td><td className="border border-slate-300 px-2 py-1">Units to ship. <b>Never exceeds Mother WH stock.</b></td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium bg-amber-50">WORKING</td><td className="border border-slate-300 px-2 py-1 bg-amber-50">Your editable cell — pre-fills from REPLEN</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">RECOMMENDED</td><td className="border border-slate-300 px-2 py-1">REPLEN rounded to full Master Cartons</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">SHORTFALL</td><td className="border border-slate-300 px-2 py-1">Gap when Mother WH is short</td></tr>
              </tbody>
            </table>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Account rules</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>Nexlev / Viomi / White Mulberry</b> → counts <b>Amazon + 1p Sales</b> only</li>
              <li><b>Audio Array</b> → counts <b>Amazon only</b> (1p Sales excluded)</li>
              <li>Nexlev and Viomi <b>share the same sales</b> (both tagged "Nexlev" brand)</li>
              <li>Models in sales but missing from the master file are silently dropped</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Example</h3>
            <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
              Sold 80 in last 4 weeks → AVG/WK = 20 → 8-week target = 160 → Amazon has 50 → need 110 → Mother WH has 200 → <b>SHIP 110</b>.
              <br/>
              If Mother WH only had 70 → SHIP 70, SHORTFALL 40 (raise a China PO for 40).
            </p>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Working column</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li>Auto-saves as you type</li>
              <li>Week runs Sun → Sat; <b>locks at Saturday 11:59 PM IST</b></li>
              <li>Past weeks are view-only via the dropdown</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Filters &amp; Team Export</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li>Click <b>▽</b> on any column header to filter like Excel</li>
              <li>Green <b>Team Export</b> button → paste-ready table for your team (formatting carries over to Sheets/Excel/email)</li>
            </ul>
          </section>

        </div>
      </div>
    </div>
  );
}

function TeamExportModal({ open, onClose, rows, format, weekLabel }) {
  const [copied, setCopied] = useState(false);
  if (!open) return null;

  const sumWorking = (filter) =>
    rows.filter(filter).reduce((s, r) => s + (parseFloat(r.working_value) || 0), 0);

  let cols, tableRows, totalRow, titleSuffix;

  if (format === "audio_array") {
    titleSuffix = "Audio Array";
    cols = ["SKU", "ASIN", "MASTER CARTON", "MODEL", "Audio Array"];
    tableRows = rows.map(r => [
      r.sku || "",
      r.asin || "",
      r.master_carton ?? "",
      r.model || "",
      r.working_value || "",
    ]);
    const tot = sumWorking(() => true);
    totalRow = ["Total", "", "", "", tot || ""];
  } else if (format === "white_mulberry") {
    titleSuffix = "White Mulberry";
    cols = ["SKU", "ASIN", "HAZMAT TYPE", "MASTER CARTON", "MODEL", "Viomi Ac"];
    tableRows = rows.map(r => [
      r.sku || "",
      r.asin || "",
      r.hazmat_type || "",
      r.master_carton ?? "",
      r.model || "",
      r.working_value || "",
    ]);
    const tot = sumWorking(() => true);
    totalRow = ["Total", "", "", "", "", tot || ""];
  } else {
    // nexlev_viomi (default)
    titleSuffix = "Nexlev + Viomi";
    cols = [
      "SKU", "ASIN", "HAZMAT TYPE", "MASTER CARTON", "MODEL",
      "ISK3 NexLev AC", "ISK3 Viomi Ac", "Remarks",
    ];
    tableRows = rows.map(r => [
      r.sku || "",
      r.asin || "",
      r.hazmat_type || "",
      r.master_carton ?? "",
      r.model || "",
      r._src === "nx" ? (r.working_value || "") : "",
      r._src === "vm" ? (r.working_value || "") : "",
      "",
    ]);
    const nxTotal = sumWorking(r => r._src === "nx");
    const vmTotal = sumWorking(r => r._src === "vm");
    totalRow = ["Total", "", "", "", "", nxTotal || "", vmTotal || "", ""];
  }

  function buildTSV() {
    const header = cols.join("\t");
    const lines = tableRows.map(r => r.join("\t"));
    return [header, ...lines, totalRow.join("\t")].join("\n");
  }

  function escHTML(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Excel/Sheets-friendly HTML with inline styles for bold header+footer,
  // text wrap, and center+middle alignment.
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
    // .xls file that's actually HTML — Excel opens it natively and keeps styles.
    const doc =
      `<html xmlns:o="urn:schemas-microsoft-com:office:office" ` +
      `xmlns:x="urn:schemas-microsoft-com:office:excel"><head>` +
      `<meta charset="utf-8"></head><body>${buildHTMLTable()}</body></html>`;
    const blob = new Blob([doc], { type: "application/vnd.ms-excel;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `team_export_${weekLabel.replace(/\s/g, "_")}.xls`;
    a.click();
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-6xl max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              Team Export — {weekLabel}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              {titleSuffix} · {rows.length} row{rows.length !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={copy}
              disabled={rows.length === 0}
              className="px-3 py-1.5 bg-indigo-600 text-white text-xs font-semibold rounded hover:bg-indigo-700 disabled:opacity-40"
            >
              {copied ? "Copied!" : "Copy to clipboard"}
            </button>
            <button
              onClick={download}
              disabled={rows.length === 0}
              className="px-3 py-1.5 bg-indigo-600 text-white text-xs font-semibold rounded hover:bg-indigo-700 disabled:opacity-40"
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
              Save Working values for {titleSuffix} for this week first,
              then click Team Export again.
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
                  {["Total", "", "", "", "", nxTotal || "", vmTotal || "", ""].map((v, j) => (
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
          className="flex-1 px-3 py-1.5 bg-indigo-600 text-white text-xs font-semibold rounded hover:bg-indigo-700"
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

function KpiTile({ label, value, accent = "indigo", hint }) {
  const accentMap = {
    indigo: { bar: "bg-indigo-500", num: "text-zinc-900", tile: "from-indigo-50/40" },
    amber:  { bar: "bg-amber-500",  num: value > 0 ? "text-amber-700" : "text-zinc-400", tile: "from-amber-50/40" },
    red:    { bar: "bg-red-500",    num: value > 0 ? "text-red-700"   : "text-zinc-400", tile: "from-red-50/40" },
    zinc:   { bar: "bg-zinc-400",   num: "text-zinc-900", tile: "from-zinc-50/40" },
  };
  const c = accentMap[accent] || accentMap.zinc;
  const display = typeof value === "number" ? value.toLocaleString() : value;
  return (
    <div className={`relative bg-white border border-zinc-200 rounded-lg shadow-sm overflow-hidden bg-gradient-to-br ${c.tile} to-transparent`}>
      <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${c.bar}`}></div>
      <div className="px-3.5 py-2.5">
        <div className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">{label}</div>
        <div className={`tabular-nums text-2xl font-semibold mt-0.5 leading-tight ${c.num}`}>{display}</div>
        {hint && <div className="text-[10.5px] text-zinc-500 mt-0.5">{hint}</div>}
      </div>
    </div>
  );
}

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
