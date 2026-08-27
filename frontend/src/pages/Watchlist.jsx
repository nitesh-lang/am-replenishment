import { useEffect, useMemo, useState } from "react";
import { cn } from "../lib/cn";

/* ============================================================
   REPLENISHMENT WATCHLIST
   Models that need a human decision this week, with the reason and the
   suggested action. Read-only + an editable email draft.

   Fossil is excluded server-side (no ASIN Type, separate PO flow).
============================================================ */

const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";

const ACCOUNTS = ["NEXLEV", "VIOMI", "AUDIO ARRAY", "WHITE MULBERRY"];

const SIGNAL_META = {
  LOST_SALES_NO_RELIEF:      { label: "Lost sales — no China arrival", tone: "bg-red-100 text-red-800 border-red-200" },
  LOST_SALES_RELIEF_INBOUND: { label: "Lost sales — relief inbound",   tone: "bg-amber-100 text-amber-800 border-amber-200" },
  NEW_LAUNCH_MUTED:          { label: "New launch — understated",      tone: "bg-indigo-100 text-indigo-800 border-indigo-200" },
  DEMAND_ACCELERATING:       { label: "Demand accelerating",           tone: "bg-sky-100 text-sky-800 border-sky-200" },
  STRANDED_AT_MOTHER_WH:     { label: "Stranded at mother WH",         tone: "bg-slate-100 text-slate-700 border-slate-200" },
  EOL_STILL_SELLING:         { label: "EOL but still selling",         tone: "bg-purple-100 text-purple-800 border-purple-200" },
};

export default function Watchlist() {
  const [accounts, setAccounts] = useState(ACCOUNTS);
  const [salesWindow, setSalesWindow] = useState(12);
  const [coverWeeks, setCoverWeeks] = useState(8);
  const [velocityMode, setVelocityMode] = useState("max");
  // Benchmark for the lost-units figures — Watchlist-only option; the
  // Replenishment tab keeps its historical peak-based numbers.
  const [lostBasis, setLostBasis] = useState("avg");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [signalFilter, setSignalFilter] = useState("");
  // ASIN Type is filtered SERVER-side (same param on both endpoints) so the
  // email draft can never describe a different set than what's on screen.
  const [asinTypes, setAsinTypes] = useState([]);
  // Options survive across fetches — the filtered response only reports the
  // types that are still present, which would make the chips vanish on click.
  const [asinTypeOpts, setAsinTypeOpts] = useState([]);

  // Changing the account scope invalidates both the selection and the chip
  // options (they were computed from the previous scope). Resetting the
  // selection makes the next fetch unfiltered, which refreshes the options.
  useEffect(() => { setAsinTypes([]); }, [accounts]);

  // Email draft — fetched on demand, then fully editable before the operator
  // copies it out. Nothing is ever sent from here.
  const [draft, setDraft] = useState(null);
  const [draftBusy, setDraftBusy] = useState(false);
  const [copied, setCopied] = useState("");

  const qs = useMemo(() => {
    const p = new URLSearchParams({
      sales_window: salesWindow,
      replenish_weeks: coverWeeks,
      velocity_mode: velocityMode,
      lost_basis: lostBasis,
    });
    if (accounts.length && accounts.length < ACCOUNTS.length) {
      p.set("account", accounts.join(","));
    }
    if (asinTypes.length) p.set("asin_type", asinTypes.join(","));
    return p.toString();
  }, [accounts, salesWindow, coverWeeks, velocityMode, asinTypes, lostBasis]);

  useEffect(() => {
    setLoading(true); setErr(""); setDraft(null);
    fetch(`${BASE}/watchlist?${qs}`)
      .then(r => r.json())
      .then(j => {
        setData(j);
        // Only refresh the chip list from an UNFILTERED response, otherwise
        // picking one type would drop every other option from the row.
        if (!asinTypes.length) setAsinTypeOpts(j?.asin_types_available || []);
      })
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }, [qs]);

  async function loadDraft() {
    setDraftBusy(true);
    try {
      const j = await fetch(`${BASE}/watchlist/email-draft?${qs}`).then(r => r.json());
      setDraft(j);
    } catch (e) {
      setErr(e.message);
    } finally {
      setDraftBusy(false);
    }
  }

  function copy(text, what) {
    navigator.clipboard?.writeText(text);
    setCopied(what);
    setTimeout(() => setCopied(""), 2000);
  }

  const rows = data?.rows || [];
  const shown = signalFilter ? rows.filter(r => r.signal === signalFilter) : rows;
  const counts = data?.counts || {};

  return (
    <div className="p-6 max-w-[1500px] mx-auto">
      <div className="flex items-start justify-between gap-4 mb-1">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Replenishment Watchlist</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Models where the system number alone would under-serve demand — with the
            reason and what to do. Fossil is excluded (no ASIN Type, separate PO flow).
          </p>
        </div>
        <button
          onClick={loadDraft}
          disabled={draftBusy || !rows.length}
          className="px-3 py-2 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium disabled:opacity-50 shrink-0"
        >
          {draftBusy ? "Building…" : "Draft email"}
        </button>
      </div>

      {/* Controls */}
      <div className="bg-white border border-slate-200 rounded-lg p-3 my-4 flex flex-wrap items-end gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Accounts</div>
          <div className="flex flex-wrap gap-1.5">
            {ACCOUNTS.map(a => {
              const on = accounts.includes(a);
              return (
                <button key={a}
                  onClick={() => setAccounts(p => p.includes(a) ? p.filter(x => x !== a) : [...p, a])}
                  className={cn("px-2.5 py-1 text-xs font-medium rounded-md border",
                    on ? "bg-slate-800 text-white border-slate-800"
                       : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50")}>
                  {a}
                </button>
              );
            })}
          </div>
        </div>
        <label className="text-xs text-slate-600">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Sales window</div>
          <select value={salesWindow} onChange={e => setSalesWindow(Number(e.target.value))}
            className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
            {[4, 8, 12, 16, 26].map(n => <option key={n} value={n}>{n} wk</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-600">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Cover</div>
          <select value={coverWeeks} onChange={e => setCoverWeeks(Number(e.target.value))}
            className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
            {[2, 4, 6, 8, 10, 12].map(n => <option key={n} value={n}>{n} wk</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-600">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Velocity basis</div>
          <select value={velocityMode} onChange={e => setVelocityMode(e.target.value)}
            className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
            <option value="max">Higher of window / 2wk</option>
            <option value="window">Selected window only</option>
          </select>
        </label>
        <label className="text-xs text-slate-600" title="What a flagged week is measured against when counting lost units. Simple math: benchmark minus that week's actual sales.">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Lost-units basis</div>
          <select value={lostBasis} onChange={e => setLostBasis(e.target.value)}
            className="px-2 py-1.5 text-sm rounded-md border border-slate-200 bg-white">
            <option value="avg">Average weekly sales</option>
            <option value="2wk">Last 2 weeks</option>
            <option value="peak">Peak week</option>
          </select>
        </label>

        {asinTypeOpts.length > 0 && (
          <div className="w-full border-t border-slate-100 pt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mr-1">ASIN Type</span>
            {asinTypeOpts.map(t => {
              const on = asinTypes.includes(t);
              return (
                <button key={t}
                  onClick={() => setAsinTypes(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t])}
                  className={cn("px-2.5 py-1 text-xs font-medium rounded-md border transition-colors",
                    on ? "bg-sky-600 text-white border-sky-600"
                       : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50")}>
                  {t}
                </button>
              );
            })}
            {asinTypes.length > 0 && (
              <button onClick={() => setAsinTypes([])}
                className="text-xs text-slate-500 hover:text-slate-900 ml-1">clear</button>
            )}
          </div>
        )}
      </div>

      {err && <div className="bg-red-50 text-red-800 border border-red-200 rounded-md p-3 mb-4 text-sm">{err}</div>}
      {data?.errors?.length > 0 && (
        <div className="bg-amber-50 text-amber-900 border border-amber-200 rounded-md p-3 mb-4 text-sm">
          Some accounts failed to load: {data.errors.join(" · ")}
        </div>
      )}

      {/* Signal summary — click to filter */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button onClick={() => setSignalFilter("")}
          className={cn("px-3 py-1.5 rounded-md border text-xs font-semibold",
            !signalFilter ? "bg-slate-800 text-white border-slate-800" : "bg-white border-slate-200")}>
          All {rows.length}
        </button>
        {Object.entries(SIGNAL_META).map(([key, meta]) => {
          const n = counts[key] || 0;
          if (!n) return null;
          const units = rows.filter(r => r.signal === key)
                            .reduce((a, r) => a + (r.units_at_stake || 0), 0);
          return (
            <button key={key} onClick={() => setSignalFilter(signalFilter === key ? "" : key)}
              title={`~${units.toLocaleString()} units at stake`}
              className={cn("px-3 py-1.5 rounded-md border text-xs font-semibold",
                signalFilter === key ? "ring-2 ring-offset-1 ring-slate-400 " + meta.tone : meta.tone)}>
              {meta.label} · {n}
              <span className="ml-1.5 font-normal opacity-70">~{units.toLocaleString()}u</span>
            </button>
          );
        })}
      </div>

      {loading && <div className="text-sm text-slate-500">Loading…</div>}
      {!loading && !rows.length && (
        <div className="bg-white border border-slate-200 rounded-lg p-8 text-center text-slate-500 text-sm">
          Nothing on the watchlist for this selection — no model clears the materiality
          threshold (20+ units, or a gap worth 4+ weeks of the model's own demand).
        </div>
      )}

      {/* Cards — one per signal, evidence + action */}
      <div className="space-y-2">
        {shown.map((r, i) => {
          const meta = SIGNAL_META[r.signal] || { label: r.signal, tone: "bg-slate-100 text-slate-700 border-slate-200" };
          return (
            <div key={`${r.account}-${r.sku}-${r.signal}-${i}`}
              className="bg-white border border-slate-200 rounded-lg p-3">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className={cn("px-2 py-0.5 rounded text-[11px] font-bold border", meta.tone)}>
                  {meta.label}
                </span>
                <span className="font-semibold text-slate-900">{r.model}</span>
                <span className="text-xs text-slate-500 font-mono">{r.sku} · {r.asin || "—"}</span>
                <span className="text-xs text-slate-500">{r.account}</span>
                {r.asin_type && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{r.asin_type}</span>
                )}
                {/* Deep 1P cover inverts the recommendation, so it has to be
                    visible at a glance and not buried in the action text. */}
                {r.cb_deep && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-200 text-amber-900 border border-amber-300"
                        title="Amazon's own 1P stock already covers the replenishment horizon — do not buy on this row's evidence.">
                    HOLD · 1P covered
                  </span>
                )}
                <span className="ml-auto text-xs font-semibold text-slate-700 tabular-nums">
                  ~{(r.units_at_stake || 0).toLocaleString()} units at stake
                </span>
              </div>
              <div className="text-sm font-medium text-slate-800">{r.headline}</div>
              <div className="text-xs text-slate-600 mt-1"><b>Why:</b> {r.why}</div>
              <div className="text-xs text-slate-800 mt-0.5"><b>Action:</b> {r.action}</div>
              <div className="flex flex-wrap gap-3 mt-2 text-[11px] text-slate-500 tabular-nums">
                <span>vel {r.velocity}/wk ({r.velocity_basis})</span>
                <span>Amazon {r.amazon_available}{r.weeks_cover != null && ` · ${r.weeks_cover}wk cover`}</span>
                <span>Mother WH {r.mother_wh}</span>
                {/* CB SOH exists only for Audio Array and Tonor (the two 1P
                    vendor brands). null = no vendor channel at all, so the
                    chip is hidden — 0 and "not applicable" are different
                    facts and 0 is the alarming one, not the neutral one. */}
                {r.cb_soh != null && (
                  <span
                    title={
                      r.cb_channel === "dark"
                        ? "Amazon's 1P warehouse holds 0 sellable units of this model — the ASIN is unbuyable on both channels."
                        : `Amazon's 1P warehouse holds ${r.cb_soh} sellable units`
                          + (r.cb_soh_weeks ? ` (~${r.cb_soh_weeks} wks at this run rate)` : "")
                          + " — the listing stayed buyable via the 1P offer, so lost units are an upper bound. This stock is Amazon's; it cannot be sent into FBA."
                    }
                    className={cn("px-1.5 rounded font-medium cursor-help",
                      r.cb_channel === "dark"
                        ? "bg-red-100 text-red-800"
                        : "bg-emerald-50 text-emerald-700")}
                  >
                    1P (CB) {r.cb_soh}
                    {r.cb_channel === "dark" ? " · dark" :
                      r.cb_soh_weeks ? ` · ${r.cb_soh_weeks}wk` : ""}
                  </span>
                )}
                <span>China pipeline {r.china_pipeline}</span>
                <span>system asks {r.replen_qty}</span>
                {r.lost_units_3m > 0 && <span>lost 3m {r.lost_units_3m}</span>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Email draft — editable, preview, copy. Never sends. */}
      {draft && (
        <div className="mt-6 bg-white border border-indigo-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-semibold text-slate-900">Email draft</h2>
            <span className="text-[11px] text-slate-500">
              Editable — nothing is sent from here. Copy into your mail client.
            </span>
          </div>
          <div className="grid gap-2 text-sm">
            <Field label="From" value={draft.from} />
            <Field label="To"   value={(draft.to || []).join(", ")}
                   onCopy={() => copy((draft.to || []).join(", "), "to")} copied={copied === "to"} />
            <Field label="Cc"   value={(draft.cc || []).join(", ")}
                   onCopy={() => copy((draft.cc || []).join(", "), "cc")} copied={copied === "cc"} />
            <label className="block">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Subject</div>
              <input
                value={draft.subject}
                onChange={e => setDraft({ ...draft, subject: e.target.value })}
                className="w-full px-2 py-1.5 rounded-md border border-slate-200 text-sm"
              />
            </label>
            <label className="block">
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Body</div>
              <textarea
                value={draft.body}
                onChange={e => setDraft({ ...draft, body: e.target.value })}
                rows={20}
                className="w-full px-2 py-1.5 rounded-md border border-slate-200 text-xs font-mono leading-relaxed"
              />
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => copy(draft.body, "body")}
                className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50"
              >
                {copied === "body" ? "Copied ✓" : "Copy body"}
              </button>
              <a
                href={`mailto:${encodeURIComponent((draft.to || []).join(","))}`
                    + `?cc=${encodeURIComponent((draft.cc || []).join(","))}`
                    + `&subject=${encodeURIComponent(draft.subject || "")}`
                    + `&body=${encodeURIComponent(draft.body || "")}`}
                className="px-3 py-2 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium"
              >
                Open in mail client
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, onCopy, copied }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">{label}</div>
      <div className="flex items-center gap-2">
        <div className="flex-1 px-2 py-1.5 rounded-md border border-slate-200 bg-slate-50 text-sm font-mono text-slate-700 break-all">
          {value || "—"}
        </div>
        {onCopy && (
          <button onClick={onCopy} className="text-xs text-slate-500 hover:text-slate-900 shrink-0">
            {copied ? "copied ✓" : "copy"}
          </button>
        )}
      </div>
    </div>
  );
}
