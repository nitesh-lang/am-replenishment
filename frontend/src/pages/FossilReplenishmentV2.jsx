import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Search, Download, ChevronDown, ChevronRight, Settings2,
} from "lucide-react";

import { CommandPalette } from "../components/CommandPalette";
import { SavedViews } from "../components/SavedViews";
import { SOPModal, SOPButton } from "../components/SOPModal";
import { FossilReplenishmentSOPContent } from "../components/SOPContents";
import DataFreshnessBanner from "../components/DataFreshnessBanner";
import { cn } from "../lib/cn";
import { proposePlan, saveDraft } from "../api/plans";
import { useAuth } from "../auth/AuthContext";

/* ============================================================
   FOSSIL REPLENISHMENT V2 — TanStack + v2 pattern
   Endpoint reused: GET /api/fossil-replenishment?cover_weeks&from_week&to_week
   Read-only (no save endpoint).
============================================================ */

const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";

const BRAND_ORDER = ["Fossil", "Armani Exchange", "Michael Kors", "Emporio Armani", "Diesel", "Skagen"];

const WOC_MATRIX = [
  { brand: "Fossil",          fp: 9, discount: 4, vd: 6 },
  { brand: "Armani Exchange", fp: 6, discount: 4, vd: 6 },
  { brand: "Michael Kors",    fp: 6, discount: 4, vd: 6 },
  { brand: "Emporio Armani",  fp: 4, discount: 4, vd: 6 },
  { brand: "Diesel",          fp: 4, discount: 4, vd: 6 },
  { brand: "Skagen",          fp: 4, discount: 4, vd: 6 },
];

export default function FossilReplenishmentV2() {
  const { user } = useAuth();
  const canPropose = (user?.allowedModules || []).includes("plans-editor") || user?.role === "admin";
  const [proposing, setProposing] = useState(false);
  const [proposeMsg, setProposeMsg] = useState("");

  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek,   setToWeek]   = useState(null);
  const [coverWeeks, setCoverWeeks] = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [view, setView] = useState("all");
  const [brand, setBrand] = useState("All");
  const [sorting, setSorting] = useState([]);
  const [expandedSku, setExpandedSku] = useState(null);
  const [density, setDensity] = useState("cozy");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 100;
  const [showMatrix, setShowMatrix] = useState(false);

  /* Range-select */
  const [selRange, setSelRange] = useState(null);
  const draggingRef = useRef(null);

  /* SOP modal */
  const [sopOpen, setSopOpen] = useState(false);

  /* ============================================================
     LOAD
  ============================================================ */
  useEffect(() => {
    setLoading(true);
    setExpandedSku(null);
    const params = new URLSearchParams();
    if (coverWeeks) params.append("cover_weeks", coverWeeks);
    if (fromWeek)   params.append("from_week",   fromWeek);
    if (toWeek)     params.append("to_week",     toWeek);
    fetch(`${BASE}/api/fossil-replenishment?${params}`)
      .then(r => r.json())
      .then(res => {
        setRows(res.data || []);
        if (res.available_weeks?.length) {
          const weeks = res.available_weeks;
          setAvailableWeeks(weeks);
          if (!fromWeek) {
            const defaultFrom = weeks.length > 12 ? weeks[weeks.length - 12] : weeks[0];
            setFromWeek(defaultFrom);
          }
          if (!toWeek) setToWeek(weeks[weeks.length - 1]);
        }
      })
      .finally(() => setLoading(false));
  }, [fromWeek, toWeek, coverWeeks]);

  useEffect(() => { setPage(1); }, [search, view, brand, fromWeek, toWeek]);

  /* ============================================================
     DERIVED
  ============================================================ */
  const brandsInData = useMemo(() => {
    const set = new Set(rows.map(r => r["Brand"]).filter(Boolean));
    return ["All", ...BRAND_ORDER.filter(b => set.has(b))];
  }, [rows]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter(r => {
      if (brand !== "All" && r["Brand"] !== brand) return false;
      if (q && !(
        String(r["Item No"] ?? "").toLowerCase().includes(q) ||
        String(r["SKU"] ?? "").toLowerCase().includes(q) ||
        String(r["ASIN"] ?? "").toLowerCase().includes(q)
      )) return false;
      if (view === "fp")       return r["Assortment Type"] === "FP";
      if (view === "discount") return r["Assortment Type"] === "Discount";
      if (view === "vd")       return r["Assortment Type"] === "VD";
      if (view === "replen")   return (r["Replenishment Qty"] || 0) > 0;
      if (view === "shortfall") {
        return (r["Fossil SOH"] || 0) < (r["Required Inventory"] || 0);
      }
      return true;
    });
  }, [rows, search, view, brand]);

  const views = useMemo(() => {
    const byType = t => rows.filter(r => r["Assortment Type"] === t).length;
    return [
      { key: "all",       label: "All",            count: rows.length },
      { key: "fp",        label: "FP",             count: byType("FP") },
      { key: "discount",  label: "Discount",       count: byType("Discount") },
      { key: "vd",        label: "VD",             count: byType("VD") },
      { key: "replen",    label: "Has Replen",     count: rows.filter(r => (r["Replenishment Qty"] || 0) > 0).length, accent: "bg-red-100 text-red-700" },
      { key: "shortfall", label: "Below Required", count: rows.filter(r => (r["Fossil SOH"] || 0) < (r["Required Inventory"] || 0)).length },
    ];
  }, [rows]);

  const kpis = useMemo(() => {
    const totalReplen = filteredRows.reduce((a, r) => a + (Number(r["Replenishment Qty"]) || 0), 0);
    const totalReq    = filteredRows.reduce((a, r) => a + (Number(r["Required Inventory"]) || 0), 0);
    const critical    = filteredRows.filter(r => (r["Replenishment Qty"] || 0) > 0).length;
    return { totalReplen: Math.round(totalReplen), totalReq: Math.round(totalReq), critical };
  }, [filteredRows]);

  /* ============================================================
     COLUMNS — Fossil schema uses Title-Case keys
  ============================================================ */
  const columns = useMemo(() => [
    { id: "SKU",                             accessorKey: "SKU",                            header: "SKU",        size: 110, meta: { sticky: 1, group: "id" } },
    { id: "ASIN",                            accessorKey: "ASIN",                           header: "ASIN",       size: 110, meta: { group: "id" } },
    { id: "Item No",                         accessorKey: "Item No",                        header: "Item No",    size: 130, meta: { group: "id" } },
    { id: "Brand",                           accessorKey: "Brand",                          header: "Brand",      size: 110, meta: { group: "id" } },
    { id: "Assortment Type",                 accessorKey: "Assortment Type",                header: "Assortment", size: 95,  meta: { group: "id" } },
    { id: "3 Months Gross Sales",            accessorKey: "3 Months Gross Sales",           header: "3M Gross",   size: 90,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "Fossil Weekly Sales",             accessorKey: "Fossil Weekly Sales",            header: "Weekly Avg", size: 95,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "Last 4 Weeks Top Avg",            accessorKey: "Last 4 Weeks Top Avg",           header: "4wk Top",    size: 90,  meta: { group: "sales", numeric: true, sortDescFirst: true } },
    { id: "Cambium SOH",                     accessorKey: "Cambium SOH",                    header: "Cambium SOH",size: 100, meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "Andheri/Goregaon sellable Stock", accessorKey: "Andheri/Goregaon sellable Stock",header: "Andheri/Gor",size: 110, meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "In Transit PO",                   accessorKey: "In Transit PO",                  header: "In Transit", size: 90,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "Open PO",                         accessorKey: "Open PO",                        header: "Open PO",    size: 80,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "Total Inventory",                 accessorKey: "Total Inventory",                header: "Total Inv",  size: 90,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "Fossil SOH",                      accessorKey: "Fossil SOH",                     header: "Fossil SOH", size: 95,  meta: { group: "inv", numeric: true, sortDescFirst: true } },
    { id: "Required Inventory",              accessorKey: "Required Inventory",             header: "Required",   size: 95,  meta: { group: "plan", numeric: true, sortDescFirst: true } },
    { id: "Replenishment Qty",               accessorKey: "Replenishment Qty",              header: "Replen Qty", size: 100, meta: { group: "plan", numeric: true, sortDescFirst: true } },
    { id: "Remarks",                         accessorKey: "Remarks",                        header: "Remarks",    size: 360, meta: { group: "plan" } },
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
        // VD rows: 4wk top avg should be blank
        if (id === "Last 4 Weeks Top Avg" && r["Assortment Type"] === "VD") v = "";
        if (v == null) v = "";
        const s = String(v).replace(/"/g, '""');
        return /[",\n]/.test(s) ? `"${s}"` : s;
      });
      lines.push(cells.join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `fossil_replenishment_${brand.toLowerCase().replace(/\s+/g, "_")}_${view}.csv`;
    a.click();
  }

  /* ============================================================
     PALETTE
  ============================================================ */
  function onPaletteSelect(item) {
    if (item.type === "sku") {
      setExpandedSku(item.payload.SKU || item.payload.sku);
      requestAnimationFrame(() => {
        const el = document.querySelector(`[data-row-sku="${item.payload.SKU || item.payload.sku}"]`);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    } else if (item.type === "view") {
      setView(item.payload.key);
    } else if (item.type === "action" && item.payload === "export") {
      exportCSV();
    }
  }

  /* ============================================================
     STYLE HELPERS
  ============================================================ */
  function wocColor(weeks) {
    if (weeks >= 9) return "bg-purple-100 text-purple-700";
    if (weeks >= 6) return "bg-blue-100 text-blue-700";
    return "bg-emerald-100 text-emerald-700";
  }
  function assortBadge(t) {
    if (t === "VD")       return "bg-orange-100 text-orange-700";
    if (t === "Discount") return "bg-amber-100 text-amber-700";
    return "bg-indigo-100 text-indigo-700";
  }

  /* ============================================================
     RENDER
  ============================================================ */
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="w-full px-6 pt-5 pb-10">
        <DataFreshnessBanner module="fossil-replenishment" />

        <div className="flex items-end justify-between mb-4">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-500 font-medium">Module</div>
            <h1 className="text-2xl font-semibold mt-0.5 tracking-tight">
              Fossil Replenishment <span className="text-slate-300 font-normal">·</span> <span className="text-slate-500 text-lg font-medium">{brand}</span>
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <SOPButton onClick={() => setSopOpen(true)} />
            <button onClick={() => setShowMatrix(s => !s)}
              className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50">
              {showMatrix ? "Hide" : "Show"} WOC Matrix
            </button>
            <button onClick={exportCSV} className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            {canPropose && (() => {
              const APPROVER = "kanwal@cambiumretail.com";
              const buildRows = () => (rows || [])
                .filter((r) => Number(r["Replenishment Qty"]) > 0)
                .map((r) => ({
                  sku: r["SKU"],
                  model: r["Item No"] || r["Model"] || "",
                  asin: r["ASIN"] || "",
                  // Fossil is 1P Vendor Central; no per-FC breakdown at
                  // this granularity. Placeholder — Kanwal can split during curation.
                  destination_fc: "VENDOR",
                  qty: Math.round(Number(r["Replenishment Qty"])),
                  // Snapshot planning context for approver
                  real_am_inv:     r["Total Inventory"] ?? null,
                  mother_inv:      r["Cambium SOH"] ?? null,
                  weekly_velocity: r["Fossil Weekly Sales"] ?? null,
                  // Vendor Central doesn't split by hazmat/IXD — send null
                  hazmat:   null,
                  ixd_flag: null,
                }));
              const runSubmit = async (kind) => {
                const toSend = buildRows();
                if (toSend.length === 0) {
                  setProposeMsg("Nothing to save — no rows with Replenishment Qty > 0");
                  setTimeout(() => setProposeMsg(""), 4000);
                  return;
                }
                const verb = kind === "draft" ? "Save" : "Propose";
                const target = kind === "draft" ? "a draft (editable, not yet sent)" : APPROVER;
                if (!confirm(`${verb} ${toSend.length} Fossil SKUs → ${target}?`)) return;
                setProposing(true); setProposeMsg("");
                try {
                  const fn = kind === "draft" ? saveDraft : proposePlan;
                  const j = await fn({
                    account: "FOSSIL", rows: toSend,
                    source_module: "fossil-replenishment",
                    approver_email: APPROVER,
                    cover_weeks: Number(coverWeeks) || null,
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
                    title="Save current rows as an editable draft. You can tweak before sending to Kanwal."
                  >
                    Save Draft
                  </button>
                  <button
                    onClick={() => runSubmit("propose")}
                    disabled={proposing}
                    className="px-3 py-2 rounded-md bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium disabled:opacity-50"
                    title="Send immediately to Kanwal, skipping the draft state"
                  >
                    {proposing ? "…" : "Propose to Approver"}
                  </button>
                </>
              );
            })()}
            {proposeMsg && (
              <span className="text-xs text-amber-700 ml-1">{proposeMsg}</span>
            )}
          </div>
        </div>

        {/* WOC matrix (collapsible) */}
        {showMatrix && (
          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 mb-4">
            <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-3">Weeks-of-Cover Matrix (per brand × assortment)</div>
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left">Brand</th>
                  <th className="px-3 py-2 text-center">FP</th>
                  <th className="px-3 py-2 text-center">Discount</th>
                  <th className="px-3 py-2 text-center">VD</th>
                </tr>
              </thead>
              <tbody>
                {WOC_MATRIX.map(r => (
                  <tr key={r.brand} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-medium">{r.brand}</td>
                    <td className="px-3 py-2 text-center"><span className={cn("px-2 py-0.5 rounded text-xs font-semibold", wocColor(r.fp))}>{r.fp}w</span></td>
                    <td className="px-3 py-2 text-center"><span className={cn("px-2 py-0.5 rounded text-xs font-semibold", wocColor(r.discount))}>{r.discount}w</span></td>
                    <td className="px-3 py-2 text-center"><span className={cn("px-2 py-0.5 rounded text-xs font-semibold", wocColor(r.vd))}>{r.vd}w</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="grid grid-cols-5 gap-3 mb-5">
          <KPICard label="Total Models"   value={rows.length}            hint={`${brandsInData.length - 1} brands`} />
          <KPICard label="In View"        value={filteredRows.length}    hint={view !== "all" ? view : "all rows"} />
          <KPICard label="Total Required" value={kpis.totalReq}          hint="units required" />
          <KPICard label="Total Replen"   value={kpis.totalReplen}       hint="units to ship" tone="brand" />
          <KPICard label="Critical"       value={kpis.critical}          hint="replen > 0" tone="bad" />
        </div>

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
                {brandsInData.map(b => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>
          </div>
        </div>

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
                  placeholder="Item No / SKU / ASIN…"
                />
              </div>
            </div>

            <div className="col-span-3">
              <Label>Sales Window (Range)</Label>
              <div className="grid grid-cols-2 gap-1.5">
                <select value={fromWeek ?? ""} onChange={e => setFromWeek(Number(e.target.value))}
                  className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                  disabled={!availableWeeks.length}>
                  {availableWeeks.map(w => <option key={`f-${w}`} value={w}>From Wk {w}</option>)}
                </select>
                <select value={toWeek ?? ""} onChange={e => setToWeek(Number(e.target.value))}
                  className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                  disabled={!availableWeeks.length}>
                  {availableWeeks.map(w => <option key={`t-${w}`} value={w}>To Wk {w}</option>)}
                </select>
              </div>
            </div>

            <div className="col-span-2">
              <Label>Cover Wks (override)</Label>
              <select value={coverWeeks ?? ""} onChange={e => setCoverWeeks(e.target.value ? Number(e.target.value) : null)}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                <option value="">Matrix default</option>
                {[2, 4, 6, 8, 9, 10, 12].map(n => <option key={n}>{n}</option>)}
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
                  const sku = r["SKU"];
                  const isExpanded = expandedSku === sku;
                  const isCritical = (r["Replenishment Qty"] || 0) > 0;
                  const isVD = r["Assortment Type"] === "VD";

                  return (
                    <React.Fragment key={sku || globalRowIdx}>
                      <tr
                        data-row-sku={sku}
                        className={cn(
                          "hover:bg-slate-50/60 cursor-pointer",
                          isCritical && "bg-red-50/40",
                          isExpanded && "bg-indigo-50/30",
                        )}
                        onClick={() => setExpandedSku(isExpanded ? null : sku)}
                      >
                        {trow.getVisibleCells().map((cell, ci) => {
                          const colId = cell.column.id;
                          const meta = cell.column.columnDef.meta || {};
                          const isSelected = selectedSet.has(`${globalRowIdx}-${ci}`);

                          let content;
                          if (colId === "SKU") {
                            content = (
                              <span className="font-mono text-xs text-slate-700 inline-flex items-center gap-1">
                                {isExpanded
                                  ? <ChevronDown  className="w-3.5 h-3.5 text-indigo-600" />
                                  : <ChevronRight className="w-3.5 h-3.5 text-slate-300" />}
                                {sku}
                              </span>
                            );
                          } else if (colId === "ASIN") {
                            content = <span className="font-mono text-xs text-slate-500">{r["ASIN"] || "—"}</span>;
                          } else if (colId === "Item No") {
                            content = <span className="font-semibold text-slate-900">{r["Item No"]}</span>;
                          } else if (colId === "Brand") {
                            content = <span className="text-slate-600">{r["Brand"] || "—"}</span>;
                          } else if (colId === "Assortment Type") {
                            content = (
                              <span className={cn("inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded", assortBadge(r["Assortment Type"]))}>
                                {r["Assortment Type"] || "FP"}
                              </span>
                            );
                          } else if (colId === "Fossil Weekly Sales") {
                            content = <span className="tabular-nums font-semibold">{(r["Fossil Weekly Sales"] || 0).toFixed(1)}</span>;
                          } else if (colId === "Last 4 Weeks Top Avg") {
                            content = isVD
                              ? <span className="text-slate-300">—</span>
                              : <span className="tabular-nums">{(r["Last 4 Weeks Top Avg"] || 0).toFixed(1)}</span>;
                          } else if (colId === "Required Inventory") {
                            content = <span className="font-semibold tabular-nums text-indigo-700">{Math.round(r["Required Inventory"] || 0)}</span>;
                          } else if (colId === "Replenishment Qty") {
                            const v = r["Replenishment Qty"] || 0;
                            content = (
                              <span className={cn("font-bold tabular-nums", v > 0 ? "text-red-700" : "text-slate-400")}>
                                {v > 0 ? Math.round(v) : "—"}
                              </span>
                            );
                          } else if (colId === "Fossil SOH") {
                            const soh = r["Fossil SOH"] || 0;
                            const req = r["Required Inventory"] || 0;
                            const tone = soh < req ? "text-red-700 font-semibold" : "";
                            content = <span className={cn("tabular-nums", tone)}>{soh}</span>;
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
                        <FossilDetailRow row={r} colSpan={columns.length} />
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
          <Legend swatch="bg-red-100"    label="Has Replenishment" />
          <Legend swatch="bg-indigo-100" label="Range-selected" />
          <span className="ml-auto text-slate-400">Read-only · WOC matrix governs Required Inventory</span>
        </div>
      </div>

      <SOPModal open={sopOpen} onClose={() => setSopOpen(false)} title="Fossil Replenishment">
        <FossilReplenishmentSOPContent />
      </SOPModal>

      <CommandPalette
        rows={rows.map(r => ({ ...r, sku: r["SKU"], asin: r["ASIN"], model: r["Item No"] }))}
        views={views.map(v => ({ key: v.key, label: v.label, hint: `${v.count} rows` }))}
        onPick={onPaletteSelect}
      />
    </div>
  );
}

/* ============================================================
   DETAIL ROW
============================================================ */

function FossilDetailRow({ row, colSpan }) {
  const cambium = Number(row["Cambium SOH"] || 0);
  const ag      = Number(row["Andheri/Goregaon sellable Stock"] || 0);
  const it      = Number(row["In Transit PO"] || 0);
  const op      = Number(row["Open PO"] || 0);
  const total   = cambium + ag + it + op;
  const pct = (v) => total > 0 ? Math.round((v / total) * 100) : 0;

  const matrix = WOC_MATRIX.find(m => m.brand === row["Brand"]);
  const targetWoc = matrix
    ? (row["Assortment Type"] === "Discount" ? matrix.discount : row["Assortment Type"] === "VD" ? matrix.vd : matrix.fp)
    : null;

  return (
    <tr className="bg-indigo-50/20">
      <td colSpan={colSpan} className="!p-0">
        <div className="px-6 py-5 bg-gradient-to-b from-indigo-50/40 to-white border-l-4 border-indigo-500 grid grid-cols-12 gap-5">
          <div className="col-span-5">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Inventory split</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2.5 text-xs">
              <Bar label="Cambium SOH" val={cambium} pct={pct(cambium)} color="bg-indigo-500" />
              <Bar label="Andheri / Goregaon" val={ag} pct={pct(ag)} color="bg-emerald-500" />
              <Bar label="In-Transit PO" val={it} pct={pct(it)} color="bg-amber-500" />
              <Bar label="Open PO" val={op} pct={pct(op)} color="bg-violet-500" />
              <div className="pt-1 border-t border-slate-100 flex justify-between">
                <span className="text-slate-500 font-semibold">Total Inventory</span>
                <span className="font-mono tabular-nums font-bold text-slate-900">{row["Total Inventory"] ?? total}</span>
              </div>
            </div>
          </div>

          <div className="col-span-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Demand</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <KV label="3-Month Gross"     val={Math.round(row["3 Months Gross Sales"] || 0)} />
              <KV label="Fossil Weekly Avg" val={(row["Fossil Weekly Sales"] || 0).toFixed(2)} accent />
              {row["Assortment Type"] !== "VD" && (
                <KV label="Last 4-Wk Top Avg" val={(row["Last 4 Weeks Top Avg"] || 0).toFixed(2)} />
              )}
              <div className="pt-2 border-t border-slate-100 flex justify-between">
                <span className="text-slate-500">Assortment Type</span>
                <span className="font-semibold text-slate-900">{row["Assortment Type"] || "FP"}</span>
              </div>
              {targetWoc !== null && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Target WOC</span>
                  <span className="font-mono tabular-nums font-bold text-indigo-700">{targetWoc} wks</span>
                </div>
              )}
            </div>
          </div>

          <div className="col-span-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Plan</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <KV label="Fossil SOH"          val={Math.round(row["Fossil SOH"] || 0)} />
              <KV label="Required Inventory"  val={Math.round(row["Required Inventory"] || 0)} accent />
              <KV label="Replenishment Qty"   val={Math.round(row["Replenishment Qty"] || 0)} danger={(row["Replenishment Qty"] || 0) > 0} />
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
