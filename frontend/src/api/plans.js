// API client for the plan approval workflow.
// All calls send the auth Bearer token; caller handles 401/403 → login redirect.

const STORAGE_KEY = "am_repl_auth_v2";
// Same-origin: SPA is now served by the FastAPI backend, so /api/*
// resolves to the same host as the page. No CORS handshake needed.
// Dev fallback: use VITE_API_BASE when running vite dev locally
// (import.meta.env.DEV is true only during `vite dev`, false in build).
const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";
const P = "/api/plans";

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

export function proposePlan({ account, week_tag, rows, source_module, approver_email, as_draft, cover_weeks, filter_context }) {
  return req("POST", `${P}/propose`, {
    account, week_tag, rows, source_module, approver_email, as_draft, cover_weeks, filter_context,
  });
}

export function saveDraft({ account, week_tag, rows, source_module, approver_email, cover_weeks, filter_context }) {
  return req("POST", `${P}/save-draft`, {
    account, week_tag, rows, source_module, approver_email, cover_weeks, filter_context,
  });
}

export function requestRework(batchId, feedback) {
  return req("POST", `${P}/${encodeURIComponent(batchId)}/request-rework`, { feedback });
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

export function editLine(batchId, lineId, { qty, notes, approver_note, exclude_from_push, row_version }) {
  const body = { row_version };
  if (qty !== undefined)                body.qty = qty;
  if (notes !== undefined)              body.notes = notes;
  if (approver_note !== undefined)      body.approver_note = approver_note;
  if (exclude_from_push !== undefined)  body.exclude_from_push = exclude_from_push;
  return req("PATCH", `${P}/${encodeURIComponent(batchId)}/lines/${lineId}`, body);
}

export function addLine(batchId, payload) {
  return req("POST", `${P}/${encodeURIComponent(batchId)}/lines`, payload);
}

export function deleteLine(batchId, lineId) {
  return req("DELETE", `${P}/${encodeURIComponent(batchId)}/lines/${lineId}`);
}

export function deletePlan(batchId) {
  return req("DELETE", `${P}/${encodeURIComponent(batchId)}`);
}

export function approvePlan(batchId) {
  return req("POST", `${P}/${encodeURIComponent(batchId)}/approve`);
}

export function pushPlan(batchId, { dryRun = false } = {}) {
  const qs = dryRun ? "?dry_run=true" : "";
  return req("POST", `${P}/${encodeURIComponent(batchId)}/push${qs}`);
}
