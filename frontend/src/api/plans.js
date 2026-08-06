// API client for the plan approval workflow.
// All calls send the auth Bearer token; caller handles 401/403 → login redirect.

const STORAGE_KEY = "am_repl_auth_v2";
// Use a RELATIVE URL so the browser sees the request as same-origin.
// The frontend's _redirects proxies /api/* to the backend, which means
// no CORS handshake is needed at all — bulletproof against browsers,
// ISPs, and proxies that mishandle CORS headers.
const P = "/api/plans";
// Dev fallback: when running Vite locally without the redirect proxy,
// hop straight to the API host. In prod, VITE_API_BASE is unset so BASE
// is "" and requests go relative to the frontend's origin.
const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";

function token() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}").token || "";
  } catch {
    return "";
  }
}

async function req(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token()}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = j.detail || j.error || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    err.body = j;
    throw err;
  }
  return j;
}

export function proposePlan({ account, week_tag, rows, source_module, approver_email, as_draft }) {
  return req("POST", `${P}/propose`, {
    account, week_tag, rows, source_module, approver_email, as_draft,
  });
}

export function saveDraft({ account, week_tag, rows, source_module, approver_email }) {
  return req("POST", `${P}/save-draft`, {
    account, week_tag, rows, source_module, approver_email,
  });
}

export function sendToApprover(batchId) {
  return req("POST", `${P}/${encodeURIComponent(batchId)}/send`);
}

export function listPlans({ account, status, limit = 50 } = {}) {
  const p = new URLSearchParams();
  if (account) p.set("account", account);
  if (status) p.set("status", status);
  p.set("limit", String(limit));
  return req("GET", `${P}?${p.toString()}`);
}

export function getPlan(batchId, { includeDeleted = true } = {}) {
  return req("GET", `${P}/${encodeURIComponent(batchId)}?include_deleted=${includeDeleted}`);
}

export function editLine(batchId, lineId, { qty, row_version }) {
  return req("PATCH", `${P}/${encodeURIComponent(batchId)}/lines/${lineId}`, {
    qty,
    row_version,
  });
}

export function addLine(batchId, payload) {
  return req("POST", `${P}/${encodeURIComponent(batchId)}/lines`, payload);
}

export function deleteLine(batchId, lineId) {
  return req("DELETE", `${P}/${encodeURIComponent(batchId)}/lines/${lineId}`);
}

export function approvePlan(batchId) {
  return req("POST", `${P}/${encodeURIComponent(batchId)}/approve`);
}

export function pushPlan(batchId) {
  return req("POST", `${P}/${encodeURIComponent(batchId)}/push`);
}
