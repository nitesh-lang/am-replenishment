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
import { proposePlan, saveDraft } from "../api/plans";
import { useAuth } from "../auth/AuthContext";
import { logUsage } from "../auth/usage";
import { Sparkline, classifyTrend } from "../components/Sparkline";
import { DetailRow } from "../components/DetailRow";
import { CommandPalette } from "../components/CommandPalette";
import { SavedViews } from "../components/SavedViews";
import { SOPModal, SOPButton } from "../components/SOPModal";
import { ReplenishmentSOPContent } from "../components/SOPContents";
import DataFreshnessBanner from "../components/DataFreshnessBanner";
import { cn } from "../lib/cn";

/* ============================================================
   REPLENISHMENT V2 — TanStack + shadcn-style
   Preserves existing logic:
     - getReplenishment / getKPIs
     - saved-weeks + saved-week-data flows
     - Working Value persistence
     - Master Carton edit
============================================================ */

const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";

export default function ReplenishmentV2() {
  const { user } = useAuth();
  const canPropose = (user?.allowedModules || []).includes("plans-editor") || user?.role === "admin";
  const [proposing, setProposing] = useState(false);
  const [proposeMsg, setProposeMsg] = useState("");

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
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [selectedStatuses, setSelectedStatuses]     = useState([]);

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

  /* ─────────── SOP modal ─────────── */
  const [sopOpen, setSopOpen] = useState(false);

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

  const listingStatuses = useMemo(
    () => [...new Set(rows.map(r => r.listing_status).filter(Boolean))].sort(),
    [rows]
  );

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = rows.filter(r => {
      if (q && !(
        (r.model || "").toLowerCase().includes(q) ||
        (r.sku   || "").toLowerCase().includes(q) ||
        (r.asin  || "").toLowerCase().includes(q)
      )) return false;
      if (selectedCategories.length > 0 && !selectedCategories.includes(r.category)) return false;
      if (selectedStatuses.length   > 0 && !selectedStatuses.includes(r.listing_status)) return false;
      if (view === "critical")  return r.is_risky;
      if (view === "bumped")    return r.velocity_basis === "2wk";
      if (view === "shortfall") return (r.warehouse_shortfall || 0) > 0;
      if (view === "overstock") return r.is_overstock;
      if (view === "hazmat") {
        const h = (r.hazmat_type || "").toLowerCase();
        return h.includes("hazmat") && !h.includes("non");
      }
      return true;
    });
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
  }, [rows, search, view, selectedCategories, selectedStatuses]);

  const views = useMemo(() => [
    { key: "all",       label: "All",            count: rows.length },
    { key: "critical",  label: "Critical",       count: rows.filter(r => r.is_risky).length, accent: "bg-red-100 text-red-700" },
    { key: "bumped",    label: "2wk Bumped",     count: rows.filter(r => r.velocity_basis === "2wk").length },
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
    { id: "model",            accessorKey: "model",            header: "Model",     size: 130, meta: { sticky: 1, group: "id" } },
    { id: "sku",              accessorKey: "sku",              header: "SKU",       size: 95,  meta: { sticky: 2, group: "id" } },
    { id: "asin",             accessorKey: "asin",             header: "ASIN",      size: 100, meta: { group: "list" } },
    { id: "trend",            accessorFn: r => classifyTrend(r.weekly_sales || []), header: "Trend", size: 110, meta: { group: "vel" } },
    { id: "sales_velocity",   accessorKey: "sales_velocity",   header: "Avg/Wk",    size: 75,  meta: { group: "vel", numeric: true, sortDescFirst: true } },
    { id: "window_velocity",  accessorKey: "window_velocity",  header: "Sel Wk",    size: 70,  meta: { group: "vel", numeric: true, sortDescFirst: true } },
    { id: "last_2_velocity",  accessorKey: "last_2_velocity",  header: "2wk",       size: 60,  meta: { group: "vel", numeric: true, sortDescFirst: true } },
    { id: "velocity_basis",   accessorKey: "velocity_basis",   header: "Basis",     size: 70,  meta: { group: "vel" } },
    { id: "total_units_sold", accessorFn: r => (r.velocity_basis === "2wk" ? (r.units_last_2w || 0) : (r.total_units_sold || 0)), header: "Total sold qty", size: 110, meta: { group: "vel", numeric: true, sortDescFirst: true } },
    { id: "inbound_inventory",accessorKey: "inbound_inventory",header: "Inbound",   size: 75,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "real_am_inv_available", accessorKey: "real_am_inv_available", header: "Real AM Inv", size: 95, meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "ampm_inventory",   accessorKey: "ampm_inventory",   header: "Mother WH", size: 90,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "b2b_inventory",    accessorKey: "b2b_inventory",    header: "B2B",       size: 60,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "required_units",   accessorKey: "required_units",   header: "Req",       size: 65,  meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "warehouse_shortfall", accessorKey: "warehouse_shortfall", header: "Shortfall", size: 85, meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "replenishment_qty",accessorKey: "replenishment_qty",header: "Replen Qty",size: 90,  meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "buffer_note",      accessorKey: "buffer_note",      header: "Buffer",    size: 100, meta: { group: "rep" } },
    { id: "oos_weeks_3m",     accessorKey: "oos_weeks_3m",     header: "OOS 3m",    size: 70, meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "thin_weeks_3m",    accessorKey: "thin_weeks_3m",    header: "Thin 3m",   size: 70, meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "lost_units_3m",    accessorKey: "lost_units_3m",    header: "Lost Est",  size: 80, meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "momentum_flag",    accessorKey: "momentum_flag",    header: "Momentum",  size: 95, meta: { group: "rep" } },
    { id: "recommended_qty",  accessorKey: "recommended_qty",  header: "Rec Qty",   size: 80,  meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "cartons_needed",   accessorKey: "cartons_needed",   header: "Cartons",   size: 80,  meta: { group: "rep", numeric: true, sortDescFirst: true } },
    { id: "working_value",    accessorKey: "working_value",    header: "Working",   size: 85,  meta: { group: "rep" } },
    { id: "ixd_type",         accessorKey: "ixd_type",         header: "IXD",       size: 65,  meta: { group: "log" } },
    { id: "hazmat_type",      accessorKey: "hazmat_type",      header: "Hazmat",    size: 90,  meta: { group: "log" } },
    { id: "master_carton",    accessorKey: "master_carton",    header: "MC",        size: 55,  meta: { group: "log" } },
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

  // Fast O(1) lookup set for selected cells
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
    const sortedRows = table.getRowModel().rows;
    let count = 0, sum = 0;
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const col = columns[c];
        const orig = sortedRows[r]?.original;
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
  }, [selRange, columns, table]);

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
    // Append the calc-trace column so operator can verify how Replen Qty was derived.
    headers.push("Formula (Replen Qty)");

    // Preamble — symbolic formulas at the top of the file (before the header row)
    // so anyone opening the CSV sees the calc convention immediately.
    const preamble = [
      `# Replenishment export — ${account} · ${replenishWeeks}wk cover · window wk ${fromWeek}-${toWeek}`,
      `# Formulas:`,
      `#   Avg/Wk        = max(window avg , last-2-week avg)`,
      `#   Req           = Avg/Wk × Inventory Cover`,
      `#   Effective Inv = Real AM Inv (available) + Inbound`,
      `#   Shortfall     = max(0 , Req − Effective Inv)`,
      `#   Replen Qty    = min(Shortfall , Mother WH)   (0 if AMPM in buffer range 1..10)`,
      `#   Total sold qty column: window total when Basis=window, else last-2-week total`,
      `#`,
    ];
    const lines = [...preamble, headers.join(",")];

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
      // Build per-row calc trace with the actual numbers substituted.
      const avg = Number(r.sales_velocity || 0);
      const inv = Number(r.real_am_inv_available || 0);
      const inb = Number(r.inbound_inventory   || 0);
      const req = Number(r.required_units      || 0);
      const eff = inv + inb;
      const shortfall = Math.max(0, req - eff);
      const ampm = Number(r.ampm_inventory || 0);
      const replen = Number(r.replenishment_qty || 0);
      const bufferNote = String(r.buffer_note || "");
      let trace = `Req=${avg}×${replenishWeeks}=${req} · EffInv=${inv}+${inb}=${eff} · Shortfall=max(0,${req}-${eff})=${shortfall} · MotherWH=${ampm} → Replen=${replen}`;
      if (bufferNote) trace += ` [${bufferNote}]`;
      const traceEsc = trace.replace(/"/g, '""');
      cells.push(/[",\n]/.test(traceEsc) ? `"${traceEsc}"` : traceEsc);
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
        <DataFreshnessBanner module="replenishment" />
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
            <SOPButton onClick={() => setSopOpen(true)} />
            <button onClick={exportCSV} className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            {canPropose && (() => {
              const APPROVER = String(account).toUpperCase() === "FOSSIL"
                ? "kanwal@cambiumretail.com"
                : "sagar@cambiumretail.com";
              const buildRows = () => (rows || [])
                .map((r) => {
                  // Prefer Naresh's Working Value override if he entered one;
                  // else fall back to the calc engine's replenishment_qty.
                  const wv = workingValues[r.sku];
                  const finalQty = Math.round(Number(
                    (wv !== undefined && wv !== "" && wv !== null) ? wv : r.replenishment_qty
                  ) || 0);
                  return {
                    sku: r.sku,
                    model: r.model || "",
                    asin: r.asin || "",
                    // Replenishment tab is per-SKU aggregate — no FC dimension.
                    // Route all lines to ISK3 (Amazon India's default marketplace
                    // FC). Operator-approved 2026-08-07: for SKU-level asks we
                    // let ISK3 receive and Amazon distributes from there. For
                    // per-FC control, use FC Allocation's Propose flow instead.
                    destination_fc: "ISK3",
                    qty: finalQty,
                    // Snapshot planning context so approver sees the numbers
                    real_am_inv:     r.real_am_inv_available ?? null,
                    mother_inv:      r.ampm_inventory ?? null,
                    weekly_velocity: r.weekly_velocity ?? r.sales_velocity ?? null,
                    // Amazon FBA split keys
                    hazmat:   String(r["Hazmat/non-Hazmat"] || r.hazmat_type || "").toLowerCase().includes("hazmat")
                              && !String(r["Hazmat/non-Hazmat"] || "").toLowerCase().includes("non"),
                    ixd_flag: r.ixd_flag || (String(r["Hazmat Type"] || r.hazmat_type || "").toUpperCase().includes("NON IXD") ? "NON IXD" : "IXD"),
                  };
                })
                .filter((r) => r.qty > 0);
              const runSubmit = async (kind) => {
                const toSend = buildRows();
                if (toSend.length === 0) {
                  setProposeMsg("Nothing to save — no rows with Replen Qty > 0");
                  setTimeout(() => setProposeMsg(""), 4000);
                  return;
                }
                const verb = kind === "draft" ? "Save" : "Propose";
                const target = kind === "draft" ? "a draft (editable, not yet sent)" : APPROVER;
                if (!confirm(`${verb} ${toSend.length} rows for ${account} → ${target}?`)) return;
                setProposing(true); setProposeMsg("");
                try {
                  const fn = kind === "draft" ? saveDraft : proposePlan;
                  const j = await fn({
                    account, rows: toSend,
                    source_module: "replenishment",
                    approver_email: APPROVER,
                    cover_weeks: Number(replenishWeeks) || null,
                  });
                  setProposeMsg(`${kind === "draft" ? "Draft saved" : "Proposed"} → ${j.batch_id}`);
                } catch (e) {
                  setProposeMsg(`Error: ${e.message}`);
                } finally {
                  setProposing(false);
                  setTimeout(() => setProposeMsg(""), 8000);
                }
              };
              return (
                <>
                  <button
                    onClick={() => runSubmit("draft")}
                    disabled={proposing}
                    className="px-3 py-2 rounded-md border border-slate-300 bg-white text-sm font-medium hover:bg-slate-50 disabled:opacity-50"
                    title="Save current rows as an editable draft. Tweak in Plans Approval before sending."
                  >
                    Save Draft
                  </button>
                  <button
                    onClick={() => runSubmit("propose")}
                    disabled={proposing}
                    className="px-3 py-2 rounded-md bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium disabled:opacity-50"
                    title={`Send immediately to ${APPROVER}`}
                  >
                    {proposing ? "…" : "Propose to Approver"}
                  </button>
                </>
              );
            })()}
            {proposeMsg && (
              <span className="text-xs text-amber-700 ml-1">{proposeMsg}</span>
            )}
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

        {/* KPI strip — derivations match V1 conventions */}
        <div className="grid grid-cols-6 gap-3 mb-5">
          <KPICard
            label="Units to Ship"
            value={rows.reduce((a, r) => a + (r.recommended_qty || r.replenishment_qty || 0), 0)}
            hint={`${rows.filter(r => (r.recommended_qty || r.replenishment_qty || 0) > 0).length} models need stock`}
            tone="brand"
          />
          <KPICard
            label="China PO Gap"
            value={rows.reduce((a, r) => a + (r.warehouse_shortfall || 0), 0)}
            hint={rows.reduce((a, r) => a + (r.warehouse_shortfall || 0), 0) > 0 ? "Raise a new China PO" : "WH covers full need"}
            tone="warn"
          />
          <KPICard
            label="Critical SKUs"
            value={rows.filter(r => r.is_risky).length}
            hint="below 1-week cover"
            tone="bad"
          />
          <KPICard
            label="Cartons Needed"
            value={rows.reduce((a, r) => a + (r.cartons_needed || 0), 0)}
            hint={`${rows.filter(r => !r.is_risky && !r.is_overstock).length} SKUs healthy`}
          />
          <KPICard
            label="2wk Bump"
            value={rows.filter(r => r.velocity_basis === "2wk").length}
            hint="SKUs using 4-wk avg"
          />
          <KPICard
            label="Total Models"
            value={rows.length}
            hint={`across ${categories.length} categories`}
          />
        </div>

        {/* Saved views */}
        <div className="mb-3">
          <SavedViews views={views} active={view} onPick={setView} />
        </div>

        {/* Filters */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-3 mb-3">
          <div className="grid grid-cols-12 gap-3 items-end">
            <div className="col-span-5">
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
              <Label>Past Sales (selected weeks)</Label>
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
              <Label>Inventory Cover</Label>
              <select value={replenishWeeks} onChange={e => setReplenishWeeks(Number(e.target.value))}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                {[2, 4, 6, 8, 10, 12].map(n => <option key={n}>{n}</option>)}
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

          {/* Category + Status chip filters */}
          {(categories.length > 0 || listingStatuses.length > 0) && (
            <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap items-center gap-1.5">
              {categories.length > 0 && (
                <>
                  <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mr-1">Category</span>
                  {categories.map(cat => {
                    const on = selectedCategories.includes(cat);
                    return (
                      <button
                        key={cat}
                        onClick={() => setSelectedCategories(p => p.includes(cat) ? p.filter(c => c !== cat) : [...p, cat])}
                        className={cn(
                          "px-2.5 py-1 text-xs font-medium rounded-md border transition-colors",
                          on
                            ? "bg-indigo-600 text-white border-indigo-600"
                            : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                        )}
                      >
                        {cat}
                      </button>
                    );
                  })}
                  {selectedCategories.length > 0 && (
                    <button onClick={() => setSelectedCategories([])} className="text-xs text-slate-500 hover:text-slate-900 ml-1">clear</button>
                  )}
                </>
              )}

              {categories.length > 0 && listingStatuses.length > 0 && (
                <span className="text-slate-200 mx-2">·</span>
              )}

              {listingStatuses.length > 0 && (
                <>
                  <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mr-1">Status</span>
                  {listingStatuses.map(ls => {
                    const on = selectedStatuses.includes(ls);
                    const dot =
                      ls === "Active" ? "bg-emerald-500" :
                      ls === "EOL"    ? "bg-red-500" :
                                        "bg-slate-400";
                    return (
                      <button
                        key={ls}
                        onClick={() => setSelectedStatuses(p => p.includes(ls) ? p.filter(s => s !== ls) : [...p, ls])}
                        className={cn(
                          "px-2.5 py-1 text-xs font-medium rounded-md border inline-flex items-center gap-1.5 transition-colors",
                          on
                            ? "bg-slate-900 text-white border-slate-900"
                            : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                        )}
                      >
                        <span className={cn("w-1.5 h-1.5 rounded-full", dot)} />
                        {ls}
                      </button>
                    );
                  })}
                  {selectedStatuses.length > 0 && (
                    <button onClick={() => setSelectedStatuses([])} className="text-xs text-slate-500 hover:text-slate-900 ml-1">clear</button>
                  )}
                </>
              )}
            </div>
          )}
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
                  const isBumped   = r.velocity_basis === "2wk";

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
                          const isSelected = selectedSet.has(`${ri}-${ci}`);

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
                          } else if (colId === "trend") {
                            content = <Sparkline data={r.weekly_sales || []} />;
                          } else if (colId === "sales_velocity") {
                            content = (
                              <span className="font-semibold tabular-nums">
                                {Number(r.sales_velocity ?? 0).toFixed(1)}
                                {isBumped && (
                                  <span className="inline-flex ml-1 px-1 py-0.5 text-[9px] font-bold rounded bg-indigo-100 text-indigo-700">2wk</span>
                                )}
                              </span>
                            );
                          } else if (colId === "warehouse_shortfall") {
                            content = (
                              <span className={cn("tabular-nums", (r.warehouse_shortfall || 0) > 0 && "text-amber-700 font-semibold")}>
                                {r.warehouse_shortfall > 0 ? r.warehouse_shortfall : "—"}
                              </span>
                            );
                          } else if (colId === "replenishment_qty") {
                            content = <span className="font-bold tabular-nums text-slate-900">{r.replenishment_qty}</span>;
                          } else if (colId === "oos_weeks_3m") {
                            const n = r.oos_weeks_3m || 0;
                            content = n === 0 ? <span className="text-slate-300">—</span> : (
                              <span className={cn("tabular-nums font-semibold",
                                n >= 4 ? "text-red-700" : n >= 2 ? "text-red-600" : "text-amber-700")}>
                                {n}
                              </span>
                            );
                          } else if (colId === "thin_weeks_3m") {
                            const n = r.thin_weeks_3m || 0;
                            content = n === 0 ? <span className="text-slate-300">—</span> : (
                              <span className={cn("tabular-nums font-semibold",
                                n >= 4 ? "text-red-600" : n >= 2 ? "text-amber-700" : "text-slate-600")}>
                                {n}
                              </span>
                            );
                          } else if (colId === "lost_units_3m") {
                            const v = r.lost_units_3m || 0;
                            content = v === 0 ? <span className="text-slate-300">—</span> : (
                              <span className="tabular-nums text-slate-700 font-medium">{v.toLocaleString("en-IN")}</span>
                            );
                          } else if (colId === "momentum_flag") {
                            const flag = r.momentum_flag || "";
                            const oos = r.oos_weeks_3m || 0;
                            const thin = r.thin_weeks_3m || 0;
                            // RED sub-label: prefer "Bleeding" (OOS) if applicable, else "Starving" (thin)
                            const redLabel = oos >= 2 ? "Bleeding" : "Starving";
                            if (flag === "RED") content = (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-bold uppercase bg-red-100 text-red-800 ring-1 ring-red-300">
                                {redLabel}
                              </span>
                            );
                            else if (flag === "AMBER") content = (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[10px] font-semibold uppercase bg-amber-100 text-amber-800 ring-1 ring-amber-300">
                                At risk
                              </span>
                            );
                            else content = <span className="text-slate-300">—</span>;
                          } else if (colId === "recommended_qty") {
                            const recQty     = r.recommended_qty ?? r.replenishment_qty ?? 0;
                            const rawQty     = r.replenishment_qty ?? 0;
                            const breakFlag  = r.carton_break_flag ?? false;
                            const noCarton   = !r.master_carton || r.master_carton === 0;
                            if (rawQty === 0) content = <span className="text-slate-300">—</span>;
                            else if (noCarton) content = <span className="text-slate-400 text-[10px] italic">no carton</span>;
                            else content = (
                              <span
                                title={`Raw replenishment: ${rawQty} → Rounded ${breakFlag ? "(carton break)" : "to full cartons"}: ${recQty}`}
                                className={cn(
                                  "font-bold tabular-nums",
                                  breakFlag ? "text-orange-600" : r.ixd_type === "IXD" ? "text-blue-700" : "text-slate-900"
                                )}
                              >
                                {recQty}{breakFlag && <span className="ml-1 text-orange-500">⚠</span>}
                              </span>
                            );
                          } else if (colId === "cartons_needed") {
                            const cartons = r.cartons_needed ?? 0;
                            const rawQty  = r.replenishment_qty ?? 0;
                            const noCarton = !r.master_carton || r.master_carton === 0;
                            if (rawQty === 0 || noCarton) content = <span className="text-slate-300">—</span>;
                            else content = (
                              <span
                                title={r.ixd_type === "IXD" ? "IXD — full cartons mandatory" : "Non-IXD — carton break allowed"}
                                className={cn(
                                  "inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium border rounded tabular-nums",
                                  r.ixd_type === "IXD"
                                    ? "bg-blue-50 text-blue-700 border-blue-200"
                                    : "bg-slate-50 text-slate-600 border-slate-200"
                                )}
                              >
                                {cartons} {cartons !== 1 ? "ctns" : "ctn"}
                              </span>
                            );
                          } else if (colId === "hazmat_type") {
                            const h = (r.hazmat_type || "").toLowerCase();
                            const isHaz = h && !h.includes("non");
                            content = isHaz
                              ? <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-amber-100 text-amber-800">{r.hazmat_type}</span>
                              : <span className="text-slate-500 text-xs">{r.hazmat_type || "—"}</span>;
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
                                className="w-16 text-right px-1.5 py-1 border border-amber-300 rounded text-xs font-mono bg-amber-50/60 disabled:bg-amber-50/40 font-semibold"
                                placeholder="—"
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
                            // Use cell.getValue() so columns with accessorFn (e.g. basis-aware
                            // "Total sold qty") show the derived value, not the raw row field.
                            const v = cell.getValue();
                            content = (
                              <span className="tabular-nums">
                                {v ?? r[colId] ?? "—"}
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

      {/* SOP modal */}
      <SOPModal open={sopOpen} onClose={() => setSopOpen(false)} title="Replenishment">
        <ReplenishmentSOPContent />
      </SOPModal>

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
