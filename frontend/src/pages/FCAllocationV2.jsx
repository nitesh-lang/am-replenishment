import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Search, Download, Save, ChevronDown, ChevronRight,
  Settings2, Truck, RotateCcw,
} from "lucide-react";

import { getFCFinal } from "../api/replenishment";
import { CommandPalette } from "../components/CommandPalette";
import { SavedViews } from "../components/SavedViews";
import { SOPModal, SOPButton } from "../components/SOPModal";
import { FCAllocationSOPContent } from "../components/SOPContents";
import DataFreshnessBanner from "../components/DataFreshnessBanner";
import { cn } from "../lib/cn";

/* ============================================================
   FC ALLOCATION V2 — TanStack + shadcn-style
   Preserves every existing handler:
     - getFCFinal with from_week/to_week range
     - Fossil cluster PO save + per-row inputs (fossil-save, fossil-cluster-save)
     - Fossil reset
     - Master Carton editing
============================================================ */

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

const FC_CLUSTER = {
  BLR5: "BLR", BLR7: "BLR", BLR8: "BLR",
  BOM4: "BOM", BOM5: "BOM", BOM7: "BOM", AMD2: "BOM", PNQ3: "BOM", ISK3: "BOM",
  MAA4: "TN",  CJB1: "TN",
  DEL2: "DEL", DEL4: "DEL", DEL5: "DEL", DED4: "DEL", LKO1: "DEL",
  HYD3: "TEL", HYD8: "TEL",
  CCX1: "WB",
};

export default function FCAllocationV2() {
  /* ─────────── state ─────────── */
  const [replenishWeeks, setReplenishWeeks] = useState(8);
  const [availableWeeks, setAvailableWeeks] = useState([]);
  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek,   setToWeek]   = useState(null);
  const [channel, setChannel]   = useState("All");
  const [account, setAccount]   = useState("Nexlev");

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [view, setView] = useState("all");
  const [sorting, setSorting] = useState([]);
  const [expandedKey, setExpandedKey] = useState(null);
  const [density, setDensity] = useState("cozy");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 100;
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [selectedStatuses,   setSelectedStatuses]   = useState([]);

  /* Fossil-specific */
  const [fossilEdits, setFossilEdits] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  /* Range-select */
  const [selRange, setSelRange] = useState(null);
  const draggingRef = useRef(null);

  /* SOP modal */
  const [sopOpen, setSopOpen] = useState(false);

  /* ============================================================
     Reset week range when account changes so per-account defaults
     (e.g. Fossil = last 12 weeks) can re-apply. Without this, whatever
     range the previous account set stays sticky and the Fossil default
     never fires.
  ============================================================ */
  useEffect(() => {
    setFromWeek(null);
    setToWeek(null);
    setAvailableWeeks([]);
  }, [account]);

  /* ============================================================
     LOAD
  ============================================================ */
  useEffect(() => {
    setLoading(true);
    setFossilEdits({});
    setExpandedKey(null);

    const fallbackWindow = (fromWeek != null && toWeek != null)
      ? Math.abs(Number(toWeek) - Number(fromWeek)) + 1
      : (availableWeeks.length || 12);

    getFCFinal(replenishWeeks, channel, account, fallbackWindow, fromWeek, toWeek)
      .then(res => {
        const list = Array.isArray(res) ? res : (res?.data ?? []);
        let availList = null;
        if (res && typeof res === "object") {
          if (Array.isArray(res.available_weeks)) {
            availList = res.available_weeks.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
          } else if (typeof res.available_weeks === "number") {
            availList = Array.from({ length: res.available_weeks }, (_, i) => i + 1);
          }
        }
        if (availList && availList.length) {
          setAvailableWeeks(availList);
          const lo = availList[0];
          const hi = availList[availList.length - 1];
          // Fossil defaults to the LAST 12 available weeks (operator asked
          // for a rolling recent window, not the full history that was
          // defaulting to 16+ weeks). Other accounts keep the full range.
          const defaultLo = account === "Fossil"
            ? (availList.find(w => w >= hi - 11) ?? lo)
            : lo;
          if (fromWeek == null || !availList.includes(Number(fromWeek))) setFromWeek(defaultLo);
          if (toWeek   == null || !availList.includes(Number(toWeek)))   setToWeek(hi);
        }
        setRows(list);

        // Preload Fossil edits from API values
        if (account === "Fossil" && list.length > 0) {
          const pre = {};
          list.forEach(row => {
            const key = `${row.sku}|${row.fulfillment_center}`;
            pre[key] = {
              send_qty: row.send_qty ?? 0,
              remarks:  row.remarks ?? "",
            };
            const cl = FC_CLUSTER[row.fulfillment_center?.toUpperCase()] || "-";
            if (cl !== "-") {
              const ck = `${row.sku}|${cl}`;
              if (!pre[ck]?.cluster_po) {
                pre[ck] = { ...pre[ck], cluster_po: row.cluster_po ?? 0 };
              }
            }
          });
          setFossilEdits(pre);
        }
      })
      .finally(() => setLoading(false));
  }, [replenishWeeks, channel, account, fromWeek, toWeek]);

  /* ============================================================
     FOSSIL SAVE
  ============================================================ */
  async function saveFossilInputs() {
    if (saving) return;
    setSaving(true);
    setSaveMsg("");
    try {
      const rowPayload = sortedRows().map(r => {
        const key = `${r.sku}|${r.fulfillment_center}`;
        const e = fossilEdits[key] || {};
        return {
          sku: r.sku,
          fulfillment_center: r.fulfillment_center,
          po_requirement: parseInt(e.send_qty ?? r.send_qty ?? 0) || 0,
          remarks: e.remarks ?? r.remarks ?? "",
        };
      });
      await fetch(`${BASE}/fc-final-allocation/fossil-save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(rowPayload),
      });

      const clusterMap = {};
      sortedRows().forEach(r => {
        const cl = FC_CLUSTER[r.fulfillment_center?.toUpperCase()] || "-";
        if (cl === "-") return;
        const ck = `${r.sku}|${cl}`;
        if (!clusterMap[ck]) {
          const val = fossilEdits[ck]?.cluster_po ?? r.cluster_po ?? 0;
          clusterMap[ck] = { sku: r.sku, cluster: cl, cluster_po: parseInt(val) || 0 };
        }
      });
      const cp = Object.values(clusterMap);
      if (cp.length > 0) {
        await fetch(`${BASE}/fc-final-allocation/fossil-cluster-save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(cp),
        });
      }
      setSaveMsg("Saved");
    } catch (e) {
      setSaveMsg("Save failed");
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(""), 4000);
    }
  }

  async function resetFossilInputs() {
    if (!confirm("Reset all Fossil send_qty + cluster_po overrides?")) return;
    setSaving(true);
    try {
      await fetch(`${BASE}/fc-final-allocation/fossil-reset`, { method: "POST" });
      // Reload
      const fallbackWindow = (fromWeek != null && toWeek != null)
        ? Math.abs(Number(toWeek) - Number(fromWeek)) + 1
        : (availableWeeks.length || 12);
      const res = await getFCFinal(replenishWeeks, channel, account, fallbackWindow, fromWeek, toWeek);
      setRows(Array.isArray(res) ? res : (res?.data ?? []));
      setSaveMsg("Reset");
    } catch {
      setSaveMsg("Reset failed");
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(""), 4000);
    }
  }

  function getFossilField(row, field) {
    const k = `${row.sku}|${row.fulfillment_center}`;
    return fossilEdits[k]?.[field] ?? row[field];
  }
  function setFossilField(row, field, val) {
    const k = `${row.sku}|${row.fulfillment_center}`;
    setFossilEdits(p => ({ ...p, [k]: { ...p[k], [field]: val } }));
  }

  /* ============================================================
     DERIVED
  ============================================================ */
  useEffect(() => { setPage(1); }, [search, view, account, channel, fromWeek, toWeek, selectedCategories, selectedStatuses]);

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
        (r.asin  || "").toLowerCase().includes(q) ||
        (r.fulfillment_center || "").toLowerCase().includes(q)
      )) return false;
      if (selectedCategories.length > 0 && !selectedCategories.includes(r.category)) return false;
      if (selectedStatuses.length   > 0 && !selectedStatuses.includes(r.listing_status)) return false;
      if (view === "send")    return (r.send_qty || 0) > 0;
      if (view === "high")    return (r.send_qty || 0) > 500;
      if (view === "low")     return (r.send_qty || 0) > 0 && (r.send_qty || 0) < 50;
      if (view === "fill_low")return (r.fill_pct || 0) > 0 && (r.fill_pct || 0) < 50;
      if (view === "no_send") return (r.send_qty || 0) === 0;
      return true;
    });
    if (!q) return filtered;
    const score = r => {
      const m = (r.model || "").toLowerCase();
      const s = (r.sku   || "").toLowerCase();
      const a = (r.asin  || "").toLowerCase();
      const f = (r.fulfillment_center || "").toLowerCase();
      if (m === q || s === q || a === q || f === q) return 0;
      if (m.startsWith(q) || s.startsWith(q) || a.startsWith(q) || f.startsWith(q)) return 1;
      return 2;
    };
    return [...filtered].sort((x, y) => score(x) - score(y));
  }, [rows, search, view, selectedCategories, selectedStatuses]);

  const views = useMemo(() => [
    { key: "all",      label: "All",            count: rows.length },
    { key: "send",     label: "Has Send Qty",   count: rows.filter(r => (r.send_qty || 0) > 0).length },
    { key: "high",     label: "High Load",      count: rows.filter(r => (r.send_qty || 0) > 500).length, accent: "bg-red-100 text-red-700" },
    { key: "low",      label: "Low Load",       count: rows.filter(r => (r.send_qty || 0) > 0 && (r.send_qty || 0) < 50).length },
    { key: "fill_low", label: "Fill < 50%",     count: rows.filter(r => (r.fill_pct || 0) > 0 && (r.fill_pct || 0) < 50).length },
    { key: "no_send",  label: "No Send",        count: rows.filter(r => (r.send_qty || 0) === 0).length },
  ], [rows]);

  /* KPI */
  const kpis = useMemo(() => {
    const send = filteredRows.reduce((a, r) => a + (r.send_qty || 0), 0);
    const skus = new Set(filteredRows.map(r => r.sku)).size;
    const fcs  = new Set(filteredRows.map(r => r.fulfillment_center)).size;
    const fillSum = filteredRows.reduce((a, r) => a + (r.fill_pct || 0), 0);
    const fillAvg = filteredRows.length ? Math.round(fillSum / filteredRows.length) : 0;
    return { send, skus, fcs, fillAvg };
  }, [filteredRows]);

  /* ============================================================
     COLUMNS — adapt to account
  ============================================================ */
  const isFossil = account === "Fossil";

  const columns = useMemo(() => {
    const base = [
      { id: "model",            accessorKey: "model",            header: "Model",  size: 140, meta: { sticky: 1, group: "id" } },
      { id: "sku",              accessorKey: "sku",              header: "SKU",    size: 110, meta: { sticky: 2, group: "id" } },
      { id: "fulfillment_center", accessorKey: "fulfillment_center", header: "FC", size: 80, meta: { sticky: 3, group: "id" } },
    ];
    if (isFossil) {
      base.push(
        { id: "cluster",   accessorFn: r => FC_CLUSTER[r.fulfillment_center?.toUpperCase()] || r.cluster || "-",
          header: "Cluster", size: 70,  meta: { group: "id" } },
        { id: "asin",      accessorKey: "asin",      header: "ASIN",       size: 105, meta: { group: "list" } },
        { id: "assortment",accessorKey: "assortment",header: "Assortment", size: 90,  meta: { group: "list" } },
      );
    } else {
      base.push(
        { id: "asin",     accessorKey: "asin",     header: "ASIN",     size: 105, meta: { group: "list" } },
      );
    }

    base.push(
      { id: "weekly_velocity",   accessorKey: "weekly_velocity",   header: "Avg/Wk", size: 80, meta: { group: "vel", numeric: true, sortDescFirst: true } },
      { id: "window_velocity",   accessorKey: "window_velocity",   header: "Sel Wk", size: 75, meta: { group: "vel", numeric: true, sortDescFirst: true } },
      { id: "last_2_velocity",   accessorKey: "last_2_velocity",   header: "2wk",    size: 65, meta: { group: "vel", numeric: true, sortDescFirst: true } },
      { id: "velocity_basis",    accessorKey: "velocity_basis",    header: "Basis",  size: 75, meta: { group: "vel" } },
      { id: "total_units_sold",  accessorKey: "total_units_sold",  header: "Total sold qty",  size: 105, meta: { group: "vel", numeric: true, sortDescFirst: true } },
    );

    base.push(
      { id: "fc_inventory",   accessorKey: "fc_inventory",   header: "FC SOH",    size: 80, meta: { group: "inv", numeric: true, sortDescFirst: true } },
      { id: "ampm_inventory", accessorKey: "ampm_inventory", header: isFossil ? "Fossil SOH" : "Mother WH", size: 100, meta: { group: "inv", numeric: true, sortDescFirst: true } },
      { id: "b2b_inventory",  accessorKey: "b2b_inventory",  header: "B2B",       size: 65, meta: { group: "inv", numeric: true, sortDescFirst: true } },
      { id: "inbound_to_fc",  accessorKey: "inbound_to_fc",  header: "Inbound",   size: 85, meta: { group: "inv", numeric: true, sortDescFirst: true } },
    );

    if (isFossil) {
      base.push(
        { id: "in_transit_qty", accessorKey: "in_transit_qty", header: "In-Transit", size: 85, meta: { group: "inv", numeric: true, sortDescFirst: true } },
        { id: "open_po_qty",    accessorKey: "open_po_qty",    header: "Open PO",    size: 75, meta: { group: "inv", numeric: true, sortDescFirst: true } },
      );
    } else {
      base.push(
        { id: "target_cover_units", accessorKey: "target_cover_units", header: "Target", size: 80, meta: { group: "plan", numeric: true, sortDescFirst: true } },
        { id: "expected_units",     accessorKey: "expected_units",     header: "Required", size: 90, meta: { group: "plan", numeric: true, sortDescFirst: true } },
      );
    }

    base.push(
      { id: "send_qty", accessorKey: "send_qty", header: isFossil ? "PO Req" : "To Send", size: 90, meta: { group: "plan", numeric: true, sortDescFirst: true, editable: isFossil } },
      { id: "buffer_note", accessorKey: "buffer_note", header: "Buffer", size: 120, meta: { group: "plan" } },
    );

    if (isFossil) {
      base.push(
        { id: "cluster_po",         accessorKey: "cluster_po",         header: "Cluster PO", size: 95, meta: { group: "plan", numeric: true, editable: true } },
        { id: "cluster_in_transit", accessorKey: "cluster_in_transit", header: "Clstr IT",   size: 85, meta: { group: "plan", numeric: true } },
      );
    } else {
      base.push(
        { id: "fill_pct",      accessorKey: "fill_pct",      header: "Fill %",        size: 75, meta: { group: "plan", numeric: true, sortDescFirst: true } },
        { id: "velocity_flag", accessorKey: "velocity_flag", header: "Vel Flag",      size: 95, meta: { group: "plan" } },
      );
    }

    base.push(
      { id: "master_carton", accessorKey: "master_carton", header: "MC", size: 55, meta: { group: "log" } },
    );

    if (isFossil) {
      base.push({ id: "remarks", accessorKey: "remarks", header: "Remarks", size: 140, meta: { group: "log", editable: true } });
    } else {
      base.push({ id: "hazmat_type", accessorKey: "hazmat_type", header: "Hazmat", size: 90, meta: { group: "log" } });
    }

    return base;
  }, [isFossil]);

  const table = useReactTable({
    data: filteredRows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  function sortedRows() {
    return table.getSortedRowModel().rows.map(r => r.original);
  }

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

  // Fast O(1) lookup set for selected cells (was O(N) .some() per cell render)
  const selectedSet = useMemo(() => {
    const s = new Set();
    if (!selRange) return s;
    const r0 = Math.min(selRange.fromRow, selRange.toRow);
    const r1 = Math.max(selRange.fromRow, selRange.toRow);
    const c0 = Math.min(selRange.fromCol, selRange.toCol);
    const c1 = Math.max(selRange.fromCol, selRange.toCol);
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) s.add(`${r}-${c}`);
    }
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
          const colId = columns[c]?.id;
          const v = sortedTable[r]?.original?.[colId];
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
    id:   { label: "Identity",   tint: "" },
    list: { label: "Listing",    tint: "" },
    vel:  { label: "Velocity",   tint: "bg-indigo-50 text-indigo-700" },
    inv:  { label: "Inventory",  tint: "bg-slate-100" },
    plan: { label: "Plan",       tint: "bg-amber-50 text-amber-800" },
    log:  { label: "Logistics",  tint: "" },
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
    const headers = order.map(id => {
      const col = columns.find(c => c.id === id);
      return typeof col.header === "string" ? col.header : id;
    });
    const lines = [headers.join(",")];
    table.getSortedRowModel().rows.forEach(({ original: r }) => {
      const cells = order.map(id => {
        let v = isFossil && (id === "send_qty" || id === "remarks")
          ? getFossilField(r, id === "send_qty" ? "send_qty" : "remarks")
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
    a.download = `fc_allocation_${account.toLowerCase().replace(/\s+/g, "_")}_${view}.csv`;
    a.click();
  }

  /* ============================================================
     PALETTE PICK
  ============================================================ */
  function onPaletteSelect(item) {
    if (item.type === "sku") {
      const key = `${item.payload.sku}|${item.payload.fulfillment_center}`;
      setExpandedKey(key);
      requestAnimationFrame(() => {
        const el = document.querySelector(`[data-row-key="${key}"]`);
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
        <DataFreshnessBanner module="fc-allocation" />

        {/* Header */}
        <div className="flex items-end justify-between mb-4">
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-500 font-medium">Account</div>
            <h1 className="text-2xl font-semibold mt-0.5 tracking-tight inline-flex items-center gap-1">
              <select
                value={account}
                onChange={e => setAccount(e.target.value)}
                className="bg-transparent border-none -ml-1 pl-1 pr-6 py-0 text-2xl font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-500/40 rounded"
              >
                <option value="Nexlev">Nexlev</option>
                <option value="Viomi">Viomi</option>
                <option value="White Mulberry">White Mulberry</option>
                <option value="Audio Array">Audio Array</option>
                <option value="Fossil">Fossil</option>
              </select>
              <span className="text-slate-300 font-normal">·</span>
              <span className="text-slate-500 text-lg font-medium">FC Allocation</span>
            </h1>
          </div>
          <div className="flex items-center gap-2">
            {saveMsg && (
              <span className="text-xs text-indigo-700 mr-2">{saveMsg}</span>
            )}
            <SOPButton onClick={() => setSopOpen(true)} />
            <button onClick={exportCSV} className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            {isFossil && (
              <>
                <button
                  onClick={resetFossilInputs}
                  disabled={saving}
                  className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5"
                  title="Reset all Fossil send_qty + cluster_po overrides"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Reset
                </button>
                <button
                  onClick={saveFossilInputs}
                  disabled={saving}
                  className="px-3 py-2 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  <Save className="w-3.5 h-3.5" />
                  {saving ? "Saving…" : "Save Fossil"}
                </button>
              </>
            )}
          </div>
        </div>

        {/* KPI */}
        <div className="grid grid-cols-5 gap-3 mb-5">
          <KPICard label="Total Send Qty" value={kpis.send} hint={`across ${kpis.fcs} FCs`} />
          <KPICard label="Unique SKUs"    value={kpis.skus} hint="in this view" />
          <KPICard label="Avg Fill %"     value={`${kpis.fillAvg}%`} hint="weighted FC fill" tone={kpis.fillAvg < 50 ? "warn" : ""} />
          <KPICard label="High Load"      value={rows.filter(r => (r.send_qty || 0) > 500).length} hint="send > 500" tone="bad" />
          <KPICard label="Loaded weeks"   value={availableWeeks.length} hint="ISO weeks available" tone="brand" />
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
                  placeholder="SKU / Model / ASIN / FC…"
                />
              </div>
            </div>

            <div className="col-span-2">
              <Label>Past Sales (Selected week)</Label>
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
              <Label>Inventory Cover</Label>
              <select value={replenishWeeks} onChange={e => setReplenishWeeks(Number(e.target.value))}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                {[2, 4, 6, 8, 10, 12].map(n => <option key={n}>{n}</option>)}
              </select>
            </div>

            <div className="col-span-2">
              <Label>Channel</Label>
              <select value={channel} onChange={e => setChannel(e.target.value)}
                className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
                <option value="All">All</option>
                <option value="amazon.in">Amazon.in</option>
                <option value="Non-Amazon">D2C (MCF / Non-Amazon)</option>
              </select>
            </div>

            <div className="col-span-2">
              <Label>Status</Label>
              <div className="text-xs text-slate-500 truncate">
                {loading ? "Loading…" : `${filteredRows.length} of ${rows.length} rows`}
              </div>
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
          {(categories.length > 0 || listingStatuses.length > 0) && !isFossil && (
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
                            meta.sticky === 2 && "sticky left-[140px] z-10 bg-slate-50 shadow-[1px_0_0_#e2e8f0]",
                            meta.sticky === 3 && "sticky left-[250px] z-10 bg-slate-50 shadow-[1px_0_0_#e2e8f0]",
                            meta.group === "vel" && "bg-indigo-50/60",
                            meta.group === "plan" && "bg-amber-50/40",
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
                  const key = `${r.sku}|${r.fulfillment_center}`;
                  const isExpanded = expandedKey === key;
                  const isHigh = (r.send_qty || 0) > 500;
                  const isLow  = (r.send_qty || 0) > 0 && (r.send_qty || 0) < 50;

                  return (
                    <React.Fragment key={key}>
                      <tr
                        data-row-key={key}
                        className={cn(
                          "hover:bg-slate-50/60 cursor-pointer",
                          isHigh && "bg-red-50/40",
                          isLow  && "bg-amber-50/40",
                          isExpanded && "bg-indigo-50/30",
                        )}
                        onClick={() => setExpandedKey(isExpanded ? null : key)}
                      >
                        {trow.getVisibleCells().map((cell, ci) => {
                          const colId = cell.column.id;
                          const meta = cell.column.columnDef.meta || {};
                          const globalRowIdx = (page - 1) * PAGE_SIZE + ri;
                          const isSelected = selectedSet.has(`${globalRowIdx}-${ci}`);

                          let content;
                          if (colId === "model") {
                            content = (
                              <span className="font-semibold text-slate-900 inline-flex items-center gap-1">
                                {isExpanded
                                  ? <ChevronDown className="w-3.5 h-3.5 text-indigo-600" />
                                  : <ChevronRight className="w-3.5 h-3.5 text-slate-300" />}
                                {r.model}
                              </span>
                            );
                          } else if (colId === "sku") {
                            content = <span className="font-mono text-xs text-slate-700">{r.sku}</span>;
                          } else if (colId === "fulfillment_center") {
                            content = <span className="font-mono text-xs text-slate-700 inline-flex items-center gap-1"><Truck className="w-3 h-3 text-slate-400" />{r.fulfillment_center}</span>;
                          } else if (colId === "cluster") {
                            const cl = FC_CLUSTER[r.fulfillment_center?.toUpperCase()] || r.cluster || "-";
                            content = <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">{cl}</span>;
                          } else if (colId === "asin") {
                            content = <span className="font-mono text-xs text-slate-500">{r.asin || "—"}</span>;
                          } else if (colId === "inbound_to_fc") {
                            const v = r.inbound_to_fc || 0;
                            content = v > 0
                              ? <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold rounded bg-sky-50 text-sky-700 tabular-nums" title="Units shipped to this FC, not yet received">{v}</span>
                              : <span className="text-slate-300 text-xs">—</span>;
                          } else if (colId === "send_qty") {
                            if (isFossil && meta.editable) {
                              content = (
                                <input
                                  type="number"
                                  value={getFossilField(r, "send_qty") ?? 0}
                                  onClick={e => e.stopPropagation()}
                                  onChange={e => setFossilField(r, "send_qty", e.target.value)}
                                  className="w-16 text-right px-1.5 py-1 border border-slate-200 rounded text-xs font-mono"
                                />
                              );
                            } else {
                              content = <span className="font-bold tabular-nums text-slate-900">{r.send_qty}</span>;
                            }
                          } else if (colId === "cluster_po" && isFossil) {
                            if (r.cluster_po == null) {
                              content = <span className="text-slate-300 text-xs">—</span>;
                            } else {
                              const cl = FC_CLUSTER[r.fulfillment_center?.toUpperCase()] || "-";
                              const ck = `${r.sku}|${cl}`;
                              content = (
                                <input
                                  type="number"
                                  value={fossilEdits[ck]?.cluster_po ?? r.cluster_po ?? 0}
                                  onClick={e => e.stopPropagation()}
                                  onChange={e => setFossilEdits(p => ({ ...p, [ck]: { ...p[ck], cluster_po: e.target.value } }))}
                                  className="w-16 text-right px-1.5 py-1 border border-slate-200 rounded text-xs font-mono"
                                />
                              );
                            }
                          } else if (colId === "cluster_in_transit" && isFossil) {
                            content = r.cluster_in_transit == null
                              ? <span className="text-slate-300 text-xs">—</span>
                              : <span className="tabular-nums">{r.cluster_in_transit}</span>;
                          } else if (colId === "remarks" && isFossil) {
                            content = (
                              <input
                                type="text"
                                value={getFossilField(r, "remarks") ?? ""}
                                onClick={e => e.stopPropagation()}
                                onChange={e => setFossilField(r, "remarks", e.target.value)}
                                className="w-32 px-1.5 py-1 border border-slate-200 rounded text-xs"
                                placeholder="—"
                              />
                            );
                          } else if (colId === "fill_pct") {
                            const v = r.fill_pct || 0;
                            const tone = v >= 80 ? "text-emerald-700" : v >= 50 ? "text-slate-700" : "text-amber-700 font-semibold";
                            content = <span className={cn("tabular-nums", tone)}>{Math.round(v)}%</span>;
                          } else if (colId === "velocity_flag") {
                            const f = r.velocity_flag || "";
                            const tone = f.includes("SHORT") ? "bg-red-100 text-red-700"
                                       : f.includes("NO_SALES") ? "bg-slate-100 text-slate-500"
                                       : "bg-emerald-50 text-emerald-700";
                            content = <span className={cn("inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded", tone)}>{f || "—"}</span>;
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
                              onMouseDown={meta.numeric ? (e) => onCellMouseDown(globalRowIdx, ci, e) : undefined}
                              onMouseEnter={() => onCellMouseEnter(globalRowIdx, ci)}
                              className={cn(
                                meta.numeric ? "text-right" : "text-left",
                                meta.sticky === 1 && "sticky left-0 bg-white z-[1] shadow-[1px_0_0_#e2e8f0]",
                                meta.sticky === 2 && "sticky left-[140px] bg-white z-[1] shadow-[1px_0_0_#e2e8f0]",
                                meta.sticky === 3 && "sticky left-[250px] bg-white z-[1] shadow-[1px_0_0_#e2e8f0]",
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
                        <FCDetailRow row={r} colSpan={columns.length} allRows={rows} isFossil={isFossil} />
                      )}
                    </React.Fragment>
                  );
                })}

                {filteredRows.length === 0 && !loading && (
                  <tr>
                    <td colSpan={columns.length} className="text-center py-10 text-slate-400 text-sm">
                      No FC rows match the current view + search.
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
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40"
                  >‹</button>
                  <span className="px-2 font-semibold text-slate-900 tabular-nums">
                    Page {page} / {Math.ceil(filteredRows.length / PAGE_SIZE)}
                  </span>
                  <button
                    onClick={() => setPage(p => Math.min(Math.ceil(filteredRows.length / PAGE_SIZE), p + 1))}
                    disabled={page >= Math.ceil(filteredRows.length / PAGE_SIZE)}
                    className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40"
                  >›</button>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-5 text-xs text-slate-500 px-1">
          <Legend swatch="bg-red-100"    label="High load (send > 500)" />
          <Legend swatch="bg-amber-100"  label="Low load (0 < send < 50)" />
          <Legend swatch="bg-indigo-100" label="Range-selected" />
        </div>
      </div>

      <SOPModal open={sopOpen} onClose={() => setSopOpen(false)} title="FC Allocation">
        <FCAllocationSOPContent />
      </SOPModal>

      <CommandPalette
        rows={rows}
        views={views.map(v => ({ key: v.key, label: v.label, hint: `${v.count} rows` }))}
        onPick={onPaletteSelect}
      />
    </div>
  );
}

/* ============================================================
   DETAIL ROW — show all FCs for the same SKU + cluster summary
============================================================ */

function FCDetailRow({ row, colSpan, allRows, isFossil }) {
  const skuRows = allRows.filter(r => r.sku === row.sku);
  const totalSend = skuRows.reduce((a, r) => a + (r.send_qty || 0), 0);
  const totalSoh  = skuRows.reduce((a, r) => a + (r.fc_inventory || 0), 0);
  const totalReq  = skuRows.reduce((a, r) => a + (r.expected_units || r.target_cover_units || 0), 0);

  return (
    <tr className="bg-indigo-50/20">
      <td colSpan={colSpan} className="!p-0">
        <div className="px-6 py-5 bg-gradient-to-b from-indigo-50/40 to-white border-l-4 border-indigo-500 grid grid-cols-12 gap-5">

          {/* All FCs for this SKU */}
          <div className="col-span-7">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
              All FCs for {row.model} · {row.sku}
            </div>
            <div className="bg-white rounded-md border border-slate-200 overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-2 py-1.5 text-left">FC</th>
                    <th className="px-2 py-1.5 text-right">SOH</th>
                    <th className="px-2 py-1.5 text-right">Inbound</th>
                    <th className="px-2 py-1.5 text-right">Velocity</th>
                    {isFossil && <th className="px-2 py-1.5 text-right">In-Transit</th>}
                    {isFossil && <th className="px-2 py-1.5 text-right">Open PO</th>}
                    <th className="px-2 py-1.5 text-right">Send</th>
                    {!isFossil && <th className="px-2 py-1.5 text-right">Fill%</th>}
                  </tr>
                </thead>
                <tbody>
                  {skuRows.map(r => (
                    <tr key={r.fulfillment_center} className={r.fulfillment_center === row.fulfillment_center ? "bg-indigo-50/40 font-semibold" : ""}>
                      <td className="px-2 py-1.5 font-mono">{r.fulfillment_center}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{r.fc_inventory ?? 0}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {(r.inbound_to_fc ?? 0) > 0
                          ? <span className="text-sky-700 font-semibold">{r.inbound_to_fc}</span>
                          : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{r.weekly_velocity ?? 0}</td>
                      {isFossil && <td className="px-2 py-1.5 text-right tabular-nums">{r.in_transit_qty ?? 0}</td>}
                      {isFossil && <td className="px-2 py-1.5 text-right tabular-nums">{r.open_po_qty ?? 0}</td>}
                      <td className="px-2 py-1.5 text-right tabular-nums font-semibold">{r.send_qty ?? 0}</td>
                      {!isFossil && <td className="px-2 py-1.5 text-right tabular-nums">{Math.round(r.fill_pct || 0)}%</td>}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-slate-50 border-t border-slate-200 text-[11px] font-semibold">
                    <td className="px-2 py-1.5">Total</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{totalSoh}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-sky-700">{skuRows.reduce((a, r) => a + (r.inbound_to_fc || 0), 0) || "—"}</td>
                    <td className="px-2 py-1.5 text-right text-slate-400">—</td>
                    {isFossil && <td className="px-2 py-1.5 text-right text-slate-400">—</td>}
                    {isFossil && <td className="px-2 py-1.5 text-right text-slate-400">—</td>}
                    <td className="px-2 py-1.5 text-right tabular-nums">{totalSend}</td>
                    {!isFossil && <td className="px-2 py-1.5 text-right text-slate-400">—</td>}
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Inventory snapshot */}
          <div className="col-span-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">This FC</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <KV label="FC SOH"          val={row.fc_inventory} />
              <KV label={isFossil ? "Fossil SOH" : "Mother WH"} val={row.ampm_inventory} accent />
              <KV label="B2B"             val={row.b2b_inventory} />
              <KV label="Inbound"         val={row.inbound_to_fc || 0} />
              {isFossil && <KV label="In-Transit"  val={row.in_transit_qty} />}
              {isFossil && <KV label="Open PO"     val={row.open_po_qty} />}
              <KV label="Send Qty"        val={row.send_qty} />
            </div>
          </div>

          {/* Totals card */}
          <div className="col-span-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Across FCs</div>
            <div className="bg-white rounded-md border border-slate-200 p-3 space-y-2 text-xs">
              <KV label="Total SOH"    val={totalSoh} />
              <KV label="Total Req"    val={Math.round(totalReq)} />
              <KV label="Total Send"   val={totalSend} accent />
              <KV label="FCs"          val={skuRows.length} />
            </div>
          </div>

        </div>
      </td>
    </tr>
  );
}

function KV({ label, val, accent }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={cn("font-mono tabular-nums font-semibold", accent ? "text-indigo-700" : "text-slate-900")}>{val ?? 0}</span>
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
