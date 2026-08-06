import React, { useEffect, useState } from "react";
import { AlertTriangle, X, AlertOctagon } from "lucide-react";

const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";

/**
 * Two-tier data-freshness banner shown atop every V2 module.
 *
 * TIER 1 — CRITICAL (red, non-dismissible): a spec entry marked
 *   `critical=True` on the backend is missing or stale. Blocks
 *   nothing at the API level (data still returns), but the visual
 *   makes it obvious the operator must upload the missing input
 *   before trusting the numbers. Example: In_Transit_PO data.xlsx
 *   for CB Replenishment — if it's absent, po_requirement is
 *   overstated by whatever's in transit but not deducted.
 *
 * TIER 2 — WARNING (amber, dismissible per (module, week)):
 *   ordinary weekly staleness. Operator often processes last
 *   week's data intentionally, so this can be dismissed for one
 *   week and re-appears next.
 *
 * Usage:
 *   <DataFreshnessBanner module="cb-replenishment" />
 */
export default function DataFreshnessBanner({ module }) {
  const [data, setData] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${BASE}/data-freshness?module=${encodeURIComponent(module)}`)
      .then((r) => r.json())
      .then((j) => {
        if (cancelled) return;
        setData(j);
        const key = `freshness_dismissed_${module}_${j?.current_week?.num ?? ""}`;
        setDismissed(localStorage.getItem(key) === "1");
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [module]);

  if (!data || !data.any_stale) return null;

  const stale = (data.files || []).filter((f) => !f.fresh);
  const cw = data.current_week || {};
  const critical_failed = !!data.critical_failed;

  // Critical banner is NOT dismissible.
  if (dismissed && !critical_failed) return null;

  function dismiss() {
    const key = `freshness_dismissed_${module}_${cw.num ?? ""}`;
    localStorage.setItem(key, "1");
    setDismissed(true);
  }

  if (critical_failed) {
    const criticalItems = stale.filter((f) => f.critical);
    const nonCriticalItems = stale.filter((f) => !f.critical);
    return (
      <div className="mb-3 px-3 py-2 rounded-md bg-red-50 border-2 border-red-500 text-red-900 flex items-start gap-2.5">
        <AlertOctagon className="w-5 h-5 mt-0.5 shrink-0 text-red-600" />
        <div className="flex-1 min-w-0 text-[12px] leading-snug">
          <div className="font-bold mb-1 text-red-800 uppercase tracking-wide text-[11px]">
            FAILED — required input {criticalItems.length > 1 ? "files are" : "file is"} missing or stale
          </div>
          <ul className="space-y-0.5">
            {criticalItems.map((f) => (
              <li key={f.path}>
                <span className="font-semibold">{f.label}</span>
                {" · "}
                {f.missing ? (
                  <span className="text-red-700 font-bold">missing</span>
                ) : (
                  <>
                    as of <span className="font-mono">{f.as_of}</span>
                    {f.as_of_week != null && (
                      <span className="text-red-700"> (W{f.as_of_week})</span>
                    )}
                    {f.stale_by_weeks > 0 && (
                      <span className="ml-1 inline-flex items-center px-1 py-0 rounded bg-red-200 text-red-900 text-[10px] font-bold">
                        {f.stale_by_weeks}w old
                      </span>
                    )}
                  </>
                )}
                {f.path && f.path !== "(FBA Sales folder)" && (
                  <span className="ml-1 font-mono text-[10px] text-red-700">({f.path})</span>
                )}
              </li>
            ))}
          </ul>
          {nonCriticalItems.length > 0 && (
            <div className="mt-1.5 text-red-700 text-[11px]">
              Also stale (informational): {nonCriticalItems.map((f) => f.label).join(", ")}
            </div>
          )}
          <div className="mt-1.5 text-red-800 text-[11px] font-semibold">
            Upload the missing file(s) before trusting the numbers on this page.
          </div>
        </div>
      </div>
    );
  }

  // Non-critical (amber, dismissible) — existing behaviour
  return (
    <div className="mb-3 px-3 py-2 rounded-md bg-amber-50 border border-amber-300 text-amber-900 flex items-start gap-2.5">
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-600" />
      <div className="flex-1 min-w-0 text-[12px] leading-snug">
        <div className="font-semibold mb-0.5">
          Some inputs haven't been refreshed for this week (W{cw.num})
        </div>
        <ul className="space-y-0.5">
          {stale.map((f) => (
            <li key={f.path}>
              <span className="font-medium">{f.label}</span>
              {" · "}
              {f.missing ? (
                <span className="text-red-700 font-semibold">missing</span>
              ) : (
                <>
                  as of <span className="font-mono">{f.as_of}</span>
                  {f.as_of_week != null && (
                    <span className="text-amber-700"> (W{f.as_of_week})</span>
                  )}
                  {f.stale_by_weeks > 0 && (
                    <span className="ml-1 inline-flex items-center px-1 py-0 rounded bg-amber-200 text-amber-900 text-[10px] font-bold">
                      {f.stale_by_weeks}w old
                    </span>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
        <div className="mt-1 text-amber-700 text-[11px]">
          Proceeding is fine if you're intentionally processing last week's data.
        </div>
      </div>
      <button
        onClick={dismiss}
        className="shrink-0 text-amber-700 hover:text-amber-900 hover:bg-amber-100 rounded px-1.5 py-0.5 text-[11px] font-medium inline-flex items-center gap-1"
        title="Dismiss for this week"
      >
        <X className="w-3 h-3" />
        Dismiss
      </button>
    </div>
  );
}
