const BASE = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE || "http://localhost:8060") : "";
const STORAGE_KEY = "am_repl_auth_v2";

function getEmail() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw).email || null;
  } catch {
    return null;
  }
}

/**
 * Fire-and-forget usage logger. Never throws, never blocks the UI.
 *
 * @param {string} eventType  e.g. 'login', 'page_view', 'save', 'export'
 * @param {string} module     e.g. 'replenishment', 'cb-replenishment'
 * @param {object} [detail]   optional extra context (account, week, row count…)
 */
export function logUsage(eventType, module, detail = {}) {
  if (!eventType) return;
  const email = getEmail();
  try {
    fetch(`${BASE}/usage/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_email: email,
        event_type: eventType,
        module: module || null,
        detail,
      }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // swallow
  }
}
