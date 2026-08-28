/* ============================================================
   Editable-cell styling (operator 2026-08-28: the edit columns
   "should look not that good and experience is timid").

   Two principles, applied to every inline-editable input across
   the replenishment pages:

   1. At REST the grid should read as data — a quiet dashed
      underline marks "this is editable" without boxing every
      row in input chrome.
   2. On HOVER/FOCUS the cell must be unmistakably an input —
      it lifts to a white card with a visible border and ring,
      so the operator never wonders whether typing will work.

   EDIT_CELL_PRIMARY is for the page's MAIN input (the Working
   column): amber identity kept from the old design, but larger,
   with a real focus state instead of a static tinted box.

   Styling only — every input keeps its existing value/save
   handlers untouched.
============================================================ */
export const EDIT_CELL =
  "rounded-md border bg-transparent transition-all cursor-text " +
  "border-transparent border-b-slate-300 [border-bottom-style:dashed] " +
  "hover:bg-white hover:border-slate-300 hover:shadow-sm hover:[border-bottom-style:solid] " +
  "focus:outline-none focus:bg-white focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 focus:[border-bottom-style:solid] " +
  "disabled:cursor-not-allowed disabled:opacity-60";

export const EDIT_CELL_PRIMARY =
  "rounded-md border transition-all cursor-text font-semibold " +
  "bg-amber-50/70 border-amber-300 " +
  "hover:bg-white hover:border-amber-400 hover:shadow-sm " +
  "focus:outline-none focus:bg-white focus:border-amber-500 focus:ring-2 focus:ring-amber-200 " +
  "disabled:cursor-not-allowed disabled:opacity-60";
