/**
 * Per-module SOP content. Each export is the JSX body to drop inside
 * <SOPModal>. Content ported verbatim from V1 so operator-facing docs
 * don't change.
 */
import React from "react";

function Row({ name, desc }) {
  return (
    <tr>
      <td className="border border-slate-300 px-2 py-1 font-medium w-40">{name}</td>
      <td className="border border-slate-300 px-2 py-1">{desc}</td>
    </tr>
  );
}

function Section({ title, children }) {
  return (
    <section>
      <h3 className="text-sm font-semibold text-slate-900 mb-1">{title}</h3>
      {children}
    </section>
  );
}

/* ============================================================
   REPLENISHMENT
============================================================ */
export function ReplenishmentSOPContent() {
  return (
    <>
      <p className="text-slate-600">
        Tells you how many units to send from your <b>Mother Warehouse</b> to Amazon FBA.
        Math runs live on the latest files for all 4 accounts (Nexlev, Viomi, Audio Array, White Mulberry).
      </p>

      <Section title="Top controls">
        <ul className="list-disc pl-5 space-y-0.5 text-xs">
          <li><b>Sales Window (From → To)</b> — recent weeks used to compute weekly sales. Default 12 weeks · maximum 12.</li>
          <li><b>Replen Wks</b> — weeks of stock you want at Amazon (default 8).</li>
          <li><b>Past Week</b> — switch to a saved week (view-only).</li>
        </ul>
      </Section>

      <Section title="Columns">
        <table className="w-full text-xs border-collapse">
          <tbody>
            <Row name="Trend"        desc="12-wk sparkline + RISING / STABLE / SURGING / COOLING label" />
            <Row name="Avg/Wk"       desc="MAX of (Window avg) and (Last-4-week avg). 4wk pill shown when 4-wk drives it." />
            <Row name="4wk"          desc="Last-4-week avg only (for comparison)" />
            <Row name="Total"        desc="Units sold across the window" />
            <Row name="AZ Inv"       desc="Stock sitting at Amazon FBA (sellable)" />
            <Row name="Inbound"      desc="Already shipped to Amazon, not yet received" />
            <Row name="Mother WH"    desc="AMPM warehouse stock — what you can ship" />
            <Row name="B2B"          desc="Amazon Business B2B inventory (display only)" />
            <Row name="Req"          desc="Target stock = Avg/Wk × Replen Wks" />
            <Row name="Shortfall"    desc="Gap when Mother WH can't fully cover Req" />
            <Row name="Replen Qty"   desc="Units to ship. Never exceeds Mother WH stock." />
            <Row name="Rec Qty"      desc="Replen rounded to full Master Cartons (⚠ if carton-break)" />
            <Row name="Cartons"      desc="Whole cartons in Rec Qty (IXD = full only, non-IXD = break allowed)" />
            <Row name="Working"      desc="Editable cell, amber background. Auto-saves as you type." />
          </tbody>
        </table>
      </Section>

      <Section title="Account rules">
        <ul className="list-disc pl-5 space-y-0.5 text-xs">
          <li><b>Nexlev / Viomi / White Mulberry</b> → counts <b>Amazon + 1p Sales</b> only</li>
          <li><b>Audio Array</b> → counts <b>Amazon only</b> (1p Sales excluded)</li>
          <li>Nexlev and Viomi <b>share the same sales</b> (both tagged "Nexlev" brand)</li>
          <li>Models in sales but missing from the master file are silently dropped</li>
        </ul>
      </Section>

      <Section title="4-week velocity bump">
        <p className="text-xs">
          When the <b>last 4 weeks' average</b> exceeds the selected-window average,
          the system uses the higher number so recent demand spikes flow into Replen
          Qty. Applied uniformly across all 5 accounts.
        </p>
      </Section>

      <Section title="Example">
        <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
          Sold 80 over 4 weeks → AVG/WK 20 → 8-wk target 160 → Amazon has 50 → need 110 →
          Mother WH has 200 → <b>Replen = 110</b>.
          <br/>
          If Mother WH only had 70 → Replen = 70, Shortfall = 40 (raise a China PO for 40).
        </p>
      </Section>

      <Section title="Working column + save">
        <ul className="list-disc pl-5 space-y-0.5 text-xs">
          <li>Auto-saves as you type</li>
          <li>Week runs Sun → Sat; <b>locks at Saturday 11:59 PM IST</b></li>
          <li>Past weeks are view-only via the dropdown</li>
          <li>Drag any numeric cells (Excel-style) → footer shows sum → ⌘C copies as TSV</li>
        </ul>
      </Section>
    </>
  );
}

/* ============================================================
   FC ALLOCATION
============================================================ */
export function FCAllocationSOPContent() {
  return (
    <>
      <p className="text-slate-600">
        Plans how much of each SKU to send to each Amazon Fulfillment Center based on
        per-FC velocity, current stock, and target weeks of cover.
      </p>

      <Section title="Top controls">
        <ul className="list-disc pl-5 space-y-0.5 text-xs">
          <li><b>Account</b> — pick brand (Fossil uses its own assortment + cluster flow)</li>
          <li><b>Sales Window (Range)</b> — ISO week range over the per-week FBA Sales folders</li>
          <li><b>Replen Wks</b> — weeks of cover the planner wants at each FC</li>
          <li><b>Channel</b> — All / Amazon.in / D2C (MCF / Non-Amazon)</li>
        </ul>
      </Section>

      <Section title="Columns (non-Fossil)">
        <table className="w-full text-xs border-collapse">
          <tbody>
            <Row name="FC"            desc="Amazon Fulfillment Center code (BLR5, BOM4, …)" />
            <Row name="FC SOH"        desc="Current stock at that FC" />
            <Row name="Mother WH"     desc="AMPM warehouse balance for the SKU" />
            <Row name="B2B Inv"       desc="B2B-AMPM stock (display only)" />
            <Row name="Avg/Wk"        desc="Weekly velocity computed per-FC over the selected window" />
            <Row name="Target"        desc="FC SOH target = Avg/Wk × Replen Wks (governance applied)" />
            <Row name="Required"      desc="Pre-transfer expected need" />
            <Row name="To Send QTY"   desc="Final ship quantity from Mother WH to this FC" />
            <Row name="Fill %"        desc="Fill rate of Required against capacity" />
            <Row name="Vel Flag"      desc="STABLE / SHORT_30%+ / NO_SALES, etc." />
          </tbody>
        </table>
      </Section>

      <Section title="Fossil-specific">
        <ul className="list-disc pl-5 space-y-0.5 text-xs">
          <li><b>Cluster</b> — BLR/BOM/TN/DEL/TEL/WB (FC grouping)</li>
          <li><b>PO Req</b> — editable per (SKU, FC) row</li>
          <li><b>Cluster PO</b> — editable per (SKU, cluster); auto-calculated initially</li>
          <li><b>In-Transit / Open PO</b> — net against the cluster's combined target</li>
          <li><b>Remarks</b> — editable text per row; saved to DB</li>
        </ul>
      </Section>

      <Section title="Example (Nexlev, IXD)">
        <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
          Sold 800 over 12 weeks at MAA4 → Velocity 67/wk → 8-wk target 533 → FC has 100 + Transfer-In 50 →
          Adjusted Shortfall 383 → IXD governance × 0.35 → <b>Send 134</b>, Fill 35% → flagged SHORT_30%+
        </p>
      </Section>
    </>
  );
}

/* ============================================================
   CB REPLENISHMENT
============================================================ */
export function CBReplenishmentSOPContent() {
  return (
    <>
      <p className="text-slate-600">
        CB (Cambium) Replenishment plans 1P / Vendor restock per model based on combined
        CB + Cambium 3-month sales and current 1P inventory.
      </p>

      <Section title="Top controls">
        <ul className="list-disc pl-5 space-y-0.5 text-xs">
          <li><b>Sales Window (Range)</b> — ISO weeks for sales aggregation</li>
          <li><b>Cover Wks</b> — desired weeks of CB stock (default 8)</li>
          <li><b>Brand</b> — filter to one brand or All</li>
          <li><b>Past Week</b> — switch to a saved snapshot</li>
        </ul>
      </Section>

      <Section title="Columns">
        <table className="w-full text-xs border-collapse">
          <tbody>
            <Row name="CB 3M"           desc="Last 3 months 1p Sales channel units" />
            <Row name="Cambium 3M"      desc="Last 3 months Amazon channel units" />
            <Row name="Avg/Wk"          desc="(CB 3M + Cambium 3M) ÷ window weeks" />
            <Row name="CB Inv"          desc="1P inventory currently with Amazon Vendor" />
            <Row name="Mother WH"       desc="AMPM stock available to ship" />
            <Row name="China IT"        desc="Stock in transit from China (Pipeline channel)" />
            <Row name="Open PO / IT"    desc="PO statuses from In-Transit PO file" />
            <Row name="Estimated"       desc="Avg/Wk × Cover Wks" />
            <Row name="Deficiency"      desc="Estimated − CB Inv (clipped at 0)" />
            <Row name="PO Req"          desc="Deficiency − (Open PO + In-Transit)" />
            <Row name="ASIN Sort"       desc="IXD / Non-IXD detail (stored in master's Hazmat Type column)" />
            <Row name="Working"         desc="Editable. Auto-saves 500ms after typing stops." />
            <Row name="Remarks"         desc="Editable notes per model" />
          </tbody>
        </table>
      </Section>

      <Section title="Attribution cascade">
        <p className="text-xs">
          Sales/inventory join via ASIN first → SKU → Model. Each level exclusive
          so duplicate-Model master rows can't double-count the same pool.
        </p>
      </Section>
    </>
  );
}

/* ============================================================
   CLICKTECH (WM)
============================================================ */
export function WMReplenishmentSOPContent() {
  return (
    <>
      <p className="text-slate-600">
        Clicktech (White Mulberry) replenishment plans 1P restock. Same engine as CB
        but the sales mix is CB + Amazon (not Cambium).
      </p>

      <Section title="Columns">
        <table className="w-full text-xs border-collapse">
          <tbody>
            <Row name="CB 3M"        desc="Last 3 months 1p Sales channel" />
            <Row name="Amazon 3M"    desc="Last 3 months Amazon channel" />
            <Row name="Avg/Wk"       desc="Combined average per week" />
            <Row name="CB Inv"       desc="1P inventory at Amazon Vendor" />
            <Row name="Mother WH"    desc="AMPM stock balance" />
            <Row name="Estimated"    desc="Avg/Wk × Cover Wks" />
            <Row name="Deficiency"   desc="Estimated − CB Inv (clipped at 0)" />
            <Row name="PO Req"       desc="Editable. Saves on blur." />
            <Row name="Remarks"      desc="Editable notes per model" />
            <Row name="Hazmat"       desc="Amber pill if hazardous; required for FBA shipping rules" />
          </tbody>
        </table>
      </Section>
    </>
  );
}

/* ============================================================
   FOSSIL
============================================================ */
export function FossilReplenishmentSOPContent() {
  return (
    <>
      <p className="text-slate-600">
        Fossil group (Fossil / Armani Exchange / Michael Kors / Emporio Armani / Diesel / Skagen)
        replenishment from Cambium SOH to Fossil's FCY warehouse. Required Inventory is governed
        by the per-brand × assortment WOC (Weeks of Cover) matrix.
      </p>

      <Section title="WOC Matrix (target weeks of cover)">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50">
              <th className="border border-slate-300 px-2 py-1 text-left">Brand</th>
              <th className="border border-slate-300 px-2 py-1">FP</th>
              <th className="border border-slate-300 px-2 py-1">Discount</th>
              <th className="border border-slate-300 px-2 py-1">VD</th>
            </tr>
          </thead>
          <tbody>
            <Row name="Fossil"          desc="9 / 4 / 6" />
            <Row name="Armani Exchange" desc="6 / 4 / 6" />
            <Row name="Michael Kors"    desc="6 / 4 / 6" />
            <Row name="Emporio Armani"  desc="4 / 4 / 6" />
            <Row name="Diesel"          desc="4 / 4 / 6" />
            <Row name="Skagen"          desc="4 / 4 / 6" />
          </tbody>
        </table>
      </Section>

      <Section title="Columns">
        <table className="w-full text-xs border-collapse">
          <tbody>
            <Row name="Assortment Type" desc="FP (full price) / Discount / VD (visual display)" />
            <Row name="3M Gross"        desc="Last 3 months gross sales" />
            <Row name="Weekly Avg"      desc="Fossil Weekly Sales (window avg)" />
            <Row name="4wk Top"         desc="Last 4 weeks top average — used for FP/Discount uplift if higher" />
            <Row name="Cambium SOH"     desc="Cambium-side stock available" />
            <Row name="Andheri/Gor"     desc="Sellable stock at Andheri / Goregaon FCs" />
            <Row name="In Transit / Open PO" desc="Pipeline to Fossil's FCY" />
            <Row name="Total Inv"       desc="All four inventory buckets summed" />
            <Row name="Fossil SOH"      desc="What's at Fossil's FCY right now" />
            <Row name="Required"        desc="Weekly Avg × WOC target (uplift for FP/Discount when 4wk > Weekly)" />
            <Row name="Replen Qty"      desc="Required − Total Inv (red if &gt; 0)" />
          </tbody>
        </table>
      </Section>

      <Section title="VD assortment">
        <p className="text-xs">
          VD (visual display) rows hide the 4wk top average — VD doesn't use the uplift rule.
        </p>
      </Section>
    </>
  );
}

/* ============================================================
   REORDER INTELLIGENCE (China Reorder)
============================================================ */
export function ChinaReorderSOPContent() {
  return (
    <>
      <p className="text-slate-600">
        Reorder Intelligence suggests new China POs based on 12-week sales velocity,
        current inventory, in-transit pipeline, and Weeks of Cover thresholds.
      </p>

      <Section title="Top controls">
        <ul className="list-disc pl-5 space-y-0.5 text-xs">
          <li><b>Brands</b> — multi-select chips (toggle each)</li>
          <li><b>Months</b> — historical sales window (default 3)</li>
          <li><b>L0 / L1</b> — cascading category drill-down</li>
        </ul>
      </Section>

      <Section title="Status (derived from Weeks of Cover)">
        <table className="w-full text-xs border-collapse">
          <tbody>
            <Row name="CRITICAL"   desc="Cover &lt; 12 weeks. Raise a China PO immediately." />
            <Row name="MODERATE"   desc="Cover 12–16 weeks. Watch closely; may need PO soon." />
            <Row name="NO REORDER" desc="Cover &gt; 16 weeks. Sufficient stock for now." />
          </tbody>
        </table>
      </Section>

      <Section title="Columns">
        <table className="w-full text-xs border-collapse">
          <tbody>
            <Row name="12W Sales"        desc="Units sold in last 12 weeks" />
            <Row name="Avg/Wk"           desc="12W Sales ÷ 12" />
            <Row name="Inventory"        desc="Current stock on hand" />
            <Row name="PO Yet to Pickup" desc="Open orders not yet picked up from supplier" />
            <Row name="PO Picked Up"     desc="Picked up, in-transit pipeline" />
            <Row name="Cover (wk)"       desc="Stock + Pipeline ÷ Avg/Wk · color-coded by status" />
            <Row name="Reorder"          desc="Suggested new PO quantity" />
            <Row name="Rating / Reviews" desc="Amazon product rating + count" />
            <Row name="Returns %"        desc="Return rate · amber &gt;10%, red &gt;20%" />
            <Row name="Margin ₹ / %"     desc="Net margin per unit (₹) and as %" />
          </tbody>
        </table>
      </Section>
    </>
  );
}
