import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "../lib/cn";

/* ============================================================
   Collapsible column-group chips (operator 2026-08-25: "things need
   to be collapsible like sales inventory ... good for visibility").

   Purely presentational: the page owns `collapsed` (a Set of group
   keys) and filters its column array with isColumnVisible() before
   handing it to useReactTable. Sticky columns (meta.sticky === 1,
   i.e. the Model column) always stay visible so a collapsed group
   can never orphan the row identity.
============================================================ */

export function ColumnGroupToggles({ groups, collapsed, onToggle }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold mr-1">
        Sections
      </span>
      {groups.map(({ key, label, count }) => {
        const isCollapsed = collapsed.has(key);
        return (
          <button
            key={key}
            onClick={() => onToggle(key)}
            title={isCollapsed
              ? `Show the ${label} columns (${count})`
              : `Hide the ${label} columns (${count})`}
            className={cn(
              "inline-flex items-center gap-1 px-2 py-1 rounded-md border text-xs font-medium",
              isCollapsed
                ? "border-slate-200 bg-slate-100 text-slate-400"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            )}
          >
            {isCollapsed
              ? <ChevronRight className="w-3 h-3" />
              : <ChevronDown className="w-3 h-3" />}
            {label}
            <span className={cn(
              "tabular-nums text-[10px]",
              isCollapsed ? "text-slate-400" : "text-slate-400"
            )}>{count}</span>
          </button>
        );
      })}
    </div>
  );
}

/* Filter helper — keep a column when its group isn't collapsed, or when it
   is the sticky identity column. */
export function isColumnVisible(col, collapsed) {
  const meta = col.meta || {};
  if (meta.sticky === 1) return true;
  return !collapsed.has(meta.group);
}

/* Build the chip list from a column array + a {key: label} map, preserving
   the order groups first appear in the columns. */
export function groupsFromColumns(columns, labels) {
  const seen = new Map();
  for (const c of columns) {
    const g = (c.meta || {}).group;
    if (!g) continue;
    if (!seen.has(g)) seen.set(g, 0);
    seen.set(g, seen.get(g) + 1);
  }
  return [...seen.entries()].map(([key, count]) => ({
    key,
    label: labels[key] || key,
    count,
  }));
}
