/*
   PO Creation V2
   ==============
   Brand Manager takes the FC Allocation send recommendations, adjusts
   quantities, picks a Selling Account, and clicks Create Internal PO.
   One Internal PO is generated per FC, then forwarded to OrderPilot's
   /pos/ingest endpoint.

   Additive to FC Allocation — does NOT touch the existing tab's calc.
*/
import React, { useEffect, useMemo, useState } from "react";
import { Send, Save, PackagePlus, Loader2 } from "lucide-react";
import { cn } from "../lib/cn";
import { getFCFinal } from "../api/replenishment";

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

const ACCOUNTS = ["NEXLEV", "VIOMI", "AUDIO ARRAY", "WHITE MULBERRY", "FOSSIL"];
const COVER_OPTIONS = [2, 4, 6, 8, 10, 12];

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
  /* filters — mirror FC Allocation */
  const [account, setAccount]           = useState("NEXLEV");
  const [replenishWeeks, setReplenishWeeks] = useState(8);
  const [channel]                       = useState("All");
  const [fromWeek, setFromWeek]         = useState(null);
  const [toWeek,   setToWeek]           = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);

  /* selling account (asked at PO time, orthogonal to brand filter) */
  const [sellingAccounts, setSellingAccounts] = useState([]);
  const [sellingAccountId, setSellingAccountId] = useState("");

  /* grid data */
  const [rows,    setRows]    = useState([]);
  const [loading, setLoading] = useState(true);

  /* per-row user overrides (checkbox + Send Qty edits) */
  const [included,  setIncluded]  = useState({});     // { key: bool }
  const [sendQty,   setSendQty]   = useState({});     // { key: number|"" }

  const [viewMode, setViewMode]   = useState("all");  // "all" | "in-po"

  /* submission state */
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState(null);

  const rowKey = r => `${r.sku}||${r.fulfillment_center}`;

  /* fetch grid data */
  useEffect(() => {
    setLoading(true);
    getFCFinal(replenishWeeks, channel, account, 12, fromWeek, toWeek)
      .then(json => {
        const data = Array.isArray(json?.data) ? json.data : (Array.isArray(json) ? json : []);
        setAvailableWeeks(json?.available_weeks || []);
        // Default include = rows where send_qty > 0
        const inc = {}, sq = {};
        data.forEach(r => {
          const k = `${r.sku}||${r.fulfillment_center}`;
          const q = Number(r.send_qty || 0);
          inc[k] = q > 0;
          sq[k]  = q;
        });
        setIncluded(inc);
        setSendQty(sq);
        setRows(data);
      })
      .catch(err => { console.error("FC data load failed", err); setRows([]); })
      .finally(() => setLoading(false));
  }, [account, replenishWeeks, channel, fromWeek, toWeek]);

  /* fetch selling accounts once */
  useEffect(() => {
    fetch(`${BASE}/selling-accounts`)
      .then(r => r.json())
      .then(j => {
        const acs = Array.isArray(j?.data) ? j.data : [];
        setSellingAccounts(acs);
        if (acs.length && !sellingAccountId) setSellingAccountId(acs[0].id);
      })
      .catch(err => console.error("selling-accounts load failed", err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* derived */
  const rowsInPo = useMemo(
    () => rows.filter(r => included[rowKey(r)] && Number(sendQty[rowKey(r)] || 0) > 0),
    [rows, included, sendQty]
  );
  const displayedRows = viewMode === "in-po" ? rowsInPo : rows;

  const kpis = useMemo(() => {
    const totalUnits = rowsInPo.reduce((a, r) => a + Number(sendQty[rowKey(r)] || 0), 0);
    const skus = new Set(rowsInPo.map(r => r.sku)).size;
    const fcs  = new Set(rowsInPo.map(r => r.fulfillment_center)).size;
    let overrides = 0;
    rowsInPo.forEach(r => {
      const q = Number(sendQty[rowKey(r)] || 0);
      const rec = Number(r.send_qty || 0);
      if (q !== rec) overrides++;
    });
    return { totalUnits, skus, fcs, overrides };
  }, [rowsInPo, sendQty]);

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
    const selling = sellingAccounts.find(a => a.id === sellingAccountId) || { id: sellingAccountId, name: sellingAccountId };
    const lines = rowsInPo.map(r => {
      const req = Number(sendQty[rowKey(r)] || 0);
      const rec = Number(r.send_qty || 0);
      return {
        sku: r.sku,
        asin: r.asin || "",
        model: r.model || "",
        ship_to_fc: r.fulfillment_center,
        recommended_qty: rec,
        quantity_requested: req,
        delta_vs_rec: req - rec,
      };
    });

    const body = {
      selling_account: selling,
      brand: account,   // grid data is scoped by brand/account filter
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

  const cols = [
    { id: "include",     header: "",              w: 40 },
    { id: "model",       header: "Model",         w: 130 },
    { id: "sku",         header: "SKU",           w: 100 },
    { id: "asin",        header: "ASIN",          w: 110 },
    { id: "fc",          header: "FC",            w: 65 },
    { id: "avg",         header: "Avg/Wk",        w: 75, numeric: true },
    { id: "soh",         header: "FC SOH",        w: 75, numeric: true },
    { id: "recommended", header: "Recommended",   w: 100, numeric: true },
    { id: "sendqty",     header: "Send Qty",      w: 110, numeric: true, editable: true },
    { id: "delta",       header: "Δ vs Rec",      w: 90, numeric: true },
    { id: "fill",        header: "Fill %",        w: 70, numeric: true },
  ];

  return (
    <div className="px-6 py-5 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-slate-900 inline-flex items-center gap-2">
          <PackagePlus className="w-5 h-5 text-indigo-600" />
          PO Creation
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Adjust FC Allocation recommendations and dispatch Internal POs to OrderPilot. One PO per FC.
        </p>
      </div>

      {/* Selling Account + filters */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-3 mb-3">
        <div className="grid grid-cols-12 gap-3 items-end">
          <div className="col-span-3">
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Selling Account</label>
            <select value={sellingAccountId} onChange={e => setSellingAccountId(e.target.value)}
              className="w-full px-2 py-1.5 text-sm rounded-md border border-indigo-200 bg-indigo-50 font-semibold">
              <option value="" disabled>Select account…</option>
              {sellingAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <div className="col-span-2">
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Brand (grid source)</label>
            <select value={account} onChange={e => setAccount(e.target.value)}
              className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
              {ACCOUNTS.map(a => <option key={a}>{a}</option>)}
            </select>
          </div>
          <div className="col-span-3">
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Past Sales (Selected week)</label>
            <div className="grid grid-cols-2 gap-1.5">
              <select value={fromWeek ?? ""} onChange={e => setFromWeek(Number(e.target.value))}
                className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                disabled={!availableWeeks.length}>
                {availableWeeks.map(w => <option key={`f${w}`} value={w}>From Wk {w}</option>)}
              </select>
              <select value={toWeek ?? ""} onChange={e => setToWeek(Number(e.target.value))}
                className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white"
                disabled={!availableWeeks.length}>
                {availableWeeks.map(w => <option key={`t${w}`} value={w}>To Wk {w}</option>)}
              </select>
            </div>
          </div>
          <div className="col-span-1">
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Inventory Cover</label>
            <select value={replenishWeeks} onChange={e => setReplenishWeeks(Number(e.target.value))}
              className="w-full px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
              {COVER_OPTIONS.map(n => <option key={n}>{n}</option>)}
            </select>
          </div>
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
        <KPI label="# FCs (POs)" value={kpis.fcs} />
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
              const rec = Number(r.send_qty || 0);
              const num = Number(q || 0);
              const delta = num - rec;
              return (
                <tr key={k} className={cn(!isIncluded && "opacity-40 bg-slate-50")}>
                  <td>
                    <input type="checkbox" checked={isIncluded} onChange={() => toggleRow(r)} />
                  </td>
                  <td className="font-semibold text-slate-900">{r.model || "—"}</td>
                  <td className="font-mono text-xs text-slate-700">{r.sku}</td>
                  <td className="font-mono text-xs text-slate-500">{r.asin || "—"}</td>
                  <td className="font-mono text-xs">{r.fulfillment_center}</td>
                  <td className="text-right tabular-nums">{r.weekly_velocity ?? 0}</td>
                  <td className="text-right tabular-nums">{r.fc_inventory ?? 0}</td>
                  <td className="text-right tabular-nums font-semibold">{rec}</td>
                  <td className="text-right">
                    <input type="number" min="0" value={q}
                      onChange={e => setQty(r, e.target.value)}
                      className="w-20 text-right px-1.5 py-1 border border-slate-200 rounded text-xs font-mono bg-amber-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/40" />
                  </td>
                  <td className={cn("text-right tabular-nums font-semibold",
                    delta > 0 ? "text-emerald-700" : delta < 0 ? "text-red-700" : "text-slate-400")}>
                    {delta > 0 ? `+${delta}` : delta}
                  </td>
                  <td className="text-right tabular-nums">{r.fill_pct != null ? `${Number(r.fill_pct).toFixed(0)}%` : "—"}</td>
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
