/*
   PO Creation V2
   ==============
   Brand Manager takes the send recommendations (from Replenishment or
   FC Allocation), adjusts quantities, picks a Selling Account, and
   clicks Create Internal PO. One Internal PO is generated per FC
   (FC Allocation source) or per SKU-group (Replenishment source),
   then forwarded to OrderPilot's /pos/ingest endpoint.

   Additive — does NOT touch the existing tabs' calc.
*/
import React, { useEffect, useMemo, useState } from "react";
import { Send, Save, PackagePlus, Loader2 } from "lucide-react";
import { cn } from "../lib/cn";
import { getFCFinal, getReplenishment } from "../api/replenishment";

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

// Fallback list — used only if /selling-accounts returns empty (e.g. env
// vars not set in the current environment). Order matches the operator's
// convention.
const FALLBACK_SELLING_ACCOUNTS = [
  { id: "NEXLEV",         name: "Nexlev" },
  { id: "VIOMI",          name: "Viomi" },
  { id: "AUDIOARRAY",     name: "Audio Array" },
  { id: "WHITEMULBERRY",  name: "White Mulberry" },
  { id: "CAMBIUMRETAIL",  name: "Cambium Retail" },
];

// Maps the selling account choice to the account key each source-API expects.
const ACCOUNT_FOR_API = {
  NEXLEV:        "NEXLEV",
  VIOMI:         "VIOMI",
  AUDIOARRAY:    "AUDIO ARRAY",
  WHITEMULBERRY: "WHITE MULBERRY",
  CAMBIUMRETAIL: "FOSSIL",   // FC Allocation & Replenishment both use "FOSSIL" for Cambium Retail
};

const COVER_OPTIONS = [2, 4, 6, 8, 10, 12];
const SOURCES = ["Replenishment", "FC Allocation"];

function KPI({ label, value, tone = "slate" }) {
  const toneCls = {
    slate:   "text-slate-900",
    indigo:  "text-indigo-700",
    amber:   "text-amber-700",
    emerald: "text-emerald-700",
    red:     "text-red-700",
  }[tone];
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div className={cn("text-xl font-bold tabular-nums mt-1", toneCls)}>{value}</div>
    </div>
  );
}

export default function PoCreationV2() {
  /* filters */
  const [replenishWeeks, setReplenishWeeks] = useState(8);
  const [channel]                       = useState("All");
  const [fromWeek, setFromWeek]         = useState(null);
  const [toWeek,   setToWeek]           = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);
  const [source, setSource]             = useState("Replenishment");  // NEW

  /* selling account (drives the grid data account too, now that
     Brand-source is removed) */
  const [sellingAccounts,   setSellingAccounts]   = useState(FALLBACK_SELLING_ACCOUNTS);
  const [sellingAccountId,  setSellingAccountId]  = useState("NEXLEV");

  /* grid data */
  const [rows,    setRows]    = useState([]);
  const [loading, setLoading] = useState(true);

  /* per-row user overrides (checkbox + Send Qty edits) */
  const [included,  setIncluded]  = useState({});
  const [sendQty,   setSendQty]   = useState({});

  const [viewMode, setViewMode]   = useState("all");

  /* submission state */
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState(null);

  /* Row key differs by source (FC Allocation is per-(SKU,FC); Replenishment
     is per-SKU). */
  const rowKey = r => source === "FC Allocation"
    ? `${r.sku}||${r.fulfillment_center}`
    : `${r.sku}`;

  /* fetch grid data — refetch when source, account, cover, or week range change */
  useEffect(() => {
    setLoading(true);
    const account = ACCOUNT_FOR_API[sellingAccountId] || "NEXLEV";
    const promise = source === "FC Allocation"
      ? getFCFinal(replenishWeeks, channel, account, 12, fromWeek, toWeek)
      : getReplenishment(12, replenishWeeks, account);

    promise
      .then(json => {
        const data = Array.isArray(json?.data) ? json.data : (Array.isArray(json) ? json : []);
        if (json?.available_weeks) setAvailableWeeks(json.available_weeks);
        const inc = {}, sq = {};
        data.forEach(r => {
          const k = source === "FC Allocation"
            ? `${r.sku}||${r.fulfillment_center}`
            : `${r.sku}`;
          const rec = source === "FC Allocation"
            ? Number(r.send_qty || 0)
            : Number(r.replenishment_qty || r.recommended_qty || 0);
          inc[k] = rec > 0;
          sq[k]  = rec;
        });
        setIncluded(inc);
        setSendQty(sq);
        setRows(data);
      })
      .catch(err => { console.error(`${source} data load failed`, err); setRows([]); })
      .finally(() => setLoading(false));
  }, [sellingAccountId, replenishWeeks, channel, fromWeek, toWeek, source]);

  /* fetch selling accounts once — fall back to hardcoded list if empty/error */
  useEffect(() => {
    fetch(`${BASE}/selling-accounts`)
      .then(r => r.json())
      .then(j => {
        const acs = Array.isArray(j?.data) ? j.data : [];
        if (acs.length > 0) {
          setSellingAccounts(acs);
          if (!sellingAccountId) setSellingAccountId(acs[0].id);
        }
      })
      .catch(err => console.error("selling-accounts load failed, using fallback", err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* Recommended qty depends on source. Same field the source tab treats as
     the "final recommended quantity". */
  const rowRec = r => source === "FC Allocation"
    ? Number(r.send_qty || 0)
    : Number(r.replenishment_qty || 0);

  /* derived */
  const rowsInPo = useMemo(
    () => rows.filter(r => included[rowKey(r)] && Number(sendQty[rowKey(r)] || 0) > 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows, included, sendQty, source]
  );
  const displayedRows = viewMode === "in-po" ? rowsInPo : rows;

  const kpis = useMemo(() => {
    const totalUnits = rowsInPo.reduce((a, r) => a + Number(sendQty[rowKey(r)] || 0), 0);
    const skus = new Set(rowsInPo.map(r => r.sku)).size;
    const fcs  = source === "FC Allocation"
      ? new Set(rowsInPo.map(r => r.fulfillment_center)).size
      : 1;
    let overrides = 0;
    rowsInPo.forEach(r => {
      const q = Number(sendQty[rowKey(r)] || 0);
      const rec = rowRec(r);
      if (q !== rec) overrides++;
    });
    return { totalUnits, skus, fcs, overrides };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rowsInPo, sendQty, source]);

  /* handlers */
  function toggleAll(next) {
    const inc = { ...included };
    rows.forEach(r => { inc[rowKey(r)] = next; });
    setIncluded(inc);
  }
  function toggleRow(r) {
    setIncluded(p => ({ ...p, [rowKey(r)]: !p[rowKey(r)] }));
  }
  function setQty(r, val) {
    const n = val === "" ? "" : Math.max(0, Math.floor(Number(val) || 0));
    setSendQty(p => ({ ...p, [rowKey(r)]: n }));
  }

  async function submit(isDraft = false) {
    if (!sellingAccountId) { alert("Pick a Selling Account first"); return; }
    if (rowsInPo.length === 0) { alert("No lines included with qty > 0"); return; }

    setSubmitting(true);
    setSubmitResult(null);
    const selling = sellingAccounts.find(a => a.id === sellingAccountId)
      || { id: sellingAccountId, name: sellingAccountId };
    const account = ACCOUNT_FOR_API[sellingAccountId] || sellingAccountId;
    const lines = rowsInPo.map(r => {
      const req = Number(sendQty[rowKey(r)] || 0);
      const rec = rowRec(r);
      return {
        sku: r.sku || r.SKU,
        asin: r.asin || r.ASIN || "",
        model: r.model || r.Model || "",
        ship_to_fc: source === "FC Allocation" ? r.fulfillment_center : "WAREHOUSE",
        recommended_qty: rec,
        quantity_requested: req,
        delta_vs_rec: req - rec,
      };
    });

    const body = {
      selling_account: selling,
      brand: account,
      source,
      week_range: (fromWeek && toWeek) ? `Wk${fromWeek}-Wk${toWeek}` : `${replenishWeeks}wk cover`,
      cover: replenishWeeks,
      created_by: localStorage.getItem("bmName") || "",
      lines,
    };
    const url = isDraft ? `${BASE}/internal-po/draft` : `${BASE}/internal-po`;
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      setSubmitResult(j);
    } catch (e) {
      setSubmitResult({ status: "error", error: String(e) });
    } finally {
      setSubmitting(false);
    }
  }

  /* Full column mirrors of the Replenishment / FC Allocation tabs, with
     3 PO-Creation-specific extras injected:
       - "include"  (checkbox)  at position 0
       - "sendqty"  (editable)  right after the Recommended column
       - "delta"    (Δ vs Rec)  right after sendqty                                        */
  const cols = useMemo(() => {
    if (source === "FC Allocation") {
      return [
        { id: "include",           header: "",                w: 40 },
        { id: "model",             field: "model",             header: "Model",           w: 140 },
        { id: "sku",               field: "sku",               header: "SKU",             w: 110, mono: true },
        { id: "fulfillment_center",field: "fulfillment_center",header: "FC",              w: 80, mono: true },
        { id: "asin",              field: "asin",              header: "ASIN",            w: 105, mono: true },
        { id: "weekly_velocity",   field: "weekly_velocity",   header: "Avg/Wk",          w: 80, numeric: true },
        { id: "window_velocity",   field: "window_velocity",   header: "Sel Wk",          w: 75, numeric: true },
        { id: "last_2_velocity",   field: "last_2_velocity",   header: "2wk",             w: 65, numeric: true },
        { id: "velocity_basis",    field: "velocity_basis",    header: "Basis",           w: 70 },
        { id: "total_units_sold",  fn: r => (r.velocity_basis === "2wk" ? (r.units_last_14d || 0) : (r.total_units_sold || 0)),
                                                               header: "Total sold qty", w: 110, numeric: true },
        { id: "fc_inventory",      field: "fc_inventory",      header: "FC SOH",          w: 80, numeric: true },
        { id: "ampm_inventory",    field: "ampm_inventory",    header: "Mother WH",       w: 100, numeric: true },
        { id: "b2b_inventory",     field: "b2b_inventory",     header: "B2B",             w: 65, numeric: true },
        { id: "inbound_to_fc",     field: "inbound_to_fc",     header: "Inbound",         w: 85, numeric: true },
        { id: "target_cover_units",field: "target_cover_units",header: "Target",          w: 80, numeric: true },
        { id: "expected_units",    field: "expected_units",    header: "Required",        w: 90, numeric: true },
        { id: "send_qty",          field: "send_qty",          header: "Recommended",     w: 100, numeric: true, bold: true },
        { id: "sendqty",           header: "Send Qty",         w: 110, numeric: true, editable: true },
        { id: "delta",             header: "Δ vs Rec",         w: 90, numeric: true },
        { id: "fill_pct",          fn: r => r.fill_pct != null ? `${Number(r.fill_pct).toFixed(0)}%` : "—",
                                                               header: "Fill %",         w: 75, numeric: true },
        { id: "velocity_flag",     field: "velocity_flag",     header: "Vel Flag",        w: 95 },
        { id: "buffer_note",       field: "buffer_note",       header: "Buffer",          w: 120 },
        { id: "master_carton",     field: "master_carton",     header: "MC",              w: 55 },
        { id: "hazmat_type",       field: "hazmat_type",       header: "Hazmat",          w: 90 },
      ];
    }
    // Replenishment source — full ReplenishmentV2 mirror
    return [
      { id: "include",           header: "",                w: 40 },
      { id: "model",             field: "model",             header: "Model",           w: 130 },
      { id: "sku",               field: "sku",               header: "SKU",             w: 95, mono: true },
      { id: "asin",              field: "asin",              header: "ASIN",            w: 100, mono: true },
      { id: "sales_velocity",    field: "sales_velocity",    header: "Avg/Wk",          w: 75, numeric: true },
      { id: "window_velocity",   field: "window_velocity",   header: "Sel Wk",          w: 70, numeric: true },
      { id: "last_2_velocity",   field: "last_2_velocity",   header: "2wk",             w: 60, numeric: true },
      { id: "velocity_basis",    field: "velocity_basis",    header: "Basis",           w: 70 },
      { id: "total_units_sold",  fn: r => (r.velocity_basis === "2wk" ? (r.units_last_2w || 0) : (r.total_units_sold || 0)),
                                                             header: "Total sold qty", w: 110, numeric: true },
      { id: "inbound_inventory", field: "inbound_inventory", header: "Inbound",         w: 75, numeric: true },
      { id: "real_am_inv_available", field: "real_am_inv_available", header: "Real AM Inv", w: 95, numeric: true },
      { id: "ampm_inventory",    field: "ampm_inventory",    header: "Mother WH",       w: 90, numeric: true },
      { id: "b2b_inventory",     field: "b2b_inventory",     header: "B2B",             w: 60, numeric: true },
      { id: "required_units",    field: "required_units",    header: "Req",             w: 65, numeric: true },
      { id: "warehouse_shortfall", field: "warehouse_shortfall", header: "Shortfall",   w: 85, numeric: true },
      { id: "replenishment_qty", field: "replenishment_qty", header: "Replen Qty",      w: 95, numeric: true, bold: true },
      { id: "sendqty",           header: "Send Qty",         w: 110, numeric: true, editable: true },
      { id: "delta",             header: "Δ vs Rec",         w: 90, numeric: true },
      { id: "buffer_note",       field: "buffer_note",       header: "Buffer",          w: 100 },
      { id: "oos_weeks_3m",      field: "oos_weeks_3m",      header: "OOS 3m",          w: 70, numeric: true },
      { id: "thin_weeks_3m",     field: "thin_weeks_3m",     header: "Thin 3m",         w: 70, numeric: true },
      { id: "lost_units_3m",     field: "lost_units_3m",     header: "Lost Est",        w: 80, numeric: true },
      { id: "momentum_flag",     field: "momentum_flag",     header: "Momentum",        w: 95 },
      { id: "recommended_qty",   field: "recommended_qty",   header: "Rec Qty",         w: 80, numeric: true },
      { id: "cartons_needed",    field: "cartons_needed",    header: "Cartons",         w: 80, numeric: true },
      { id: "ixd_type",          field: "ixd_type",          header: "IXD",             w: 65 },
      { id: "hazmat_type",       field: "hazmat_type",       header: "Hazmat",          w: 90 },
      { id: "master_carton",     field: "master_carton",     header: "MC",              w: 55 },
    ];
  }, [source]);

  return (
    <div className="px-6 py-5 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-slate-900 inline-flex items-center gap-2">
          <PackagePlus className="w-5 h-5 text-indigo-600" />
          PO Creation
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Adjust send recommendations and dispatch Internal POs to OrderPilot.
          One PO per FC (FC Allocation source) or one per selection (Replenishment source).
        </p>
      </div>

      {/* Filters row */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-3 mb-3">
        <div className="grid grid-cols-12 gap-3 items-end">
          {/* Selling Account */}
          <div className="col-span-3">
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Selling Account</label>
            <select value={sellingAccountId} onChange={e => setSellingAccountId(e.target.value)}
              className="w-full px-2 py-1.5 text-sm rounded-md border border-indigo-200 bg-indigo-50 font-semibold">
              {sellingAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>

          {/* Past Sales range */}
          <div className="col-span-3">
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Past Sales (Selected week)</label>
            <div className="grid grid-cols-2 gap-1.5">
              <select value={fromWeek ?? ""} onChange={e => setFromWeek(Number(e.target.value))}
                className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                disabled={!availableWeeks.length}>
                {availableWeeks.length === 0
                  ? <option value="">—</option>
                  : availableWeeks.map(w => <option key={`f${w}`} value={w}>From Wk {w}</option>)}
              </select>
              <select value={toWeek ?? ""} onChange={e => setToWeek(Number(e.target.value))}
                className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                disabled={!availableWeeks.length}>
                {availableWeeks.length === 0
                  ? <option value="">—</option>
                  : availableWeeks.map(w => <option key={`t${w}`} value={w}>To Wk {w}</option>)}
              </select>
            </div>
          </div>

          {/* NEW: Source dropdown, no title, sits to the LEFT of Inventory Cover */}
          <div className="col-span-2">
            <div className="h-4 mb-1" />
            <select value={source} onChange={e => setSource(e.target.value)}
              className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white font-semibold">
              {SOURCES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          {/* Inventory Cover */}
          <div className="col-span-1">
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Inventory Cover</label>
            <select value={replenishWeeks} onChange={e => setReplenishWeeks(Number(e.target.value))}
              className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
              {COVER_OPTIONS.map(n => <option key={n}>{n}</option>)}
            </select>
          </div>

          {/* View toggle */}
          <div className="col-span-3 flex items-end justify-end gap-2">
            <div className="inline-flex rounded-md border border-slate-200 bg-white">
              <button onClick={() => setViewMode("all")}
                className={cn("px-3 py-1.5 text-xs font-semibold",
                  viewMode === "all" ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100")}>All SKUs</button>
              <button onClick={() => setViewMode("in-po")}
                className={cn("px-3 py-1.5 text-xs font-semibold",
                  viewMode === "in-po" ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100")}>In this PO</button>
            </div>
          </div>
        </div>
      </div>

      {/* KPI band */}
      <div className="grid grid-cols-4 gap-3 mb-3">
        <KPI label="Total units in PO" value={kpis.totalUnits.toLocaleString()} tone="indigo" />
        <KPI label="# SKUs" value={kpis.skus} />
        <KPI label={source === "FC Allocation" ? "# FCs (POs)" : "# POs"} value={kpis.fcs} />
        <KPI label="# Overrides" value={kpis.overrides} tone={kpis.overrides ? "amber" : "slate"} />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between mb-2">
        <label className="text-[12px] text-slate-600 inline-flex items-center gap-2">
          <input type="checkbox"
            checked={rows.length > 0 && rows.every(r => included[rowKey(r)])}
            onChange={e => toggleAll(e.target.checked)} />
          Select all in view
        </label>
        <div className="flex items-center gap-2">
          <button onClick={() => submit(true)} disabled={submitting}
            className="px-3 py-1.5 rounded-md border border-slate-200 bg-white text-slate-700 text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5">
            <Save className="w-4 h-4" /> Save draft
          </button>
          <button onClick={() => submit(false)} disabled={submitting || !sellingAccountId || rowsInPo.length === 0}
            className="px-4 py-1.5 rounded-md bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 inline-flex items-center gap-1.5">
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Create Internal PO
          </button>
        </div>
      </div>

      {/* Grid */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[11px] uppercase font-semibold text-slate-600 bg-slate-50">
            <tr>
              {cols.map(c => (
                <th key={c.id} style={{ width: c.w }}
                  className={cn("px-2 py-2 border-b border-slate-200",
                    c.numeric ? "text-right" : "text-left")}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-slate-700 [&_td]:px-2 [&_td]:py-1.5 [&_tr]:border-b [&_tr]:border-slate-100">
            {loading ? (
              <tr><td colSpan={cols.length} className="text-center py-8 text-slate-400">Loading…</td></tr>
            ) : displayedRows.length === 0 ? (
              <tr><td colSpan={cols.length} className="text-center py-8 text-slate-400">No rows to show</td></tr>
            ) : displayedRows.map(r => {
              const k = rowKey(r);
              const isIncluded = !!included[k];
              const q = sendQty[k] ?? "";
              const rec = rowRec(r);
              const num = Number(q || 0);
              const delta = num - rec;
              return (
                <tr key={k} className={cn(!isIncluded && "opacity-40 bg-slate-50")}>
                  {cols.map(c => {
                    /* PO-specific columns */
                    if (c.id === "include") {
                      return (
                        <td key={c.id}>
                          <input type="checkbox" checked={isIncluded} onChange={() => toggleRow(r)} />
                        </td>
                      );
                    }
                    if (c.id === "sendqty") {
                      return (
                        <td key={c.id} className="text-right">
                          <input type="number" min="0" value={q}
                            onChange={e => setQty(r, e.target.value)}
                            className="w-20 text-right px-1.5 py-1 border border-slate-200 rounded text-xs font-mono bg-amber-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/40" />
                        </td>
                      );
                    }
                    if (c.id === "delta") {
                      return (
                        <td key={c.id} className={cn("text-right tabular-nums font-semibold",
                          delta > 0 ? "text-emerald-700" : delta < 0 ? "text-red-700" : "text-slate-400")}>
                          {delta > 0 ? `+${delta}` : delta}
                        </td>
                      );
                    }
                    /* Mirror columns from the source tab */
                    const raw = c.fn ? c.fn(r) : r[c.field];
                    const value = raw == null || raw === "" ? "—" : raw;
                    return (
                      <td key={c.id}
                        className={cn(
                          c.numeric ? "text-right tabular-nums" : "text-left",
                          c.mono   && "font-mono text-xs",
                          c.bold   && "font-semibold",
                          !c.mono && c.id === "model" && "font-semibold text-slate-900",
                          !c.mono && c.id === "asin" && "text-slate-500",
                        )}>
                        {value}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Result panel */}
      {submitResult && (
        <div className={cn("mt-3 p-3 rounded-lg border text-sm",
          submitResult.status === "ok"
            ? "border-emerald-200 bg-emerald-50 text-emerald-800"
            : "border-red-200 bg-red-50 text-red-800")}>
          {submitResult.status === "ok" ? (
            <>
              <div className="font-semibold mb-1">Created {submitResult.pos?.length || 0} Internal PO(s)</div>
              <ul className="text-xs space-y-0.5">
                {(submitResult.pos || []).map(po => (
                  <li key={po.po_number}>
                    <b className="font-mono">{po.po_number}</b> · {po.ship_to_fc} · {po.line_count} lines · {po.total_qty}u ·
                    OrderPilot: <b>{po.orderpilot_status}</b>
                    {po.orderpilot_error && <span className="text-red-700 ml-1">({po.orderpilot_error})</span>}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <>
              <div className="font-semibold">Error</div>
              <div className="text-xs mt-1">{submitResult.error || JSON.stringify(submitResult)}</div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
