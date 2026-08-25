import React, { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";

/**
 * ⌘K-style command palette.
 * Mount once at the page root. Press Cmd/Ctrl+K to open.
 *
 * Props:
 *   rows: current dataset
 *   views: [{ key, label }]  — saved views
 *   onPick: (item) => void   — fires with { type: "sku"|"view"|"action", payload }
 */
export function CommandPalette({ rows = [], views = [], onPick }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef(null);

  // Toggle on Cmd/Ctrl+K
  useEffect(() => {
    function handler(e) {
      const isToggle = (e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K");
      if (isToggle) {
        e.preventDefault();
        setOpen(o => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus();
    if (!open) {
      setQuery("");
      setCursor(0);
    }
  }, [open]);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    const paletteHasExact = q && rows.some(r =>
      (r.sku || "").toLowerCase() === q ||
      (r.model || "").toLowerCase() === q ||
      (r.asin || "").toLowerCase() === q
    );
    const skuMatches = rows
      .filter(r => {
        if (!q) return false;
        // Exact-match-first, mirroring the table search boxes.
        if (paletteHasExact) {
          return (
            (r.sku || "").toLowerCase() === q ||
            (r.model || "").toLowerCase() === q ||
            (r.asin || "").toLowerCase() === q
          );
        }
        return (
          (r.sku || "").toLowerCase().includes(q) ||
          (r.model || "").toLowerCase().includes(q) ||
          (r.asin || "").toLowerCase().includes(q)
        );
      })
      .slice(0, 6)
      .map(r => ({ type: "sku", payload: r, label: `${r.model} · ${r.sku}`, sub: `${r.asin || "—"} · ${r.sales_velocity}/wk` }));

    const viewMatches = views
      .filter(v => !q || v.label.toLowerCase().includes(q))
      .slice(0, 5)
      .map(v => ({ type: "view", payload: v, label: `Open "${v.label}"`, sub: v.hint || "" }));

    const actions = [
      { type: "action", payload: "export", label: "Export current view to CSV", sub: "⌘E" },
    ].filter(a => !q || a.label.toLowerCase().includes(q));

    return { skuMatches, viewMatches, actions };
  }, [query, rows, views]);

  const flat = [...items.skuMatches, ...items.viewMatches, ...items.actions];

  function handleKey(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor(c => Math.min(c + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor(c => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const sel = flat[cursor];
      if (sel && onPick) {
        onPick(sel);
        setOpen(false);
      }
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] px-4" role="dialog">
      <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-2xl bg-white rounded-xl border border-slate-200 shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100">
          <Search className="w-4 h-4 text-slate-300" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setCursor(0); }}
            onKeyDown={handleKey}
            className="flex-1 text-sm bg-transparent focus:outline-none"
            placeholder="Jump to SKU, Model, ASIN, view, or action…"
          />
          <kbd className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] font-mono text-slate-500">esc</kbd>
        </div>

        <div className="py-2 max-h-[60vh] overflow-y-auto">
          {flat.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-slate-400">
              {query ? "No matches" : "Start typing or use ↑↓"}
            </div>
          )}

          {items.skuMatches.length > 0 && (
            <>
              <SectionHeader>SKUs</SectionHeader>
              <div className="px-2">
                {items.skuMatches.map((it, i) => (
                  <Item key={`sku-${i}`} item={it} active={cursor === i} onClick={() => { onPick?.(it); setOpen(false); }} />
                ))}
              </div>
            </>
          )}

          {items.viewMatches.length > 0 && (
            <>
              <SectionHeader>Views</SectionHeader>
              <div className="px-2">
                {items.viewMatches.map((it, i) => {
                  const idx = items.skuMatches.length + i;
                  return (
                    <Item key={`v-${i}`} item={it} active={cursor === idx} onClick={() => { onPick?.(it); setOpen(false); }} />
                  );
                })}
              </div>
            </>
          )}

          {items.actions.length > 0 && (
            <>
              <SectionHeader>Actions</SectionHeader>
              <div className="px-2 pb-2">
                {items.actions.map((it, i) => {
                  const idx = items.skuMatches.length + items.viewMatches.length + i;
                  return (
                    <Item key={`a-${i}`} item={it} active={cursor === idx} onClick={() => { onPick?.(it); setOpen(false); }} />
                  );
                })}
              </div>
            </>
          )}
        </div>

        <div className="px-4 py-2 border-t border-slate-100 flex items-center gap-4 text-[10px] text-slate-500">
          <span className="flex items-center gap-1"><kbd className="px-1.5 py-0.5 rounded bg-slate-100 font-mono">↑↓</kbd> navigate</span>
          <span className="flex items-center gap-1"><kbd className="px-1.5 py-0.5 rounded bg-slate-100 font-mono">↵</kbd> open</span>
          <span className="flex items-center gap-1"><kbd className="px-1.5 py-0.5 rounded bg-slate-100 font-mono">esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}

function SectionHeader({ children }) {
  return <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold px-4 py-1.5">{children}</div>;
}

function Item({ item, active, onClick }) {
  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-3 px-2 py-2 rounded-md cursor-pointer ${active ? "bg-indigo-50" : "hover:bg-slate-50"}`}
    >
      <div className={`w-7 h-7 rounded grid place-items-center text-xs font-bold ${active ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-700"}`}>
        {item.type === "sku" ? "S" : item.type === "view" ? "V" : "▶"}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-slate-900 truncate">{item.label}</div>
        {item.sub && <div className="text-xs text-slate-500 truncate">{item.sub}</div>}
      </div>
      {active && <kbd className="px-1.5 py-0.5 rounded bg-slate-200 text-[10px] font-mono text-slate-700">↵</kbd>}
    </div>
  );
}
