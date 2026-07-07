import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Search, Download, ChevronDown, ChevronRight, Settings2, Star,
} from "lucide-react";

import { CommandPalette } from "../components/CommandPalette";
import { SavedViews } from "../components/SavedViews";
import { SOPModal, SOPButton } from "../components/SOPModal";
import { ChinaReorderSOPContent } from "../components/SOPContents";
import DataFreshnessBanner from "../components/DataFreshnessBanner";
import { cn } from "../lib/cn";

/* ============================================================
   REORDER INTELLIGENCE V2 — TanStack + v2 pattern
   Endpoint reused: GET /china-reorder/?brand=…&months=…&from_week=…&to_week=…
   Read-only.
============================================================ */

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

// Viomi excluded — it shares Nexlev's manufactured SKUs (rebrand for
// separate Amazon listings), so reordering is done at the Nexlev level.
const BRAND_OPTIONS = ["Nexlev", "Audio Array", "White Mulberry", "Tonor"];

// Status derived from weeks_cover — thresholds match V1 (12 / 16).
function reorderStatus(row) {
  const w = Number(row?.weeks_cover) || 0;
  if (w < 12)               return "CRITICAL";
  if (w >= 12 && w <= 16)   return "MODERATE";
  return "NO REORDER";
}

export default function ChinaReorderV2() {
  const [selectedBrands, setSelectedBrands] = useState(["Nexlev"]);
  const [selectedMonths, setSelectedMonths] = useState(3);
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek,   setToWeek]   = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);
  const [selectedL0, setSelectedL0] = useState("");
  const [selectedL1, setSelectedL1] = useState("");

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [view, setView] = useState("all");
  const [sorting, setSorting] = useState([]);
  const [expandedModel, setExpandedModel] = useState(null);
  const [density, setDensity] = useState("cozy");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 100;

  /* Range-select */
  const [selRange, setSelRange] = useState(null);
  const draggingRef = useRef(null);

  /* SOP modal */
  const [sopOpen, setSopOpen] = useState(false);

  /* ============================================================
     LOAD
  ============================================================ */
  useEffect(() => {
    if (selectedBrands.length === 0) { setRows([]); return; }
    setLoading(true);
    setExpandedModel(null);
    const params = new URLSearchParams({ months: selectedMonths });
    selectedBrands.forEach(b => params.append("brand", b));
    if (fromWeek) params.append("from_week", fromWeek);
    if (toWeek)   params.append("to_week",   toWeek);

    fetch(`${BASE}/china-reorder/?${params}`)
      .then(r => r.json())
      .then(res => {
        setRows(Array.isArray(res.data) ? res.data : []);
        if (res.available_weeks?.length) {
          const weeks = res.available_weeks;
          setAvailableWeeks(weeks);
          if (!fromWeek) setFromWeek(weeks[0]);
          if (!toWeek)   setToWeek(weeks[weeks.length - 1]);
        }
      })
      .finally(() => setLoading(false));
  }, [selectedBrands, selectedMonths, fromWeek, toWeek]);

  useEffect(() => { setPage(1); }, [search, view, selectedL0, selectedL1, selectedBrands, fromWeek, toWeek]);

  /* ============================================================
     DERIVED
  ============================================================ */
  const l0Options = useMemo(
    () => [...new Set(rows.map(r => r.category_l0).filter(Boolean))].sort(),
    [rows]
  );
  const l1Options = useMemo(() => {
    if (!selectedL0) return [];
    return [...new Set(
      rows.filter(r => r.category_l0 === selectedL0).map(r => r.category_l1).filter(Boolean)
    )].sort();
  }, [rows, selectedL0]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter(r => {
      if (selectedL0 && r.category_l0 !== selectedL0) return false;
      if (selectedL1 && r.category_l1 !== selectedL1) return false;
      if (q && !(
        (r.model || "").toLowerCase().includes(q) ||
        (r.sku   || "").toLowerCase().includes(q) ||
        (r.asin  || "").toLowerCase().includes(q)
      )) return false;
      if (view === "reorder")       return (r.suggested_reorder || 0) > 0;
      if (view === "critical")      return (r.weeks_cover != null) && r.weeks_cover < 12;
      if (view === "moderate")      return (r.weeks_cover != null) && r.weeks_cover >= 12 && r.weeks_cover <= 16;
      if (view === "high_returns")  return (r.returns_pct || 0) > 10;
      if (view === "neg_margin")    return (r.net_margin_pct || 0) < 0;
      if (view === "top_rated")     return (r.avg_rating || 0) >= 4;
      return true;
    });
  }, [rows, search, view, selectedL0, selectedL1]);

  const views = useMemo(() => [
    { key: "all",          label: "All",              count: rows.length },
    { key: "reorder",      label: "Has Reorder",      count: rows.filter(r => (r.suggested_reorder || 0) > 0).length },
    { key: "critical",     label: "Critical (<12wk)", count: rows.filter(r => (r.weeks_cover != null) && r.weeks_cover < 12).length, accent: "bg-red-100 text-red-700" },
    { key: "moderate",     label: "Moderate (12-16wk)", count: rows.filter(r => (r.weeks_cover != null) && r.weeks_cover >= 12 && r.weeks_cover <= 16).length },
    { key: "high_returns", label: "Returns > 10%",    count: rows.filter(r => (r.returns_pct || 0) > 10).length },
    { key: "neg_margin",   label: "Neg. Margin",      count: rows.filter(r => (r.net_margin_pct || 0) < 0).length },
    { key: "top_rated",    label: "4★+",              count: rows.filter(r => (r.avg_rating || 0) >= 4).length },
  ], [rows]);

  const kpis = useMemo(() => {
    const totalReorder = filteredRows.reduce((a, r) => a + (Number(r.suggested_reorder) || 0), 0);
    const totalCover   = filteredRows.reduce((a, r) => a + (Number(r.weeks_cover) || 0), 0);
    const avgCover     = filteredRows.length ? (totalCover / filteredRows.length) : 0;
    const critical     = filteredRows.filter(r => (r.weeks_cover != null) && r.weeks_cover < 12).length;
    return { totalReorder: Math.round(totalReorder), avgCover: avgCover.toFixed(1), critical };
  }, [filteredRows]);

  /* ============================================================
     COLUMNS
  ============================================================ */
  const columns = useMemo(() => [
    { id: "model",             accessorKey: "model",             header: "Model",      size: 150, meta: { sticky: 1, group: "id" } },
    { id: "sku",               accessorKey: "sku",               header: "SKU",        size: 110, meta: { group: "id" } },
    { id: "asin",              accessorKey: "asin",              header: "ASIN",       size: 110, meta: { group: "id" } },
    { id: "brand",             accessorKey: "brand",             header: "Brand",      size: 100, meta: { group: "id" } },
    { id: "category_l0",       accessorKey: "category_l0",       header: "L0",         size: 110, meta: { group: "id" } },
    { id: "last_12w_sales",    accessorKey: "last_12w_sales",    header: "12W Sales",  size: 95,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "avg_weekly_sales",  accessorKey: "avg_weekly_sales",  header: "Avg/Wk",     size: 80,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "current_inventory", accessorKey: "current_inventory", header: "Inventory",       size: 95,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "open_order_qty",    accessorKey: "open_order_qty",    header: "PO Yet to Pickup",size: 110, meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "pipeline_qty",      accessorKey: "pipeline_qty",      header: "PO Picked Up",    size: 105, meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "weeks_cover",       accessorKey: "weeks_cover",       header: "Cover (wk)", size: 90,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "suggested_reorder", accessorKey: "suggested_reorder", header: "Reorder",    size: 95,  meta: { group: "plan", numeric: true, sortDescFirst: true } },
    { id: "status",            accessorFn: r => reorderStatus(r), header: "Status",    size: 110, meta: { group: "plan" } },
    { id: "avg_rating",        accessorKey: "avg_rating",        header: "Rating",     size: 80,  meta: { group: "quality", numeric: true, sortDescFirst: true } },
    { id: "rating_count",      accessorKey: "rating_count",      header: "Reviews",    size: 85,  meta: { group: "quality", numeric: true, sortDescFirst: true } },
    { id: "returns_pct",       accessorKey: "returns_pct",       header: "Returns %",  size: 90,  meta: { group: "quality", numeric: true, sortDescFirst: true } },
    { id: "net_margin_inr",    accessorKey: "net_margin_inr",    header: "Margin (₹)", size: 100, meta: { group: "money", numeric: true, sortDescFirst: true } },
    { id: "net_margin_pct",    accessorKey: "net_margin_pct",    header: "Margin %",   size: 90,  meta: { group: "money", numeric: true, sortDescFirst: true } },
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
    id:      { label: "Identity",  tint: "" },
    sales:   { label: "Sales",     tint: "bg-indigo-50 text-indigo-700" },
    inv:     { label: "Inventory", tint: "bg-slate-100" },
    plan:    { label: "Plan",      tint: "bg-amber-50 text-amber-800" },
    quality: { label: "Quality",   tint: "bg-emerald-50 text-emerald-700" },
    money:   { label: "Margin",    tint: "" },
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
     EXPORT
  ============================================================ */
  function exportCSV() {
    const order = columns.map(c => c.id);
    const headers = order.map(id => columns.find(c => c.id === id).header);
    const lines = [headers.join(",")];
    table.getSortedRowModel().rows.forEach(({ original: r }) => {
      const cells = order.map(id => {
        let v = r[id];
        if (v == null) v = "";
        const s = String(v).replace(/"/g, '""');
        return /[",\n]/.test(s) ? `"${s}"` : s;
      });
      lines.push(cells.join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `reorder_${selectedBrands.join("_").toLowerCase()}_${view}.csv`;
    a.click();
  }

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

  function toggleBrand(b) {
    setSelectedBrands(prev =>
      prev.includes(b) ? prev.filter(x => x !== b) : [...prev, b]
    );
  }

  /* ============================================================
     RENDER
  ============================================================ */
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="w-full px-6 pt-5 pb-10">
        <DataFreshnessBanner module="china-reorder" />

        <div className="flex items-end justify-between mb-4">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-500 font-medium">Module</div>
            <h1 className="text-2xl font-semibold mt-0.5 tracking-tight">
              Reorder Intelligence <span className="text-slate-300 font-normal">·</span>
              <span className="text-slate-500 text-lg font-medium ml-1">
                {selectedBrands.join(" + ") || "no brand"}
              </span>
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <SOPButton onClick={() => setSopOpen(true)} />
            <button onClick={exportCSV} className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
          </div>
        </div>

        <div className="grid grid-cols-5 gap-3 mb-5">
          <KPICard label="Total Models"     value={rows.length}        hint={`${selectedBrands.length} brand${selectedBrands.length === 1 ? "" : "s"} loaded`} />
          <KPICard label="In View"          value={filteredRows.length} hint={view !== "all" ? view : "all rows"} />
          <KPICard label="Total Reorder"    value={kpis.totalReorder}   hint="suggested units"  tone="brand" />
          <KPICard label="Avg Cover"        value={`${kpis.avgCover} wks`} hint="across view" />
          <KPICard label="Critical Cover"   value={kpis.critical}       hint="< 12 weeks"  tone="bad" />
        </div>

        <div className="mb-3">
          <SavedViews views={views} active={view} onPick={setView} />
        </div>

        {/* Brand chips + filters */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-3 mb-3">
          <div className="grid grid-cols-12 gap-3 items-end">
            <div className="col-span-4">
              <Label>Brands</Label>
              <div className="flex flex-wrap gap-1.5">
                {BRAND_OPTIONS.map(b => {
                  const on = selectedBrands.includes(b);
                  return (
                    <button
                      key={b}
                      onClick={() => toggleBrand(b)}
                      className={cn(
                        "px-2.5 py-1 text-xs font-medium rounded-md border transition-colors",
                        on
                          ? "bg-indigo-600 text-white border-indigo-600"
                          : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                      )}
                    >
                      {b}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="col-span-3">
              <Label>Search</Label>
              <div className="relative">
                <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-300" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"
                  placeholder="Model / SKU / ASIN…"
                />
              </div>
            </div>

            <div className="col-span-1">
              <Label>Months</Label>
              <select value={selectedMonths} onChange={e => setSelectedMonths(Number(e.target.value))}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                {[1, 2, 3, 6, 12].map(n => <option key={n}>{n}</option>)}
              </select>
            </div>

            <div className="col-span-2">
              <Label>Sales Window</Label>
              <div className="grid grid-cols-2 gap-1.5">
                <select value={fromWeek ?? ""} onChange={e => setFromWeek(Number(e.target.value))}
                  className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                  disabled={!availableWeeks.length}>
                  {availableWeeks.map(w => <option key={`f-${w}`} value={w}>From {w}</option>)}
                </select>
                <select value={toWeek ?? ""} onChange={e => setToWeek(Number(e.target.value))}
                  className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                  disabled={!availableWeeks.length}>
                  {availableWeeks.map(w => <option key={`t-${w}`} value={w}>To {w}</option>)}
                </select>
              </div>
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

          {/* Category drilldown row */}
          <div className="grid grid-cols-12 gap-3 mt-3 pt-3 border-t border-slate-100">
            <div className="col-span-3">
              <Label>Category (L0)</Label>
              <select value={selectedL0} onChange={e => { setSelectedL0(e.target.value); setSelectedL1(""); }}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                <option value="">All L0</option>
                {l0Options.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="col-span-3">
              <Label>Category (L1)</Label>
              <select value={selectedL1} onChange={e => setSelectedL1(e.target.value)}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                disabled={!selectedL0}>
                <option value="">All L1</option>
                {l1Options.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
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
                            meta.group === "quality" && "bg-emerald-50/60",
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
                  const cover = r.weeks_cover ?? null;
                  const isCritical = cover != null && cover < 4;

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
                          } else if (colId === "sku" || colId === "asin") {
                            content = <span className="font-mono text-xs text-slate-500">{r[colId] || "—"}</span>;
                          } else if (colId === "brand") {
                            content = <span className="text-slate-600">{r.brand || "—"}</span>;
                          } else if (colId === "category_l0") {
                            content = <span className="text-slate-600 text-xs">{r.category_l0 || "—"}</span>;
                          } else if (colId === "avg_weekly_sales") {
                            content = <span className="tabular-nums font-semibold">{(r.avg_weekly_sales || 0).toFixed(1)}</span>;
                          } else if (colId === "weeks_cover") {
                            const w = r.weeks_cover ?? null;
                            // V1 thresholds: <12 CRITICAL, 12-16 MODERATE, >16 NO REORDER
                            const tone =
                              w == null         ? "text-slate-300" :
                              w < 12            ? "text-red-700 font-semibold" :
                              w <= 16           ? "text-amber-700" :
                                                  "text-emerald-700";
                            content = <span className={cn("tabular-nums", tone)}>{w == null ? "—" : Number(w).toFixed(1)}</span>;
                          } else if (colId === "status") {
                            const s = reorderStatus(r);
                            const tone =
                              s === "CRITICAL"   ? "bg-red-100 text-red-700" :
                              s === "MODERATE"   ? "bg-amber-100 text-amber-700" :
                                                   "bg-emerald-100 text-emerald-700";
                            content = <span className={cn("inline-flex items-center px-1.5 py-0.5 text-[10px] font-bold rounded", tone)}>{s}</span>;
                          } else if (
                            colId === "last_12w_sales" ||
                            colId === "current_inventory" ||
                            colId === "open_order_qty" ||
                            colId === "pipeline_qty" ||
                            colId === "rating_count"
                          ) {
                            const v = Number(r[colId] || 0);
                            content = <span className="tabular-nums">{Math.round(v).toLocaleString()}</span>;
                          } else if (colId === "suggested_reorder") {
                            content = <span className="font-bold tabular-nums text-indigo-700">{Math.round(r.suggested_reorder || 0)}</span>;
                          } else if (colId === "avg_rating") {
                            const v = Number(r.avg_rating || 0);
                            content = v > 0
                              ? <span className="inline-flex items-center gap-0.5 tabular-nums"><Star className="w-3 h-3 text-amber-500 fill-amber-500" />{v.toFixed(1)}</span>
                              : <span className="text-slate-300">—</span>;
                          } else if (colId === "rating_count") {
                            const v = Number(r.rating_count || 0);
                            content = v > 0 ? <span className="tabular-nums text-slate-600">{v.toLocaleString()}</span> : <span className="text-slate-300">—</span>;
                          } else if (colId === "returns_pct") {
                            const v = Number(r.returns_pct || 0);
                            const tone = v >= 20 ? "text-red-700 font-semibold" : v >= 10 ? "text-amber-700" : "text-slate-700";
                            content = v > 0 ? <span className={cn("tabular-nums", tone)}>{v.toFixed(1)}%</span> : <span className="text-slate-300">—</span>;
                          } else if (colId === "net_margin_inr") {
                            const v = Number(r.net_margin_inr || 0);
                            const tone = v < 0 ? "text-red-700 font-semibold" : "text-slate-800";
                            content = v ? <span className={cn("tabular-nums", tone)}>₹{v.toLocaleString()}</span> : <span className="text-slate-300">—</span>;
                          } else if (colId === "net_margin_pct") {
                            const v = Number(r.net_margin_pct || 0);
                            const tone = v < 0 ? "text-red-700 font-semibold" : "text-slate-700";
                            content = v ? <span className={cn("tabular-nums", tone)}>{v.toFixed(1)}%</span> : <span className="text-slate-300">—</span>;
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
                        <ReorderDetailRow row={r} colSpan={columns.length} />
                      )}
                    </React.Fragment>
                  );
                })}

                {filteredRows.length === 0 && !loading && (
                  <tr>
                    <td colSpan={columns.length} className="text-center py-10 text-slate-400 text-sm">
                      No items match the current view + search.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

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
          <Legend swatch="bg-red-100"    label="Critical (< 12 wks cover)" />
          <Legend swatch="bg-amber-100"  label="Moderate (12–16 wks)" />
          <Legend swatch="bg-emerald-100" label="No Reorder (> 16 wks)" />
          <Legend swatch="bg-indigo-100" label="Range-selected" />
        </div>
      </div>

      <SOPModal open={sopOpen} onClose={() => setSopOpen(false)} title="Reorder Intelligence">
        <ChinaReorderSOPContent />
      </SOPModal>

      <CommandPalette
        rows={rows.map(r => ({ ...r, sku: r.sku || r.model, asin: r.asin || "", model: r.model }))}
        views={views.map(v => ({ key: v.key, label: v.label, hint: `${v.count} rows` }))}
        onPick={onPaletteSelect}
      />
    </div>
  );
}

/* ============================================================
   DETAIL ROW
============================================================ */

function ReorderDetailRow({ row, colSpan }) {
  const inv  = Number(row.current_inventory || 0);
  const oo   = Number(row.open_order_qty || 0);
  const pipe = Number(row.pipeline_qty || 0);
  const total = inv + oo + pipe;
  const pct = (v) => total > 0 ? Math.round((v / total) * 100) : 0;

  return (
    <tr className="bg-indigo-50/20">
      <td colSpan={colSpan} className="!p-0">
        <div className="px-6 py-5 bg-gradient-to-b from-indigo-50/40 to-white border-l-4 border-indigo-500 grid grid-cols-12 gap-5">
          <div className="col-span-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Stock pipeline</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2.5 text-xs">
              <Bar label="Current Inventory" val={inv}  pct={pct(inv)}  color="bg-indigo-500" />
              <Bar label="Open Order"        val={oo}   pct={pct(oo)}   color="bg-emerald-500" />
              <Bar label="Pipeline"          val={pipe} pct={pct(pipe)} color="bg-violet-500" />
              <div className="pt-1 border-t border-slate-100 flex justify-between">
                <span className="text-slate-500 font-semibold">Total available</span>
                <span className="font-mono tabular-nums font-bold text-slate-900">{total}</span>
              </div>
            </div>
          </div>

          <div className="col-span-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Demand & cover</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <KV label="12-wk sales"      val={Math.round(row.last_12w_sales || 0)} />
              <KV label="Avg / week"       val={(row.avg_weekly_sales || 0).toFixed(1)} accent />
              <KV label="Weeks of cover"   val={row.weeks_cover != null ? `${Number(row.weeks_cover).toFixed(1)} wks` : "—"} />
              <KV label="Suggested reorder" val={Math.round(row.suggested_reorder || 0)} accent />
              <div className="pt-2 border-t border-slate-100">
                <div className="text-slate-500 text-[10px] uppercase tracking-wider mb-1">Category</div>
                <div className="text-xs">{row.category_l0 || "—"} · <span className="text-slate-500">{row.category_l1 || "—"}</span></div>
              </div>
            </div>
          </div>

          <div className="col-span-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Quality & margin</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <KV label="Avg rating"       val={row.avg_rating ? Number(row.avg_rating).toFixed(1) : "—"} />
              <KV label="# reviews"        val={row.rating_count ? Number(row.rating_count).toLocaleString() : "—"} />
              <KV label="Returns %"        val={row.returns_pct ? `${Number(row.returns_pct).toFixed(1)}%` : "—"} danger={(row.returns_pct || 0) >= 20} />
              <KV label="Net margin (₹)"   val={row.net_margin_inr ? `₹${Number(row.net_margin_inr).toLocaleString()}` : "—"} danger={(row.net_margin_inr || 0) < 0} />
              <KV label="Net margin %"     val={row.net_margin_pct ? `${Number(row.net_margin_pct).toFixed(2)}%` : "—"} danger={(row.net_margin_pct || 0) < 0} />
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

function Bar({ label, val, pct, color }) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span>{label}</span>
        <span className="font-mono tabular-nums font-semibold">{val} ({pct}%)</span>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={cn("h-full", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
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
