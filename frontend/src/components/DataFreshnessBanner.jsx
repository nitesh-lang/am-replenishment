import React, { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

/**
 * Informational banner shown atop every V2 module when any of its input
 * files is older than the current Sun-Sat working week.
 *
 * Non-blocking: operator occasionally reprocesses last week, so a
 * "Dismiss for this week" button stores a per-(module, week) flag in
 * localStorage. The banner re-appears next week automatically.
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
        // Re-evaluate dismissed flag against this week's key
        const key = `freshness_dismissed_${module}_${j?.current_week?.num ?? ""}`;
        setDismissed(localStorage.getItem(key) === "1");
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [module]);

  if (!data || !data.any_stale || dismissed) return null;

  const stale = (data.files || []).filter((f) => !f.fresh);
  const cw = data.current_week || {};

  function dismiss() {
    const key = `freshness_dismissed_${module}_${cw.num ?? ""}`;
    localStorage.setItem(key, "1");
    setDismissed(true);
  }

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
