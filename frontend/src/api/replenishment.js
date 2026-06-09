const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

/* =========================================================
   GENERIC FETCH HELPER
   ========================================================= */
async function fetchJSON(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response.json(); 
}

/* =========================================================
   REPLENISHMENT
   - sales_window → past weeks for velocity
   - replenish_weeks → future weeks projection
   ========================================================= */
export async function getReplenishment(salesWindow, replenishWeeks, account) {
  return fetchJSON(
    `${BASE}/replenishment?sales_window=${salesWindow}&replenish_weeks=${replenishWeeks}&account=${account}`
  );
}

/* =========================================================
   KPIs
   ========================================================= */
export async function getKPIs(weeks) {
  return fetchJSON(`${BASE}/kpis/?weeks=${weeks}`);
}

/* =========================================================
   FC FINAL ALLOCATION (AMPM → FC)
   - fromWeek / toWeek (ISO week numbers) define the sales-window range.
   - salesWindow is kept as a fallback when no range is provided.
   ========================================================= */
export async function getFCFinal(
  replenishWeeks,
  channel,
  account,
  salesWindow = 12,
  fromWeek = null,
  toWeek = null,
) {
  const params = new URLSearchParams({
    replenish_weeks: replenishWeeks,
    channel,
    account,
    sales_window: salesWindow,
  });
  if (fromWeek != null && toWeek != null) {
    params.set("from_week", fromWeek);
    params.set("to_week", toWeek);
  }
  return fetchJSON(`${BASE}/fc-final-allocation?${params.toString()}`);
}

/* =========================================================
   DASHBOARD – RISKY MODELS
   ========================================================= */
export async function getRiskyModels(weeks) {
  return fetchJSON(
    `${BASE}/dashboard/risky-models?weeks=${weeks}`
  );
}

/* =========================================================
   DASHBOARD – OVERSTOCK
   ========================================================= */
export async function getOverstock(weeks) {
  return fetchJSON(
    `${BASE}/dashboard/overstock?weeks=${weeks}`
  );
}