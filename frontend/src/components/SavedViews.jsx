import React from "react";
import { Plus } from "lucide-react";

/**
 * Saved views bar.
 * views: [{ key, label, count, accent? }]
 * active: key
 * onPick: (key) => void
 */
export function SavedViews({ views, active, onPick, onSaveCurrent }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 shadow-sm px-3 py-2 flex items-center gap-1 overflow-x-auto">
      <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold pr-2 whitespace-nowrap">
        Saved views
      </div>
      {views.map(v => (
        <button
          key={v.key}
          onClick={() => onPick?.(v.key)}
          className={`px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap ${
            active === v.key
              ? "bg-slate-900 text-white"
              : "text-slate-700 hover:bg-slate-100"
          }`}
        >
          {v.label} · {v.count}
          {v.accent && (
            <span className={`ml-1 px-1 py-0.5 rounded text-[9px] ${v.accent}`}>●</span>
          )}
        </button>
      ))}
      <div className="flex-1" />
      {onSaveCurrent && (
        <button
          onClick={onSaveCurrent}
          className="px-2 py-1.5 rounded-md text-xs font-medium text-indigo-600 hover:bg-indigo-50 whitespace-nowrap inline-flex items-center gap-1"
        >
          <Plus className="w-3 h-3" />
          Save current
        </button>
      )}
    </div>
  );
}
