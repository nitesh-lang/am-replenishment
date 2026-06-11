import React, { useEffect } from "react";
import { BookOpen, X } from "lucide-react";

/**
 * Generic SOP / "How is this calculated?" modal.
 *
 * Props:
 *   open      – boolean
 *   onClose   – callback
 *   title     – string (page name, e.g. "Replenishment")
 *   children  – the SOP content (JSX)
 */
export function SOPModal({ open, onClose, title, children }) {
  // Close on Escape
  useEffect(() => {
    function onKey(e) { if (e.key === "Escape") onClose?.(); }
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-12 px-4">
      <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-3xl bg-white rounded-xl border border-slate-200 shadow-2xl overflow-hidden max-h-[85vh] flex flex-col">
        <header className="flex items-center justify-between px-5 py-3 border-b border-slate-100 bg-slate-50/60">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-indigo-600" />
            <h2 className="text-sm font-semibold text-slate-900">SOP · {title}</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-900 p-1 rounded hover:bg-slate-100">
            <X className="w-4 h-4" />
          </button>
        </header>
        <div className="overflow-y-auto px-6 py-5 text-sm text-slate-700 leading-relaxed space-y-4">
          {children}
        </div>
        <footer className="px-5 py-2.5 border-t border-slate-100 bg-slate-50/60 text-[10px] text-slate-500 text-right">
          Press <kbd className="px-1 py-0.5 rounded bg-slate-200 font-mono">Esc</kbd> to close
        </footer>
      </div>
    </div>
  );
}

/** Small button you can drop next to "Export CSV" to open the modal. */
export function SOPButton({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="px-3 py-2 rounded-md border border-slate-200 bg-white text-sm font-medium hover:bg-slate-50 inline-flex items-center gap-1.5"
      title="Read the SOP for this page"
    >
      <BookOpen className="w-3.5 h-3.5" />
      How is this calculated?
    </button>
  );
}
