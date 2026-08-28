import { useState } from "react";
import { cn } from "../lib/cn";

/* ============================================================
   Compact ASIN chip (operator 2026-08-28: "between identity and
   listing ASIN column is cluttered").

   The full 10-char mono ASIN wrapped/clipped at narrow table
   widths into meaningless fragments ("…5BM", "/N81"). First-4 +
   last-4 stays identifiable at a glance, never wraps, the full
   value lives in the tooltip, and a click copies it — which is
   the only thing anyone actually does with an ASIN on this page.

   Display-only: sorting, search and CSV export all read the raw
   row value, not this rendering.
============================================================ */
export function AsinTag({ asin, eol }) {
  const [copied, setCopied] = useState(false);
  if (!asin) return <span className="text-slate-300 text-xs">—</span>;
  const compact = asin.length > 9 ? `${asin.slice(0, 4)}…${asin.slice(-4)}` : asin;
  return (
    <button
      type="button"
      title={`${asin} — click to copy`}
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(asin);
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      }}
      className={cn(
        "font-mono text-[11px] whitespace-nowrap px-1.5 py-0.5 rounded border transition-colors",
        copied
          ? "bg-emerald-50 border-emerald-300 text-emerald-700"
          : eol
            ? "bg-white border-slate-200 text-rose-400 line-through hover:border-slate-300"
            : "bg-white border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-700"
      )}
    >
      {copied ? "copied ✓" : compact}
    </button>
  );
}
