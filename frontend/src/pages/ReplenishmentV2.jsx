import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Search, Download, Save, ChevronDown, ChevronRight, Settings2,
} from "lucide-react";

import { getReplenishment, getKPIs } from "../api/replenishment";
import { logUsage } from "../auth/usage";
import { Sparkline, classifyTrend } from "../components/Sparkline";
import { DetailRow } from "../components/DetailRow";
import { CommandPalette } from "../components/CommandPalette";
import { SavedViews } from "../components/SavedViews";
import { cn } from "../lib/cn";

/* ============================================================
   REPLENISHMENT V2 — TanStack + shadcn-style
   Preserves existing logic:
     - getReplenishment / getKPIs
     - saved-weeks + saved-week-data flows
     - Working Value persistence
     - Master Carton edit
============================================================ */

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

export default function ReplenishmentV2() {
  /* ─────────── filters / window ─────────── */
  const [fromWeek, setFromWeek] = useState(1);
  const [toWeek, setToWeek] = useState(12);
  const [replenishWeeks, setReplenishWeeks] = useState(8);
  const [account, setAccount] = useState("NEXLEV");

  /* ─────────── data ─────────── */
  const [kpis, setKpis] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  /* ─────────── ui state ─────────── */
  const [search, setSearch] = useState("");
  const [view, setView] = useState("all");
  const [sorting, setSorting] = useState([]);
  const [expandedSku, setExpandedSku] = useState(null);
  const [density, setDensity] = useState("cozy");

  /* ─────────── week-save flow ─────────── */
  const [weekStart, setWeekStart] = useState(null);
  const [currentWeekMeta, setCurrentWeekMeta] = useState(null);
  const [pastWeekMeta, setPastWeekMeta] = useState(null);
  const [savedWeeks, setSavedWeeks] = useState([]);
  const [workingValues, setWorkingValues] = useState({});
  const [masterCartons, setMasterCartons] = useState({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const isReadOnly = weekStart !== null;

  /* ─────────── range-select ─────────── */
  const [selRange, setSelRange] = useState(null);
  const draggingRef = useRef(null);

  /* ============================================================
     LOAD
  ============================================================ */
  useEffect(() => {
    fetch(`${BASE}/replenishment/saved-weeks?account=${account}`)
      .then(r => r.json())
      .then(res => {
        setCurrentWeekMeta(res.current_week || null);
        setSavedWeeks(res.saved_weeks || []);
      })
      .catch(() => {});
  }, [account]);

  useEffect(() => {
    setLoading(true);
    setPastWeekMeta(null);
    setExpandedSku(null);

    const loadCurrent = () => Promise.all([
      getKPIs(fromWeek, toWeek),
      getReplenishment(toWeek - fromWeek + 1, replenishWeeks, account),
    ]).then(([kpiRes, replRes]) => {
      setKpis(kpiRes);
      const data = Array.isArray(replRes) ? replRes : [];
      data.forEach(r => { r.master_carton = masterCartons[r.model] ?? r.master_carton ?? ""; });
      setRows(data);
      const wv = {};
      data.forEach(r => { if (r.sku && r.working_value) wv[r.sku] = r.working_value; });
      setWorkingValues(wv);
      setDirty(false);
    });

    const loadPast = (ws) => fetch(
      `${BASE}/replenishment/saved-week-data?account=${account}&week_start=${ws}`
    ).then(r => r.json()).then(j => {
      const data = Array.isArray(j.rows) ? j.rows : [];
      setRows(data);
      setPastWeekMeta({ week_start: j.week_start, week_end: j.week_end, label: j.label });
      const wv = {};
      data.forEach(r => { if (r.sku && r.working_value) wv[r.sku] = r.working_value; });
      setWorkingValues(wv);
      setDirty(false);
      setKpis(null);
    });

    (weekStart ? loadPast(weekStart) : loadCurrent()).finally(() => setLoading(false));
  }, [fromWeek, toWeek, replenishWeeks, account, weekStart]);

  /* ============================================================
     SAVE WEEK
  ============================================================ */
  async function saveWeek() {
    if (saving) return;
    setSaving(true);
    setSaveMsg("");
    try {
      const payload = rows.map(r => ({
        ...r,
        working_value: workingValues[r.sku] ?? r.working_value ?? "",
      }));
      const res = await fetch(`${BASE}/replenishment/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account, rows: payload }),
      });
      const j = await res.json();
      if (j.status === "saved") {
        setSaveMsg(`Saved ${j.rows} rows · ${j.label}`);
        setDirty(false);
        logUsage("save", "replenishment", { account, rows: j.rows, week_start: j.week_start });
        fetch(`${BASE}/replenishment/saved-weeks?account=${account}`)
          .then(r => r.json())
          .then(res => setSavedWeeks(res.saved_weeks || []))
          .catch(() => {});
      } else {
        setSaveMsg(j.error || "Save failed");
      }
    } catch (e) {
      setSaveMsg(e.message);
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(""), 6000);
    }
  }

  /* ============================================================
     DERIVED
  ============================================================ */
  const categories = useMemo(
    () => [...new Set(rows.map(r => r.category).filter(Boolean))].sort(),
    [rows]
  );

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter(r => {
      if (q && !(
        (r.model || "").toLowerCase().includes(q) ||
        (r.sku   || "").toLowerCase().includes(q) ||
        (r.asin  || "").toLowerCase().includes(q)
      )) return false;
      if (view === "critical")  return r.is_risky;
      if (view === "bumped")    return r.velocity_basis === "4wk";
      if (view === "shortfall") return (r.warehouse_shortfall || 0) > 0;
      if (view === "overstock") return r.is_overstock;
      if (view === "hazmat") {
        const h = (r.hazmat_type || "").toLowerCase();
        return h.includes("hazmat") && !h.includes("non");
      }
      return true;
    });
  }, [rows, search, view]);

  const views = useMemo(() => [
    { key: "all",       label: "All",            count: rows.length },
    { key: "critical",  label: "Critical",       count: rows.filter(r => r.is_risky).length, accent: "bg-red-100 text-red-700" },
    { key: "bumped",    label: "4wk Bumped",     count: rows.filter(r => r.velocity_basis === "4wk").length },
    { key: "shortfall", label: "Has Shortfall",  count: rows.filter(r => (r.warehouse_shortfall || 0) > 0).length },
    { key: "overstock", label: "Overstock",      count: rows.filter(r => r.is_overstock).length },
    { key: "hazmat",    label: "Hazmat only",    count: rows.filter(r => {
      const h = (r.hazmat_type || "").toLowerCase();
      return h.includes("hazmat") && !h.includes("non");
    }).length },
  ], [rows]);

  /* ============================================================
     COLUMNS
  ============================================================ */
  const columns = useMemo(() => [
    { id: "model",            accessorKey: "model",            header: "Model",     size: 150, meta: { sticky: 1, group: "id" } },
    { id: "sku",              accessorKey: "sku",              header: "SKU",       size: 110, meta: { sticky: 2, group: "id" } },
    { id: "asin",             accessorKey: "asin",             header: "ASIN",      size: 110, meta: { group: "list" } },
    { id: "listing_status",   accessorKey: "listing_status",   header: "Status",    size: 80,  meta: { group: "list" } },
    { id: "trend",            accessorFn: r => classifyTrend(r.weekly_sales || []), header: "Trend", size: 130, meta: { group: "vel" } },
    { id: "sales_velocity",   accessorKey: "sales_velocity",   header: "Avg/Wk",    size: 90,  meta: { group: "vel", numeric: true, sortDescFirst: true } },
    { id: "last_4_velocity",  accessorKey: "last_4_velocity",  header: "4wk",       size: 70,  meta: { group: "vel", numeric: true, sortDescFirst: true } },
    { id: "total_units_sold", accessorKey: "total_units_sold", header: "Total",     size: 80,  meta: { group: "vel", numeric: true, sortDescFirst: true } },
    { id: "amazon_inventory", accessorKey: "amazon_inventory", header: "AZ Inv",    size: 80,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "inbound_inventory",accessorKey: "inbound_inventory",header: "Inbound",   size: 80,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "ampm_inventory",   accessorKey: "ampm_inventory",   header: "Mother WH", size: 100, meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "b2b_inventory",    accessorKey: "b2b_inventory",    header: "B2B",       size: 70,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "required_units",   accessorKey: "required_units",   header: "Req",       size: 70,  meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "warehouse_shortfall", accessorKey: "warehouse_shortfall", header: "Shortfall", size: 90, meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "replenishment_qty",accessorKey: "replenishment_qty",header: "Replen Qty",size: 100, meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "working_value",    accessorKey: "working_value",    header: "Working",   size: 90,  meta: { group: "rep" } },
    { id: "ixd_type",         accessorKey: "ixd_type",         header: "IXD",       size: 70,  meta: { group: "log" } },
    { id: "master_carton",    accessorKey: "master_carton",    header: "MC",        size: 60,  meta: { group: "log" } },
  ], []);

  const table = useReactTable({
    data: filteredRows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  /* ============================================================
     RANGE-SELECT
  ============================================================ */
  function onCellMouseDown(rowIdx, colIdx, e) {
    if (e.button !== 0) return;
    e.stopPropagation();
    draggingRef.current = { fromRow: rowIdx, fromCol: colIdx, toRow: rowIdx, toCol: colIdx };
    setSelRange({ ...draggingRef.current });
  }
  function onCellMouseEnter(rowIdx, colIdx) {
    if (!draggingRef.current) return;
    draggingRef.current.toRow = rowIdx;
    draggingRef.current.toCol = colIdx;
    setSelRange({ ...draggingRef.current });
  }
  useEffect(() => {
    const up = () => { draggingRef.current = null; };
    window.addEventListener("mouseup", up);
    return () => window.removeEventListener("mouseup", up);
  }, []);

  const selectedCells = useMemo(() => {
    if (!selRange) return [];
    const r0 = Math.min(selRange.fromRow, selRange.toRow);
    const r1 = Math.max(selRange.fromRow, selRange.toRow);
    const c0 = Math.min(selRange.fromCol, selRange.toCol);
    const c1 = Math.max(selRange.fromCol, selRange.toCol);
    const sortedRows = table.getRowModel().rows;
    const out = [];
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const col = columns[c];
        if (!col) continue;
        const original = sortedRows[r]?.original;
        if (!original) continue;
        out.push({ rowIdx: r, colIdx: c, value: original[col.id], numeric: !!col.meta?.numeric });
      }
    }
    return out;
  }, [selRange, table, columns]);

  const selectionSummary = useMemo(() => {
    if (selectedCells.length === 0) return null;
    const nums = selectedCells.filter(c => c.numeric).map(c => Number(c.value) || 0);
    return { count: selectedCells.length, sum: nums.reduce((a, b) => a + b, 0) };
  }, [selectedCells]);

  useEffect(() => {
    function onCopy(e) {
      if (!selRange || selectedCells.length === 0) return;
      e.preventDefault();
      const r0 = Math.min(selRange.fromRow, selRange.toRow);
      const r1 = Math.max(selRange.fromRow, selRange.toRow);
      const c0 = Math.min(selRange.fromCol, selRange.toCol);
      const c1 = Math.max(selRange.fromCol, selRange.toCol);
      const sortedRows = table.getRowModel().rows;
      const lines = [];
      for (let r = r0; r <= r1; r++) {
        const cells = [];
        for (let c = c0; c <= c1; c++) {
          const colId = columns[c]?.id;
          const v = sortedRows[r]?.original?.[colId];
          cells.push(v == null ? "" : String(v));
        }
        lines.push(cells.join("\t"));
      }
      e.clipboardData.setData("text/plain", lines.join("\n"));
    }
    document.addEventListener("copy", onCopy);
    return () => document.removeEventListener("copy", onCopy);
  }, [selRange, selectedCells, columns, table]);

  /* ============================================================
     GROUPED HEADER BAND
  ============================================================ */
  const groupMeta = {
    id:   { label: "Identity",          tint: "" },
    list: { label: "Listing",           tint: "" },
    vel:  { label: "Velocity · 12 wks", tint: "bg-indigo-50 text-indigo-700" },
    inv:  { label: "Inventory",         tint: "bg-slate-100" },
    rep:  { label: "Replen",            tint: "" },
    log:  { label: "Logistics",         tint: "" },
  };
  const groupedHeaders = useMemo(() => {
    const out = [];
    let prev = null;
    columns.forEach(c => {
      const g = c.meta?.group || "_";
      if (g === prev) out[out.length - 1].span += 1;
      else { out.push({ key: g, ...groupMeta[g], span: 1 }); prev = g; }
    });
    return out;
  }, [columns]);

  /* ============================================================
     DENSITY
  ============================================================ */
  const densityCls = {
    comfy:   "[&_td]:py-2.5",
    cozy:    "[&_td]:py-1.5",
    compact: "[&_td]:py-0.5 text-[12px]",
  }[density];

  /* ============================================================
     EXPORT CSV
  ============================================================ */
  function exportCSV() {
    const order = columns.map(c => c.id);
    const headers = order.map(id => {
      const col = columns.find(c => c.id === id);
      return typeof col.header === "string" ? col.header : id;
    });
    const lines = [headers.join(",")];
    table.getSortedRowModel().rows.forEach(({ original: r }) => {
      const cells = order.map(id => {
        let v = id === "working_value"
          ? (workingValues[r.sku] ?? r.working_value ?? "")
          : id === "master_carton"
            ? (masterCartons[r.model] ?? r.master_carton ?? "")
            : r[id];
        if (v == null) v = "";
        const s = String(v).replace(/"/g, '""');
        return /[",\n]/.test(s) ? `"${s}"` : s;
      });
      lines.push(cells.join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `replenishment_${account.toLowerCase()}_${view}.csv`;
    a.click();
  }

  /* ============================================================
     PALETTE PICK
  ============================================================ */
  function onPaletteSelect(item) {
    if (item.type === "sku") {
      setExpandedSku(item.payload.sku);
      requestAnimationFrame(() => {
        const el = document.querySelector(`[data-row-sku="${item.payload.sku}"]`);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    } else if (item.type === "view") {
      setView(item.payload.key);
    } else if (item.type === "action" && item.payload === "export") {
      exportCSV();
    }
  }

  /* ============================================================
     RENDER
  ============================================================ */
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="w-full px-6 pt-5 pb-10">
        {/* Header row */}
        <div className="flex items-end justify-between mb-4">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-500 font-medium">Account</div>
            <h1 className="text-2xl font-semibold mt-0.5 tracking-tight inline-flex items-center gap-1">
              <select
                value={account}
                onChange={e => setAccount(e.target.value)}
                className="bg-transparent border-none -ml-1 pl-1 pr-6 py-0 text-2xl font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-500/40 rounded"
              >
                <option value="NEXLEV">Nexlev</option>
                <option value="VIOMI">Viomi</option>
                <option value="AUDIO ARRAY">Audio Array</option>
                <option value="WHITE MULBERRY">White Mulberry</option>
              </select>
              <span className="text-slate-300 font-normal">·</span>
              <span className="text-slate-500 text-lg font-medium">Replenishment</span>
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-2 px-3 py-2 rounded-md bg-white border border-slate-200 text-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-slate-700">
                {pastWeekMeta?.label || currentWeekMeta?.label || `Week ${toWeek}`}
                {isReadOnly && <span className="text-slate-400"> · view only</span>}
                {!isReadOnly && currentWeekMeta?.locked && <span className="text-amber-700"> · locked</span>}
              </span>
            </div>
            <button onClick={exportCSV} className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            {!isReadOnly && (
              <button
                onClick={saveWeek}
                disabled={saving || currentWeekMeta?.locked}
                className="px-3 py-2 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                <Save className="w-3.5 h-3.5" />
                {saving ? "Saving…" : "Save Week"}
              </button>
            )}
          </div>
        </div>

        {/* KPI strip */}
        <div className="grid grid-cols-5 gap-3 mb-5">
          <KPICard label="Total Models" value={rows.length} hint={`across ${categories.length} categories`} />
          <KPICard label="Critical"     value={rows.filter(r => r.is_risky).length}                               hint="below 1-week cover" tone="bad" />
          <KPICard label="Replen Qty"   value={rows.reduce((a, r) => a + (r.replenishment_qty || 0), 0)}          hint="units to ship this week" />
          <KPICard label="WH Shortfall" value={rows.reduce((a, r) => a + (r.warehouse_shortfall || 0), 0)}        hint="AMPM can't cover" tone="warn" />
          <KPICard label="4wk Bump"     value={rows.filter(r => r.velocity_basis === "4wk").length}              hint="SKUs using 4-wk avg" tone="brand" />
        </div>

        {/* Saved views */}
        <div className="mb-3">
          <SavedViews views={views} active={view} onPick={setView} />
        </div>

        {/* Filters */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-3 mb-3">
          <div className="grid grid-cols-12 gap-3 items-end">
            <div className="col-span-3">
              <Label>Search</Label>
              <div className="relative">
                <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-300" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"
                  placeholder="SKU / Model / ASIN…"
                />
              </div>
            </div>

            <div className="col-span-2">
              <Label>Sales Window</Label>
              <div className="grid grid-cols-2 gap-1.5">
                <select value={fromWeek} onChange={e => setFromWeek(Number(e.target.value))}
                  className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                  {[...Array(12)].map((_, i) => <option key={i+1} value={i+1}>From {i+1}</option>)}
                </select>
                <select value={toWeek} onChange={e => setToWeek(Number(e.target.value))}
                  className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                  {[...Array(12)].map((_, i) => <option key={i+1} value={i+1}>To {i+1}</option>)}
                </select>
              </div>
            </div>

            <div className="col-span-1">
              <Label>Replen Wks</Label>
              <select value={replenishWeeks} onChange={e => setReplenishWeeks(Number(e.target.value))}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                {[4, 6, 8, 10, 12].map(n => <option key={n}>{n}</option>)}
              </select>
            </div>

            <div className="col-span-2">
              <Label>Past Week</Label>
              <select
                value={weekStart || ""}
                onChange={e => setWeekStart(e.target.value || null)}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
              >
                <option value="">Current week</option>
                {savedWeeks.map(w => <option key={w.week_start} value={w.week_start}>{w.label}</option>)}
              </select>
            </div>

            <div className="col-span-2">
              <Label>Status</Label>
              <div className="text-xs text-slate-500 truncate">
                {loading ? "Loading…" : `${filteredRows.length} of ${rows.length} rows`}
              </div>
              {saveMsg && <div className="text-xs text-indigo-700 mt-1">{saveMsg}</div>}
            </div>

            <div className="col-span-2 flex items-center gap-2 justify-end">
              <div className="inline-flex rounded-md border border-slate-200 bg-white">
                {["comfy", "cozy", "compact"].map(d => (
                  <button key={d} onClick={() => setDensity(d)}
                    className={cn(
                      "px-2 py-1 text-xs font-medium",
                      density === d ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-50"
                    )}
                    title={d}
                  >
                    {d === "comfy" ? "≡" : d === "cozy" ? "≣" : "≣≣"}
                  </button>
                ))}
              </div>
              <button className="px-3 py-1.5 text-xs font-medium rounded-md border border-slate-200 bg-white hover:bg-slate-50 inline-flex items-center gap-1.5">
                <Settings2 className="w-3.5 h-3.5" /> Columns
              </button>
            </div>
          </div>
        </div>

        {/* TABLE */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className={cn("w-full text-sm", densityCls)}>
              <thead>
                {/* Grouped band */}
                <tr className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                  {groupedHeaders.map((g, i) => (
                    <th key={i} colSpan={g.span}
                        className={cn("px-3 py-2 text-center border-b border-slate-200", g.tint, i > 0 && "border-l")}>
                      {g.label}
                    </th>
                  ))}
                </tr>
                {/* Column row */}
                {table.getHeaderGroups().map(hg => (
                  <tr key={hg.id} className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-700 font-semibold">
                    {hg.headers.map(h => {
                      const meta = h.column.columnDef.meta || {};
                      return (
                        <th
                          key={h.id}
                          onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                          style={{ width: h.getSize() }}
                          className={cn(
                            "px-3 py-2.5 border-b-2 border-slate-300 select-none",
                            meta.numeric ? "text-right" : "text-left",
                            h.column.getCanSort() && "cursor-pointer hover:bg-slate-100",
                            meta.sticky === 1 && "sticky left-0 z-10 bg-slate-50 shadow-[1px_0_0_#e2e8f0]",
                            meta.sticky === 2 && "sticky left-[150px] z-10 bg-slate-50 shadow-[1px_0_0_#e2e8f0]",
                            meta.group === "vel" && "bg-indigo-50/60"
                          )}
                        >
                          <span className="inline-flex items-center gap-1">
                            {flexRender(h.column.columnDef.header, h.getContext())}
                            {h.column.getIsSorted() === "asc"  && "▲"}
                            {h.column.getIsSorted() === "desc" && "▼"}
                          </span>
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>

              <tbody className="text-slate-700 [&_td]:px-3 [&_tr]:border-b [&_tr]:border-slate-100">
                {table.getRowModel().rows.map((trow, ri) => {
                  const r = trow.original;
                  const isExpanded = expandedSku === r.sku;
                  const isCritical = r.is_risky;
                  const isBumped   = r.velocity_basis === "4wk";

                  return (
                    <React.Fragment key={r.sku || ri}>
                      <tr
                        data-row-sku={r.sku}
                        className={cn(
                          "hover:bg-slate-50/60 cursor-pointer",
                          isCritical && "bg-red-50/40 hover:bg-red-50/60",
                          isExpanded && "bg-indigo-50/30",
                        )}
                        onClick={() => setExpandedSku(isExpanded ? null : r.sku)}
                      >
                        {trow.getVisibleCells().map((cell, ci) => {
                          const colId = cell.column.id;
                          const meta = cell.column.columnDef.meta || {};
                          const isSelected = selectedCells.some(s => s.rowIdx === ri && s.colIdx === ci);

                          let content;
                          if (colId === "model") {
                            content = (
                              <span className="font-semibold text-slate-900 inline-flex items-center gap-1">
                                {isExpanded
                                  ? <ChevronDown  className="w-3.5 h-3.5 text-indigo-600" />
                                  : <ChevronRight className="w-3.5 h-3.5 text-slate-300" />}
                                {r.model}
                              </span>
                            );
                          } else if (colId === "sku") {
                            content = <span className="font-mono text-xs text-slate-700">{r.sku}</span>;
                          } else if (colId === "asin") {
                            content = <span className="font-mono text-xs text-slate-500">{r.asin || "—"}</span>;
                          } else if (colId === "listing_status") {
                            content = <StatusPill status={r.listing_status} />;
                          } else if (colId === "trend") {
                            content = <Sparkline data={r.weekly_sales || []} />;
                          } else if (colId === "sales_velocity") {
                            content = (
                              <span className="font-semibold tabular-nums">
                                {r.sales_velocity}
                                {isBumped && (
                                  <span className="inline-flex ml-1 px-1 py-0.5 text-[9px] font-bold rounded bg-indigo-100 text-indigo-700">4wk</span>
                                )}
                              </span>
                            );
                          } else if (colId === "warehouse_shortfall") {
                            content = (
                              <span className={cn("tabular-nums", (r.warehouse_shortfall || 0) > 0 && "text-amber-700 font-semibold")}>
                                {r.warehouse_shortfall > 0 ? r.warehouse_shortfall : "—"}
                              </span>
                            );
                          } else if (colId === "amazon_inventory") {
                            content = (
                              <span className={cn("tabular-nums font-medium", isCritical && "text-red-700")}>
                                {r.amazon_inventory}
                              </span>
                            );
                          } else if (colId === "replenishment_qty") {
                            content = <span className="font-bold tabular-nums text-slate-900">{r.replenishment_qty}</span>;
                          } else if (colId === "working_value") {
                            content = (
                              <input
                                type="text"
                                value={workingValues[r.sku] ?? r.working_value ?? ""}
                                disabled={isReadOnly}
                                onClick={e => e.stopPropagation()}
                                onChange={e => {
                                  setWorkingValues(p => ({ ...p, [r.sku]: e.target.value }));
                                  setDirty(true);
                                }}
                                className="w-16 text-right px-1.5 py-1 border border-slate-200 rounded text-xs font-mono disabled:bg-slate-50"
                              />
                            );
                          } else if (colId === "master_carton") {
                            content = (
                              <input
                                type="text"
                                value={masterCartons[r.model] ?? r.master_carton ?? ""}
                                onClick={e => e.stopPropagation()}
                                onChange={async (e) => {
                                  const value = e.target.value;
                                  setMasterCartons(p => ({ ...p, [r.model]: value }));
                                  try {
                                    await fetch(`${BASE}/save-master-carton`, {
                                      method: "POST",
                                      headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify({ model: r.model, master_carton: value }),
                                    });
                                  } catch {}
                                }}
                                className="w-12 text-right px-1.5 py-1 border border-slate-200 rounded text-xs font-mono"
                              />
                            );
                          } else if (colId === "ixd_type") {
                            content = <span className="text-slate-500 text-xs">{r.ixd_type || "—"}</span>;
                          } else {
                            content = (
                              <span className="tabular-nums">
                                {r[colId] ?? "—"}
                              </span>
                            );
                          }

                          return (
                            <td
                              key={cell.id}
                              onMouseDown={meta.numeric ? (e) => onCellMouseDown(ri, ci, e) : undefined}
                              onMouseEnter={() => onCellMouseEnter(ri, ci)}
                              className={cn(
                                meta.numeric ? "text-right" : "text-left",
                                meta.sticky === 1 && "sticky left-0 bg-white z-[1] shadow-[1px_0_0_#e2e8f0]",
                                meta.sticky === 2 && "sticky left-[150px] bg-white z-[1] shadow-[1px_0_0_#e2e8f0]",
                                isExpanded && meta.sticky && "!bg-indigo-50",
                                meta.group === "vel" && isBumped && colId !== "trend" && "bg-indigo-50/40",
                                isSelected && "bg-indigo-100 outline outline-1 outline-indigo-500 outline-offset-[-1px]",
                              )}
                            >
                              {content}
                            </td>
                          );
                        })}
                      </tr>

                      {isExpanded && (
                        <DetailRow row={r} colSpan={columns.length} allRows={rows} />
                      )}
                    </React.Fragment>
                  );
                })}

                {filteredRows.length === 0 && !loading && (
                  <tr>
                    <td colSpan={columns.length} className="text-center py-10 text-slate-400 text-sm">
                      No SKUs match the current view + search.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-t border-slate-200 text-xs text-slate-500">
            <div>
              {selectionSummary ? (
                <>
                  <span className="font-semibold text-slate-900">{selectionSummary.count} cells selected</span> · Sum <span className="font-mono font-semibold text-slate-900">{selectionSummary.sum.toLocaleString()}</span>
                  <span className="text-indigo-600 ml-2">⌘C to copy</span>
                </>
              ) : (
                <>Drag across numeric cells to range-select · <kbd className="px-1 py-0.5 rounded bg-slate-200 text-[10px] font-mono">⌘K</kbd> for command palette</>
              )}
            </div>
            <div>
              Showing <span className="font-semibold text-slate-900">{filteredRows.length}</span> of {rows.length} rows
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="mt-4 flex flex-wrap gap-5 text-xs text-slate-500 px-1">
          <Legend swatch="bg-red-100"     label="Critical row (stock-out risk)" />
          <Legend swatch="bg-amber-100"   label="Warehouse shortfall" />
          <Legend swatch="bg-indigo-50 border border-indigo-100" label="4-wk velocity bump applied" />
          <Legend swatch="bg-indigo-100"  label="Range-selected (drag numeric cells)" />
        </div>
      </div>

      {/* Command palette */}
      <CommandPalette
        rows={rows}
        views={views.map(v => ({ key: v.key, label: v.label, hint: `${v.count} SKUs` }))}
        onPick={onPaletteSelect}
      />
    </div>
  );
}

/* ============================================================
   PRIMITIVES
============================================================ */

function KPICard({ label, value, hint, tone }) {
  const toneCls = {
    bad:   "text-red-700",
    warn:  "text-amber-700",
    brand: "text-indigo-700",
  }[tone] || "text-slate-900";
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
      <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">{label}</div>
      <div className={cn("text-2xl font-semibold mt-1.5 tabular-nums", toneCls)}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      <div className="text-xs text-slate-500 mt-0.5">{hint}</div>
    </div>
  );
}

function Label({ children }) {
  return (
    <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1 block">
      {children}
    </label>
  );
}

function StatusPill({ status }) {
  const s = String(status || "").trim();
  if (s === "Active")
    return <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-100 text-emerald-700">Active</span>;
  if (s === "EOL" || s === "Inactive")
    return <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-red-100 text-red-700">{s}</span>;
  if (s.toLowerCase().includes("low") || s.toLowerCase().includes("hold"))
    return <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-amber-100 text-amber-700">{s}</span>;
  return <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-slate-100 text-slate-600">{s || "—"}</span>;
}

function Legend({ swatch, label }) {
  return (
    <div className="flex items-center gap-2">
      <span className={cn("w-3 h-3 rounded", swatch)} />
      <span>{label}</span>
    </div>
  );
}
