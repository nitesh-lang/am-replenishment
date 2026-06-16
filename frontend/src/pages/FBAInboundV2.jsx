import React, { useEffect, useMemo, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Search, Download } from "lucide-react";
import { cn } from "../lib/cn";

/* ============================================================
   FBA INBOUND V2 — Nexlev only (for now)
   Endpoint: GET /inbound-shipments?account=NEXLEV
   Source:   data/input/inbound_shipments_nexlev.csv
             ASIN + Model enriched from sku_master.xlsx via SellerSKU.
============================================================ */

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

const STATUS_STYLES = {
  IN_TRANSIT:    "bg-sky-100 text-sky-800 ring-sky-200",
  SHIPPED:       "bg-indigo-100 text-indigo-800 ring-indigo-200",
  READY_TO_SHIP: "bg-amber-100 text-amber-800 ring-amber-200",
  WORKING:       "bg-slate-100 text-slate-700 ring-slate-200",
  DELIVERED:     "bg-teal-100 text-teal-800 ring-teal-200",
  CHECKED_IN:    "bg-emerald-100 text-emerald-800 ring-emerald-200",
  RECEIVING:     "bg-violet-100 text-violet-800 ring-violet-200",
};

function StatusPill({ status }) {
  const s = STATUS_STYLES[status] || "bg-slate-100 text-slate-700 ring-slate-200";
  return (
    <span className={cn("inline-flex px-2 py-0.5 rounded text-[11px] font-semibold ring-1", s)}>
      {status || "—"}
    </span>
  );
}

export default function FBAInboundV2() {
  const [data, setData] = useState({ rows: [], summary: {} });
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState([]);
  const [fcFilter, setFcFilter] = useState([]);
  const [sorting, setSorting] = useState([{ id: "ShipmentStatus", desc: false }]);
  /* Edited remarks — keyed by `${ShipmentId}::${SellerSKU}` */
  const [remarks, setRemarks] = useState({});
  const [savingKey, setSavingKey] = useState(null);
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => {
    setLoading(true);
    fetch(`${BASE}/inbound-shipments?account=NEXLEV`)
      .then((r) => r.json())
      .then((j) => {
        const rows = j.rows || [];
        setData({ rows, summary: j.summary || {} });
        const m = {};
        rows.forEach((r) => {
          if (r.Remarks) m[`${r.ShipmentId}::${r.SellerSKU}`] = r.Remarks;
        });
        setRemarks(m);
      })
      .catch(() => setData({ rows: [], summary: {} }))
      .finally(() => setLoading(false));
  }, []);

  async function saveRemark(shipmentId, sellerSku, value) {
    const key = `${shipmentId}::${sellerSku}`;
    setSavingKey(key);
    setSaveMsg("");
    try {
      const res = await fetch(`${BASE}/inbound-shipments/save-remarks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account: "NEXLEV",
          rows: [{ shipment_id: shipmentId, seller_sku: sellerSku, remarks: value }],
        }),
      });
      const j = await res.json();
      setSaveMsg(j.status === "saved" ? "Saved" : (j.error || "Save failed"));
      setTimeout(() => setSaveMsg(""), 1500);
    } catch (e) {
      setSaveMsg("Save failed");
    } finally {
      setSavingKey(null);
    }
  }

  /* ─────────── derived option sets ─────────── */
  const allStatuses = useMemo(() => {
    const s = new Set();
    data.rows.forEach((r) => r.ShipmentStatus && s.add(r.ShipmentStatus));
    return Array.from(s).sort();
  }, [data.rows]);

  const allFCs = useMemo(() => {
    const s = new Set();
    data.rows.forEach((r) => r.DestinationFC && s.add(r.DestinationFC));
    return Array.from(s).sort();
  }, [data.rows]);

  /* ─────────── filter ─────────── */
  const filtered = useMemo(() => {
    let rows = data.rows;
    if (statusFilter.length) rows = rows.filter((r) => statusFilter.includes(r.ShipmentStatus));
    if (fcFilter.length) rows = rows.filter((r) => fcFilter.includes(r.DestinationFC));
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter((r) => {
        const haystack = [r.SellerSKU, r.ASIN, r.Model, r.ShipmentId, r.ShipFrom, r.DestinationFC]
          .map((v) => String(v || "").toLowerCase())
          .join("|");
        return haystack.includes(q);
      });
    }
    return rows;
  }, [data.rows, statusFilter, fcFilter, search]);

  /* ─────────── columns ─────────── */
  const columns = useMemo(
    () => [
      {
        accessorKey: "SellerSKU",
        header: "Seller SKU",
        cell: ({ getValue }) => <span className="font-mono text-[12px]">{getValue()}</span>,
      },
      {
        accessorKey: "ASIN",
        header: "ASIN",
        cell: ({ getValue }) => <span className="font-mono text-[12px] text-slate-600">{getValue() || "—"}</span>,
      },
      { accessorKey: "Model", header: "Model" },
      { accessorKey: "ShipFrom", header: "Shipped From" },
      {
        accessorKey: "DestinationFC",
        header: "Destination FC",
        cell: ({ getValue }) => (
          <span className="inline-flex px-1.5 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 ring-1 ring-slate-200">
            {getValue() || "—"}
          </span>
        ),
      },
      {
        accessorKey: "QuantityShipped",
        header: "Qty Shipped",
        cell: ({ getValue }) => <span className="font-mono tabular-nums">{Number(getValue() || 0).toLocaleString()}</span>,
      },
      {
        accessorKey: "QuantityReceived",
        header: "Qty Received",
        cell: ({ getValue }) => <span className="font-mono tabular-nums text-slate-600">{Number(getValue() || 0).toLocaleString()}</span>,
      },
      {
        accessorKey: "QuantityInCase",
        header: "Qty In Case",
        cell: ({ getValue }) => <span className="font-mono tabular-nums text-slate-500">{Number(getValue() || 0).toLocaleString()}</span>,
      },
      {
        accessorKey: "ShipmentStatus",
        header: "Status",
        cell: ({ getValue }) => <StatusPill status={getValue()} />,
      },
      {
        accessorKey: "ShipmentId",
        header: "Shipment ID",
        cell: ({ getValue }) => <span className="font-mono text-[11px] text-slate-500">{getValue()}</span>,
      },
      {
        id: "Remarks",
        header: "Remarks",
        enableSorting: false,
        cell: ({ row }) => {
          const sid = row.original.ShipmentId;
          const sku = row.original.SellerSKU;
          const key = `${sid}::${sku}`;
          const value = remarks[key] ?? "";
          const isSaving = savingKey === key;
          return (
            <input
              type="text"
              value={value}
              onChange={(e) => setRemarks((m) => ({ ...m, [key]: e.target.value }))}
              onBlur={(e) => {
                // only call save if value actually changed from server snapshot for this row
                const original = row.original.Remarks || "";
                if (e.target.value !== original) saveRemark(sid, sku, e.target.value);
              }}
              disabled={isSaving}
              placeholder="—"
              className="w-44 px-2 py-1 text-[12px] border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-indigo-400 bg-white"
            />
          );
        },
      },
    ],
    [remarks, savingKey]
  );

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  /* ─────────── CSV export ─────────── */
  function downloadCsv() {
    const headers = ["Seller SKU", "ASIN", "Model", "Shipped From", "Destination FC",
                     "Qty Shipped", "Qty Received", "Qty In Case", "Status", "Shipment ID", "Remarks"];
    const lines = [headers.join(",")];
    filtered.forEach((r) => {
      const key = `${r.ShipmentId}::${r.SellerSKU}`;
      const row = [
        r.SellerSKU, r.ASIN, r.Model, r.ShipFrom, r.DestinationFC,
        r.QuantityShipped, r.QuantityReceived, r.QuantityInCase,
        r.ShipmentStatus, r.ShipmentId, remarks[key] ?? r.Remarks ?? "",
      ].map((v) => {
        const s = String(v ?? "");
        return s.includes(",") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
      });
      lines.push(row.join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fba_inbound_nexlev_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const sum = data.summary || {};

  return (
    <div className="px-6 py-5 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Nexlev FBA Inbound Shipments</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Live SP-API pull. ASIN + Model enriched via sku_master. Source: <code className="text-[11px]">inbound_shipments_nexlev.csv</code>
          </p>
        </div>
        <div className="flex items-center gap-3">
          {saveMsg && (
            <span className="text-[11px] text-slate-600">{saveMsg}</span>
          )}
          <button
            onClick={downloadCsv}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-900 text-white hover:bg-slate-800"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <KpiCard label="Shipments"     value={sum.total_shipments} />
        <KpiCard label="In-flight Units" value={sum.in_flight_units} accent="sky" />
        <KpiCard label="At-FC Remaining" value={sum.at_fc_remaining} accent="violet" />
        <KpiCard label="Total Incoming" value={sum.total_incoming} accent="emerald" />
      </div>

      {/* Filters */}
      <div className="bg-white border border-slate-200 rounded-lg p-3 mb-3 space-y-2.5">
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search SKU, ASIN, Model, Shipment ID…"
              className="pl-8 pr-3 py-1.5 text-xs border border-slate-300 rounded w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <span className="text-[11px] text-slate-500">
            {filtered.length} rows {filtered.length !== data.rows.length && `of ${data.rows.length}`}
          </span>
        </div>

        <ChipFilter
          label="Status"
          options={allStatuses}
          selected={statusFilter}
          onChange={setStatusFilter}
          renderOption={(opt) => <StatusPill status={opt} />}
        />
        <ChipFilter
          label="FC"
          options={allFCs}
          selected={fcFilter}
          onChange={setFcFilter}
        />
      </div>

      {/* Table */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        {loading ? (
          <div className="p-10 text-center text-sm text-slate-500">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">No shipments match the current filters.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-[12px]">
              <thead className="bg-slate-50 border-b border-slate-200">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((h) => (
                      <th
                        key={h.id}
                        onClick={h.column.getToggleSortingHandler()}
                        className="px-3 py-2 text-left font-semibold text-slate-700 cursor-pointer select-none whitespace-nowrap"
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {h.column.getIsSorted() === "asc" && " ▲"}
                        {h.column.getIsSorted() === "desc" && " ▼"}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-1.5 whitespace-nowrap">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function KpiCard({ label, value, accent }) {
  const accentRing = {
    sky:     "ring-sky-200",
    violet:  "ring-violet-200",
    emerald: "ring-emerald-200",
  }[accent] || "ring-slate-200";
  const accentText = {
    sky:     "text-sky-700",
    violet:  "text-violet-700",
    emerald: "text-emerald-700",
  }[accent] || "text-slate-900";
  return (
    <div className={cn("bg-white border border-slate-200 rounded-lg p-3 ring-1", accentRing)}>
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</div>
      <div className={cn("text-xl font-bold tabular-nums mt-1", accentText)}>
        {value != null ? Number(value).toLocaleString() : "—"}
      </div>
    </div>
  );
}

function ChipFilter({ label, options, selected, onChange, renderOption }) {
  function toggle(opt) {
    if (selected.includes(opt)) onChange(selected.filter((x) => x !== opt));
    else onChange([...selected, opt]);
  }
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-[11px] text-slate-500 font-medium mr-1">{label}:</span>
      {options.map((opt) => {
        const isSel = selected.includes(opt);
        return (
          <button
            key={opt}
            onClick={() => toggle(opt)}
            className={cn(
              "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium transition",
              isSel
                ? "bg-indigo-600 text-white ring-1 ring-indigo-600"
                : "bg-white text-slate-600 ring-1 ring-slate-300 hover:bg-slate-50"
            )}
          >
            {renderOption ? renderOption(opt) : opt}
          </button>
        );
      })}
      {selected.length > 0 && (
        <button
          onClick={() => onChange([])}
          className="text-[10px] text-slate-500 hover:text-slate-800 ml-1 underline"
        >
          clear
        </button>
      )}
    </div>
  );
}
