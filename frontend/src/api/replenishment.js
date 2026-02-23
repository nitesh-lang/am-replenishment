const BASE = "http://127.0.0.1:8060";

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
  return fetchJSON(`${BASE}/kpis?weeks=${weeks}`);
}

/* =========================================================
   FC FINAL ALLOCATION (AMPM → FC)
   ========================================================= */
export async function getFCFinal(replenishWeeks, channel) {
  return fetchJSON(
    `${BASE}/fc-final-allocation?replenish_weeks=${replenishWeeks}&channel=${channel}`
  );
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