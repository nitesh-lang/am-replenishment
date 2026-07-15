import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Search, Download, Save, ChevronDown, ChevronRight,
  Settings2, RotateCcw,
} from "lucide-react";

import { logUsage } from "../auth/usage";
import { CommandPalette } from "../components/CommandPalette";
import { SavedViews } from "../components/SavedViews";
import { SOPModal, SOPButton } from "../components/SOPModal";
import { CBReplenishmentSOPContent } from "../components/SOPContents";
import DataFreshnessBanner from "../components/DataFreshnessBanner";
import { cn } from "../lib/cn";

/* ============================================================
   CB REPLENISHMENT V2 — TanStack + v2 pattern
   Preserves existing endpoints + handlers:
     GET  /api/cb-replenishment/?cover_weeks=…&from_week=…&to_week=…
     GET  /api/cb-replenishment/saved-weeks
     GET  /api/cb-replenishment/saved-week-data?week_start=…
     POST /api/cb-replenishment/save-working   (debounced auto-save)
     POST /api/cb-replenishment/reset
============================================================ */

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

export default function CBReplenishmentV2() {
  /* ─────────── state ─────────── */
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek,   setToWeek]   = useState(null);
  const [coverWeeks, setCoverWeeks] = useState(8);
  const [availableWeeks, setAvailableWeeks] = useState([]);

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [view, setView] = useState("all");
  const [brand, setBrand] = useState("All");
  const [sorting, setSorting] = useState([]);
  const [expandedModel, setExpandedModel] = useState(null);
  const [density, setDensity] = useState("cozy");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 100;

  /* Working values + remarks (debounced auto-save) */
  const [workingValues, setWorkingValues] = useState({});
  const [remarksValues, setRemarksValues] = useState({});
  const [savingMap, setSavingMap]         = useState({});
  const saveTimersRef = useRef({});

  /* Week save flow */
  const [weekStart, setWeekStart] = useState(null);
  const [currentWeekMeta, setCurrentWeekMeta] = useState(null);
  const [pastWeekMeta, setPastWeekMeta] = useState(null);
  const [savedWeeks, setSavedWeeks] = useState([]);
  const isReadOnly = weekStart !== null;
  const isLocked = isReadOnly || currentWeekMeta?.locked;

  /* SP-API CB SOH last-synced date (from vendor_soh_audio_array.csv) */
  const [cbSohSyncedDate, setCbSohSyncedDate] = useState("");

  /* Range-select */
  const [selRange, setSelRange] = useState(null);
  const draggingRef = useRef(null);

  /* SOP modal */
  const [sopOpen, setSopOpen] = useState(false);

  /* ============================================================
     LOAD
  ============================================================ */
  useEffect(() => {
    fetch(`${BASE}/api/cb-replenishment/saved-weeks`)
      .then(res => res.json())
      .then(res => {
        setCurrentWeekMeta(res.current_week || null);
        setSavedWeeks(res.saved_weeks || []);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    setPastWeekMeta(null);
    setExpandedModel(null);

    const seed = (list) => {
      const wv = {}, rk = {};
      list.forEach(r => {
        if (!r.model) return;
        if (r.working_value != null && String(r.working_value).trim() !== "") wv[r.model] = String(r.working_value);
        if (r.remarks       != null && String(r.remarks).trim() !== "")       rk[r.model] = String(r.remarks);
      });
      setWorkingValues(wv);
      setRemarksValues(rk);
    };

    const loadCurrent = () => {
      const params = new URLSearchParams({ cover_weeks: coverWeeks });
      if (fromWeek) params.append("from_week", fromWeek);
      if (toWeek)   params.append("to_week",   toWeek);
      return fetch(`${BASE}/api/cb-replenishment/?${params}`)
        .then(res => res.json())
        .then(res => {
          const list = res.data || [];
          setRows(list);
          seed(list);
          setCbSohSyncedDate(res.cb_soh_synced_date || "");
          if (res.available_weeks?.length) {
            const weeks = res.available_weeks;
            setAvailableWeeks(weeks);
            if (!fromWeek) setFromWeek(weeks[0]);
            if (!toWeek)   setToWeek(weeks[weeks.length - 1]);
          }
        });
    };

    const loadPast = (ws) =>
      fetch(`${BASE}/api/cb-replenishment/saved-week-data?week_start=${ws}`)
        .then(res => res.json())
        .then(j => {
          const list = Array.isArray(j.rows) ? j.rows : [];
          setRows(list);
          setPastWeekMeta({ week_start: j.week_start, week_end: j.week_end, label: j.label });
          seed(list);
        });

    (weekStart ? loadPast(weekStart) : loadCurrent()).finally(() => setLoading(false));
  }, [fromWeek, toWeek, coverWeeks, weekStart]);

  useEffect(() => { setPage(1); }, [search, view, brand, fromWeek, toWeek]);

  /* ============================================================
     AUTO-SAVE (debounced 500ms)
  ============================================================ */
  function scheduleAutoSave(row, nextWorking, nextRemarks) {
    if (isLocked) return;
    const model = row.model;
    if (!model) return;
    if (saveTimersRef.current[model]) clearTimeout(saveTimersRef.current[model]);
    setSavingMap(p => ({ ...p, [model]: "saving" }));
    saveTimersRef.current[model] = setTimeout(async () => {
      try {
        const res = await fetch(`${BASE}/api/cb-replenishment/save-working`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model,
            working_value: nextWorking ?? "",
            remarks: nextRemarks ?? "",
            snapshot: row,
          }),
        });
        const j = await res.json();
        setSavingMap(p => ({ ...p, [model]: j.status === "saved" ? "saved" : "error" }));
        if (j.status === "saved") logUsage("save", "cb-replenishment", { model });
        setTimeout(() => setSavingMap(p => { const n = { ...p }; delete n[model]; return n; }), 1500);
      } catch {
        setSavingMap(p => ({ ...p, [model]: "error" }));
      }
    }, 500);
  }

  async function resetAll() {
    if (!confirm("Reset all CB working values + remarks?")) return;
    try {
      await fetch(`${BASE}/api/cb-replenishment/reset`, { method: "POST" });
      setWorkingValues({});
      setRemarksValues({});
    } catch {}
  }

  /* ============================================================
     DERIVED
  ============================================================ */
  const brands = useMemo(
    () => ["All", ...[...new Set(rows.map(r => r.brand).filter(Boolean))].sort()],
    [rows]
  );

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = rows.filter(r => {
      if (brand !== "All" && r.brand !== brand) return false;
      if (q && !(
        (r.model || "").toLowerCase().includes(q) ||
        (r.asin  || "").toLowerCase().includes(q) ||
        (r.sku   || "").toLowerCase().includes(q)
      )) return false;
      if (view === "deficiency") return (r.deficiency || 0) > 0;
      if (view === "po_req")     return (r.po_requirement || 0) > 0;
      if (view === "no_open_po") return !r.open_po || r.open_po === 0;
      if (view === "edited") {
        return (workingValues[r.model] != null && workingValues[r.model] !== "") ||
               (remarksValues[r.model] != null && remarksValues[r.model] !== "");
      }
      return true;
    });
    // Relevance sort when searching: exact model/sku/asin match first,
    // then startsWith, then remaining includes-only matches. Keeps
    // AM-Mix10 at the top when the operator types "am-mix10", even if
    // less-relevant substring hits exist.
    if (!q) return filtered;
    const score = r => {
      const m = (r.model || "").toLowerCase();
      const s = (r.sku   || "").toLowerCase();
      const a = (r.asin  || "").toLowerCase();
      if (m === q || s === q || a === q) return 0;
      if (m.startsWith(q) || s.startsWith(q) || a.startsWith(q)) return 1;
      return 2;
    };
    return [...filtered].sort((x, y) => score(x) - score(y));
  }, [rows, search, view, brand, workingValues, remarksValues]);

  const views = useMemo(() => [
    { key: "all",        label: "All",            count: rows.length },
    { key: "deficiency", label: "Has Deficiency", count: rows.filter(r => (r.deficiency || 0) > 0).length, accent: "bg-red-100 text-red-700" },
    { key: "po_req",     label: "Has PO Req",     count: rows.filter(r => (r.po_requirement || 0) > 0).length },
    { key: "no_open_po", label: "No Open PO",     count: rows.filter(r => !r.open_po || r.open_po === 0).length },
    { key: "edited",     label: "Edited",         count: rows.filter(r => (workingValues[r.model] != null && workingValues[r.model] !== "") || (remarksValues[r.model] != null && remarksValues[r.model] !== "")).length },
  ], [rows, workingValues, remarksValues]);

  const kpis = useMemo(() => {
    const totalPoReq      = filteredRows.reduce((a, r) => a + (Number(r.po_requirement) || 0), 0);
    const totalDeficiency = filteredRows.reduce((a, r) => a + (Number(r.deficiency) || 0), 0);
    const critical        = filteredRows.filter(r => (r.deficiency || 0) > 0).length;
    return { totalPoReq: Math.round(totalPoReq), totalDeficiency: Math.round(totalDeficiency), critical };
  }, [filteredRows]);

  /* ============================================================
     COLUMNS
  ============================================================ */
  const columns = useMemo(() => [
    { id: "model",            accessorKey: "model",            header: "Model",          size: 150, meta: { sticky: 1, group: "id" } },
    { id: "asin",             accessorKey: "asin",             header: "ASIN",           size: 110, meta: { group: "id" } },
    { id: "sku",              accessorKey: "sku",              header: "SKU",            size: 110, meta: { group: "id" } },
    { id: "brand",            accessorKey: "brand",            header: "Brand",          size: 90,  meta: { group: "id" } },
    { id: "cb_3m_sales",      accessorKey: "cb_3m_sales",      header: "CB 3M",          size: 80,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "cambium_3m_sales", accessorKey: "cambium_3m_sales", header: "Cambium 3M",     size: 95,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "avg_weekly_sales", accessorKey: "avg_weekly_sales", header: "Avg/Wk",         size: 80,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "last_2_velocity",  accessorKey: "last_2_velocity",  header: "2wk Top",        size: 80,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "final_cb_qty",     accessorKey: "final_cb_qty",     header: "CB Inv",         size: 80,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "ampm_inventory",   accessorKey: "ampm_inventory",   header: "Mother WH",      size: 100, meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "china_in_transit", accessorKey: "china_in_transit", header: "China IT",       size: 90,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "open_po",          accessorKey: "open_po",          header: "Open PO",        size: 85,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "in_transit",       accessorKey: "in_transit",       header: "In-Transit",     size: 90,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "estimated_qty",    accessorKey: "estimated_qty",    header: "Estimated",      size: 90,  meta: { group: "plan", numeric: true, sortDescFirst: true } },
    { id: "deficiency",       accessorKey: "deficiency",       header: "Deficiency",     size: 95,  meta: { group: "plan", numeric: true, sortDescFirst: true } },
    { id: "po_requirement",   accessorKey: "po_requirement",   header: "PO Req",         size: 90,  meta: { group: "plan", numeric: true, sortDescFirst: true } },
    { id: "buffer_note",      accessorKey: "buffer_note",      header: "Buffer",         size: 160, meta: { group: "plan" } },
    { id: "asin_sort_details",accessorKey: "asin_sort_details",header: "ASIN Sort",      size: 95,  meta: { group: "plan" } },
    { id: "working_value",    accessorKey: "working_value",    header: "Working",        size: 100, meta: { group: "edit" } },
    { id: "remarks",          accessorKey: "remarks",          header: "Remarks",        size: 200, meta: { group: "edit" } },
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

  const selectedSet = useMemo(() => {
    const s = new Set();
    if (!selRange) return s;
    const r0 = Math.min(selRange.fromRow, selRange.toRow);
    const r1 = Math.max(selRange.fromRow, selRange.toRow);
    const c0 = Math.min(selRange.fromCol, selRange.toCol);
    const c1 = Math.max(selRange.fromCol, selRange.toCol);
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) s.add(`${r}-${c}`);
    return s;
  }, [selRange]);

  const selectionSummary = useMemo(() => {
    if (!selRange) return null;
    const r0 = Math.min(selRange.fromRow, selRange.toRow);
    const r1 = Math.max(selRange.fromRow, selRange.toRow);
    const c0 = Math.min(selRange.fromCol, selRange.toCol);
    const c1 = Math.max(selRange.fromCol, selRange.toCol);
    const sortedTable = table.getRowModel().rows;
    let count = 0, sum = 0;
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const col = columns[c];
        const orig = sortedTable[r]?.original;
        if (!col || !orig) continue;
        count++;
        if (col.meta?.numeric) sum += Number(orig[col.id]) || 0;
      }
    }
    return count ? { count, sum } : null;
  }, [selRange, table, columns]);

  useEffect(() => {
    function onCopy(e) {
      if (!selRange) return;
      e.preventDefault();
      const r0 = Math.min(selRange.fromRow, selRange.toRow);
      const r1 = Math.max(selRange.fromRow, selRange.toRow);
      const c0 = Math.min(selRange.fromCol, selRange.toCol);
      const c1 = Math.max(selRange.fromCol, selRange.toCol);
      const sortedTable = table.getRowModel().rows;
      const lines = [];
      for (let r = r0; r <= r1; r++) {
        const cells = [];
        for (let c = c0; c <= c1; c++) {
          const id = columns[c]?.id;
          const v  = sortedTable[r]?.original?.[id];
          cells.push(v == null ? "" : String(v));
        }
        lines.push(cells.join("\t"));
      }
      e.clipboardData.setData("text/plain", lines.join("\n"));
    }
    document.addEventListener("copy", onCopy);
    return () => document.removeEventListener("copy", onCopy);
  }, [selRange, columns, table]);

  /* ============================================================
     GROUPED HEADERS
  ============================================================ */
  const groupMeta = {
    id:    { label: "Identity",  tint: "" },
    sales: { label: "Sales",     tint: "bg-indigo-50 text-indigo-700" },
    inv:   { label: "Inventory", tint: "bg-slate-100" },
    plan:  { label: "Plan",      tint: "bg-amber-50 text-amber-800" },
    edit:  { label: "Operator",  tint: "" },
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
    const headers = order.map(id => columns.find(c => c.id === id).header);
    const lines = [headers.join(",")];
    table.getSortedRowModel().rows.forEach(({ original: r }) => {
      const cells = order.map(id => {
        let v = id === "working_value"
          ? (workingValues[r.model] ?? r.working_value ?? r.po_requirement ?? "")
          : id === "remarks"
            ? (remarksValues[r.model] ?? r.remarks ?? "")
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
    a.download = `cb_replenishment_${brand.toLowerCase()}_${view}.csv`;
    a.click();
    logUsage("export", "cb-replenishment", { rows: filteredRows.length });
  }

  /* ============================================================
     PALETTE PICK
  ============================================================ */
  function onPaletteSelect(item) {
    if (item.type === "sku") {
      setExpandedModel(item.payload.model);
      requestAnimationFrame(() => {
        const el = document.querySelector(`[data-row-model="${item.payload.model}"]`);
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
        <DataFreshnessBanner module="cb-replenishment" />

        {/* Header */}
        <div className="flex items-end justify-between mb-4">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-500 font-medium">Module</div>
            <h1 className="text-2xl font-semibold mt-0.5 tracking-tight">
              CB Replenishment <span className="text-slate-300 font-normal">·</span> <span className="text-slate-500 text-lg font-medium">{brand}</span>
            </h1>
            {cbSohSyncedDate && (
              <div className="mt-1 inline-flex items-center gap-1.5 text-[11px] text-slate-500">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
                CB SOH synced: <span className="font-semibold text-slate-700">{cbSohSyncedDate}</span>
                <span className="text-slate-400">(via SP-API Vendor Inventory)</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-2 px-3 py-2 rounded-md bg-white border border-slate-200 text-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-slate-700">
                {pastWeekMeta?.label || currentWeekMeta?.label || "Current week"}
                {isReadOnly && <span className="text-slate-400"> · view only</span>}
                {!isReadOnly && currentWeekMeta?.locked && <span className="text-amber-700"> · locked</span>}
              </span>
            </div>
            <SOPButton onClick={() => setSopOpen(true)} />
            <button onClick={exportCSV} className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            {!isReadOnly && (
              <button
                onClick={resetAll}
                className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Reset
              </button>
            )}
          </div>
        </div>

        {/* KPI */}
        <div className="grid grid-cols-5 gap-3 mb-5">
          <KPICard label="Total Models"     value={rows.length}      hint={`${brands.length - 1} brands`} />
          <KPICard label="In View"          value={filteredRows.length} hint={view !== "all" ? `${view}` : "all rows"} />
          <KPICard label="Total PO Req"     value={kpis.totalPoReq}     hint="units across view" />
          <KPICard label="Total Deficiency" value={kpis.totalDeficiency} hint="warehouse shortfall" tone="warn" />
          <KPICard label="Critical"         value={kpis.critical}        hint="deficiency > 0" tone="bad" />
        </div>

        {/* Saved views + brand */}
        <div className="mb-3 grid grid-cols-12 gap-3">
          <div className="col-span-9">
            <SavedViews views={views} active={view} onPick={setView} />
          </div>
          <div className="col-span-3">
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm px-3 py-2 flex items-center gap-2">
              <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold whitespace-nowrap">Brand</span>
              <select
                value={brand}
                onChange={e => setBrand(e.target.value)}
                className="flex-1 px-2 py-1 text-sm rounded-md border border-slate-200 bg-white"
              >
                {brands.map(b => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-3 mb-3">
          <div className="grid grid-cols-12 gap-3 items-end">
            <div className="col-span-4">
              <Label>Search</Label>
              <div className="relative">
                <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-300" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"
                  placeholder="Model / ASIN / SKU…"
                />
              </div>
            </div>

            <div className="col-span-3">
              <Label>Sales Window (Range)</Label>
              <div className="grid grid-cols-2 gap-1.5">
                <select
                  value={fromWeek ?? ""}
                  onChange={e => setFromWeek(Number(e.target.value))}
                  className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                  disabled={!availableWeeks.length}
                >
                  {availableWeeks.map(w => <option key={`f-${w}`} value={w}>From Wk {w}</option>)}
                </select>
                <select
                  value={toWeek ?? ""}
                  onChange={e => setToWeek(Number(e.target.value))}
                  className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                  disabled={!availableWeeks.length}
                >
                  {availableWeeks.map(w => <option key={`t-${w}`} value={w}>To Wk {w}</option>)}
                </select>
              </div>
            </div>

            <div className="col-span-1">
              <Label>Cover Wks</Label>
              <select value={coverWeeks} onChange={e => setCoverWeeks(Number(e.target.value))}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                {[2, 4, 6, 8, 10, 12].map(n => <option key={n}>{n}</option>)}
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

            <div className="col-span-2 flex items-center gap-2 justify-end">
              <div className="inline-flex rounded-md border border-slate-200 bg-white">
                {["comfy", "cozy", "compact"].map(d => (
                  <button key={d} onClick={() => setDensity(d)}
                    className={cn("px-2 py-1 text-xs font-medium",
                      density === d ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-50")}
                    title={d}>
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
                <tr className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                  {groupedHeaders.map((g, i) => (
                    <th key={i} colSpan={g.span}
                      className={cn("px-3 py-2 text-center border-b border-slate-200", g.tint, i > 0 && "border-l")}>
                      {g.label}
                    </th>
                  ))}
                </tr>
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
                            meta.group === "sales" && "bg-indigo-50/60",
                            meta.group === "plan"  && "bg-amber-50/40",
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
                {table.getRowModel().rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((trow, ri) => {
                  const r = trow.original;
                  const globalRowIdx = (page - 1) * PAGE_SIZE + ri;
                  const isExpanded = expandedModel === r.model;
                  const isCritical = (r.deficiency || 0) > 0;

                  return (
                    <React.Fragment key={r.model || globalRowIdx}>
                      <tr
                        data-row-model={r.model}
                        className={cn(
                          "hover:bg-slate-50/60 cursor-pointer",
                          isCritical && "bg-red-50/40",
                          isExpanded && "bg-indigo-50/30",
                        )}
                        onClick={() => setExpandedModel(isExpanded ? null : r.model)}
                      >
                        {trow.getVisibleCells().map((cell, ci) => {
                          const colId = cell.column.id;
                          const meta = cell.column.columnDef.meta || {};
                          const isSelected = selectedSet.has(`${globalRowIdx}-${ci}`);

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
                          } else if (colId === "asin" || colId === "sku") {
                            content = <span className="font-mono text-xs text-slate-500">{r[colId] || "—"}</span>;
                          } else if (colId === "brand") {
                            content = <span className="text-slate-600">{r.brand || "—"}</span>;
                          } else if (colId === "avg_weekly_sales") {
                            const bumped = r.velocity_basis === "2wk";
                            content = (
                              <span className="tabular-nums font-semibold">
                                {Math.round(r.avg_weekly_sales || 0)}
                                {bumped && (
                                  <span className="inline-flex ml-1 px-1 py-0.5 text-[9px] font-bold rounded bg-indigo-100 text-indigo-700" title="Last-2-week top exceeds window avg — driving Estimated Qty">
                                    2wk
                                  </span>
                                )}
                              </span>
                            );
                          } else if (colId === "last_2_velocity") {
                            const v = Math.round(r.last_2_velocity || 0);
                            content = <span className="tabular-nums text-indigo-700">{v > 0 ? v : "—"}</span>;
                          } else if (colId === "estimated_qty") {
                            content = <span className="tabular-nums">{Math.round(r.estimated_qty || 0)}</span>;
                          } else if (colId === "deficiency") {
                            const v = r.deficiency || 0;
                            content = (
                              <span className={cn("tabular-nums", v > 0 && "text-red-700 font-semibold")}>
                                {v > 0 ? Math.round(v) : "—"}
                              </span>
                            );
                          } else if (colId === "po_requirement") {
                            content = <span className="font-bold tabular-nums text-slate-900">{Math.round(r.po_requirement || 0)}</span>;
                          } else if (colId === "asin_sort_details") {
                            const s = String(r.asin_sort_details || "").trim();
                            const tone = s === "IXD"
                              ? "bg-blue-50 text-blue-700 border-blue-200"
                              : s.toLowerCase().includes("non")
                                ? "bg-slate-50 text-slate-600 border-slate-200"
                                : "bg-slate-50 text-slate-500 border-slate-200";
                            content = s
                              ? <span className={cn("inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium border rounded", tone)}>{s}</span>
                              : <span className="text-slate-300 text-xs">—</span>;
                          } else if (colId === "working_value") {
                            const status = savingMap[r.model];
                            content = (
                              <div className="flex items-center gap-1">
                                <input
                                  type="text"
                                  value={workingValues[r.model] ?? String(r.po_requirement ?? "")}
                                  onClick={e => e.stopPropagation()}
                                  disabled={isLocked}
                                  onChange={e => {
                                    const v = e.target.value;
                                    setWorkingValues(p => ({ ...p, [r.model]: v }));
                                    scheduleAutoSave(r, v, remarksValues[r.model] ?? r.remarks ?? "");
                                  }}
                                  className="w-16 text-right px-1.5 py-1 border border-slate-200 rounded text-xs font-mono disabled:bg-slate-50"
                                />
                                {status && (
                                  <span className={cn("text-[9px]",
                                    status === "saved" ? "text-emerald-600" :
                                    status === "error" ? "text-red-600" : "text-slate-400")}>
                                    {status === "saving" ? "…" : status === "saved" ? "✓" : "✕"}
                                  </span>
                                )}
                              </div>
                            );
                          } else if (colId === "remarks") {
                            content = (
                              <input
                                type="text"
                                value={remarksValues[r.model] ?? r.remarks ?? ""}
                                onClick={e => e.stopPropagation()}
                                disabled={isLocked}
                                onChange={e => {
                                  const v = e.target.value;
                                  setRemarksValues(p => ({ ...p, [r.model]: v }));
                                  scheduleAutoSave(
                                    r,
                                    workingValues[r.model] ?? String(r.po_requirement ?? ""),
                                    v,
                                  );
                                }}
                                className="w-44 px-1.5 py-1 border border-slate-200 rounded text-xs disabled:bg-slate-50"
                                placeholder="—"
                              />
                            );
                          } else {
                            content = (
                              <span className="tabular-nums">
                                {r[colId] ?? (meta.numeric ? 0 : "—")}
                              </span>
                            );
                          }

                          return (
                            <td
                              key={cell.id}
                              onMouseDown={meta.numeric ? (e) => onCellMouseDown(globalRowIdx, ci, e) : undefined}
                              onMouseEnter={() => onCellMouseEnter(globalRowIdx, ci)}
                              className={cn(
                                meta.numeric ? "text-right" : "text-left",
                                meta.sticky === 1 && "sticky left-0 bg-white z-[1] shadow-[1px_0_0_#e2e8f0]",
                                isExpanded && meta.sticky && "!bg-indigo-50",
                                isSelected && "bg-indigo-100 outline outline-1 outline-indigo-500 outline-offset-[-1px]",
                              )}
                            >
                              {content}
                            </td>
                          );
                        })}
                      </tr>

                      {isExpanded && (
                        <CBDetailRow row={r} colSpan={columns.length} />
                      )}
                    </React.Fragment>
                  );
                })}

                {filteredRows.length === 0 && !loading && (
                  <tr>
                    <td colSpan={columns.length} className="text-center py-10 text-slate-400 text-sm">
                      No models match the current view + search.
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
                  <span className="font-semibold text-slate-900">{selectionSummary.count} cells</span> · Sum <span className="font-mono font-semibold text-slate-900">{selectionSummary.sum.toLocaleString()}</span>
                  <span className="text-indigo-600 ml-2">⌘C to copy</span>
                </>
              ) : (
                <>Drag numeric cells to range-select · <kbd className="px-1 py-0.5 rounded bg-slate-200 text-[10px] font-mono">⌘K</kbd> command palette</>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span>
                Showing <span className="font-semibold text-slate-900">
                  {Math.min((page - 1) * PAGE_SIZE + 1, filteredRows.length)}–{Math.min(page * PAGE_SIZE, filteredRows.length)}
                </span> of {filteredRows.length}
              </span>
              {filteredRows.length > PAGE_SIZE && (
                <div className="flex items-center gap-1">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                    className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40">‹</button>
                  <span className="px-2 font-semibold text-slate-900 tabular-nums">
                    Page {page} / {Math.ceil(filteredRows.length / PAGE_SIZE)}
                  </span>
                  <button onClick={() => setPage(p => Math.min(Math.ceil(filteredRows.length / PAGE_SIZE), p + 1))}
                    disabled={page >= Math.ceil(filteredRows.length / PAGE_SIZE)}
                    className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40">›</button>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-5 text-xs text-slate-500 px-1">
          <Legend swatch="bg-red-100"    label="Critical (deficiency > 0)" />
          <Legend swatch="bg-indigo-100" label="Range-selected" />
          <span className="ml-auto text-slate-400">Working/Remarks auto-save 500 ms after typing stops</span>
        </div>
      </div>

      <SOPModal open={sopOpen} onClose={() => setSopOpen(false)} title="CB Replenishment">
        <CBReplenishmentSOPContent />
      </SOPModal>

      <CommandPalette
        rows={rows.map(r => ({ ...r, sku: r.model, asin: r.asin, model: r.model }))}
        views={views.map(v => ({ key: v.key, label: v.label, hint: `${v.count} rows` }))}
        onPick={onPaletteSelect}
      />
    </div>
  );
}

/* ============================================================
   DETAIL ROW
============================================================ */

function CBDetailRow({ row, colSpan }) {
  const cbSales      = Number(row.cb_3m_sales || 0);
  const cambiumSales = Number(row.cambium_3m_sales || 0);
  const totalSales   = cbSales + cambiumSales;
  const cbPct = totalSales > 0 ? Math.round((cbSales / totalSales) * 100) : 0;
  const camPct = 100 - cbPct;

  return (
    <tr className="bg-indigo-50/20">
      <td colSpan={colSpan} className="!p-0">
        <div className="px-6 py-5 bg-gradient-to-b from-indigo-50/40 to-white border-l-4 border-indigo-500 grid grid-cols-12 gap-5">
          <div className="col-span-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Sales mix (3M)</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2.5 text-xs">
              <div>
                <div className="flex justify-between mb-1"><span>CB</span><span className="font-mono tabular-nums font-semibold">{Math.round(cbSales)} ({cbPct}%)</span></div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className="h-full bg-indigo-500" style={{ width: `${cbPct}%` }} /></div>
              </div>
              <div>
                <div className="flex justify-between mb-1"><span>Cambium</span><span className="font-mono tabular-nums font-semibold">{Math.round(cambiumSales)} ({camPct}%)</span></div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden"><div className="h-full bg-emerald-500" style={{ width: `${camPct}%` }} /></div>
              </div>
              <div className="pt-1 border-t border-slate-100 flex justify-between">
                <span className="text-slate-500">Avg / wk</span>
                <span className="font-mono tabular-nums font-semibold">{Math.round(row.avg_weekly_sales || 0)}</span>
              </div>
            </div>
          </div>

          <div className="col-span-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Pipeline</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <KV label="CB Inv"          val={Math.round(row.final_cb_qty || 0)} />
              <KV label="Mother WH (AMPM)" val={Math.round(row.ampm_inventory || 0)} accent />
              <KV label="China In-Transit" val={Math.round(row.china_in_transit || 0)} />
              <KV label="Open PO"          val={Math.round(row.open_po || 0)} />
              <KV label="In-Transit"       val={Math.round(row.in_transit || 0)} />
            </div>
          </div>

          <div className="col-span-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Plan</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <KV label="Estimated"   val={Math.round(row.estimated_qty || 0)} />
              <KV label="Deficiency"  val={Math.round(row.deficiency || 0)} danger={(row.deficiency || 0) > 0} />
              <KV label="PO Required" val={Math.round(row.po_requirement || 0)} accent />
              {row.asin_sort_details && (
                <div className="pt-2 border-t border-slate-100">
                  <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-1">ASIN details</div>
                  <div className="font-mono text-xs">{row.asin_sort_details}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

function KV({ label, val, accent, danger }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={cn("font-mono tabular-nums font-semibold",
        danger ? "text-red-700" : accent ? "text-indigo-700" : "text-slate-900")}>
        {val ?? 0}
      </span>
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

function Legend({ swatch, label }) {
  return (
    <div className="flex items-center gap-2">
      <span className={cn("w-3 h-3 rounded", swatch)} />
      <span>{label}</span>
    </div>
  );
}
