import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { Activity, Users, MousePointerClick, Save, Download } from "lucide-react";

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

const MODULE_LABELS = {
  "dashboard":              "Dashboard",
  "replenishment":          "Replenishment",
  "fc-allocation":          "FC Allocation",
  "sales-analytics":        "Sales Analytics",
  "region-sales":           "Region Sales",
  "china-reorder":          "China Reorder",
  "china-reorder-working":  "China Reorder Working",
  "cb-replenishment":       "CB Replenishment",
  "wm-replenishment":       "Clicktech Replenishment",
  "fossil-replenishment":   "Fossil Replenishment",
};

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function UsageAnalytics() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const authHeader = useMemo(() => ({ "x-admin-email": user?.email || "" }), [user]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${BASE}/usage/summary`, { headers: authHeader });
      const j = await res.json();
      if (j.status === "ok") {
        setData(j);
      } else {
        setError(j.detail || j.error || "Failed to load usage data");
      }
    } catch (e) {
      setError("Could not reach the server");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const overview = data?.overview || {};
  const byUser   = data?.by_user || [];
  const byModule = data?.by_module || [];
  const byDay    = data?.by_day || [];

  const maxDay = Math.max(1, ...byDay.map(d => d.events || 0));

  return (
    <div className="space-y-4">
      {/* HEADER */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white shadow-sm shadow-indigo-500/20">
            <Activity size={15} />
          </div>
          <div>
            <h1 className="text-[15px] font-semibold text-zinc-900 tracking-tight leading-tight">Usage Analytics</h1>
            <p className="text-[11px] text-zinc-500">Who's using the tool, how often, and on which modules.</p>
          </div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="px-3 py-1.5 text-xs font-medium text-zinc-700 bg-white border border-zinc-200 rounded-md hover:border-zinc-400 transition disabled:opacity-50"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500 flex-shrink-0"></span>
          {error}
        </div>
      )}

      {/* OVERVIEW */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatTile icon={Activity}     label="Total events"       value={overview.total_events ?? 0}   hint={`Lifetime`} accent="indigo" />
        <StatTile icon={Users}        label="Active (7 days)"    value={overview.active_users_7d ?? 0} hint={`${overview.active_users_30d ?? 0} in last 30 days`} accent="emerald" />
        <StatTile icon={MousePointerClick} label="Events (24h)"   value={overview.events_24h ?? 0}     hint={`${overview.events_7d ?? 0} in last 7 days`} accent="amber" />
        <StatTile icon={Save}         label="Unique users ever"  value={overview.unique_users ?? 0}    hint={`across all logins`} accent="zinc" />
      </div>

      {/* DAILY TIMELINE — last 30 days bars */}
      <div className="bg-white border border-zinc-200 rounded-lg shadow-sm">
        <div className="px-3 py-2.5 border-b border-zinc-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Last 30 days</div>
            <div className="text-sm font-semibold text-zinc-900">Activity timeline</div>
          </div>
          <div className="text-[11px] text-zinc-500 tabular-nums">{byDay.length} day{byDay.length !== 1 ? "s" : ""} with activity</div>
        </div>
        <div className="p-3">
          {byDay.length === 0 ? (
            <div className="text-xs text-zinc-400 italic py-6 text-center">No activity recorded yet.</div>
          ) : (
            <div className="flex items-end gap-[3px] h-24">
              {byDay.map(d => {
                const h = Math.max(2, Math.round((d.events / maxDay) * 100));
                return (
                  <div key={d.day} className="flex-1 flex flex-col items-center gap-0.5 group min-w-0">
                    <div
                      style={{ height: `${h}%` }}
                      className="w-full bg-indigo-200 hover:bg-indigo-500 transition-colors rounded-sm relative"
                      title={`${d.day} · ${d.events} events · ${d.users} users`}
                    >
                      <div className="absolute -top-7 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition pointer-events-none whitespace-nowrap text-[10px] bg-zinc-900 text-white px-1.5 py-0.5 rounded">
                        {d.events}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* PER USER */}
      <div className="bg-white border border-zinc-200 rounded-lg shadow-sm overflow-hidden">
        <div className="px-3 py-2.5 border-b border-zinc-200">
          <div className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Per user</div>
          <div className="text-sm font-semibold text-zinc-900">{byUser.length} user{byUser.length !== 1 ? "s" : ""} have used the tool</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-[10px] uppercase tracking-[0.06em] text-zinc-600 border-b border-zinc-200">
              <tr>
                <th className="text-left  px-3 py-2 font-semibold">User</th>
                <th className="text-right px-3 py-2 font-semibold">Logins</th>
                <th className="text-right px-3 py-2 font-semibold">Page views</th>
                <th className="text-right px-3 py-2 font-semibold">Saves</th>
                <th className="text-right px-3 py-2 font-semibold">Exports</th>
                <th className="text-right px-3 py-2 font-semibold">Total</th>
                <th className="text-left  px-3 py-2 font-semibold">Last activity</th>
              </tr>
            </thead>
            <tbody>
              {byUser.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-6 text-center text-zinc-400 text-xs">No usage recorded yet.</td></tr>
              )}
              {byUser.map(u => (
                <tr key={u.email} className="border-b border-zinc-100 last:border-0 hover:bg-zinc-50/60">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-6 w-6 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-[10px] font-bold shadow-sm shadow-indigo-500/20">
                        {(u.email || "").slice(0,2).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <div className="text-[12px] font-medium text-zinc-900 leading-tight">{u.name || u.email}</div>
                        <div className="text-[10px] text-zinc-500 leading-tight">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-zinc-700">{u.logins}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-zinc-700">{u.page_views}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold text-indigo-700">{u.saves}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold text-emerald-700">{u.exports}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold text-zinc-900">{u.total}</td>
                  <td className="px-3 py-2 text-[11px] text-zinc-500">{formatDate(u.last_activity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* PER MODULE */}
      <div className="bg-white border border-zinc-200 rounded-lg shadow-sm overflow-hidden">
        <div className="px-3 py-2.5 border-b border-zinc-200">
          <div className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Per module</div>
          <div className="text-sm font-semibold text-zinc-900">Which modules are getting used</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-[10px] uppercase tracking-[0.06em] text-zinc-600 border-b border-zinc-200">
              <tr>
                <th className="text-left  px-3 py-2 font-semibold">Module</th>
                <th className="text-right px-3 py-2 font-semibold">Events</th>
                <th className="text-right px-3 py-2 font-semibold">Unique users</th>
                <th className="text-left  px-3 py-2 font-semibold">Last activity</th>
              </tr>
            </thead>
            <tbody>
              {byModule.length === 0 && (
                <tr><td colSpan={4} className="px-3 py-6 text-center text-zinc-400 text-xs">No module activity yet.</td></tr>
              )}
              {byModule.map(m => (
                <tr key={m.module} className="border-b border-zinc-100 last:border-0 hover:bg-zinc-50/60">
                  <td className="px-3 py-2 text-zinc-800 font-medium">{MODULE_LABELS[m.module] || m.module}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold text-zinc-900">{m.total}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-zinc-700">{m.users}</td>
                  <td className="px-3 py-2 text-[11px] text-zinc-500">{formatDate(m.last_activity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


function StatTile({ icon: Icon, label, value, hint, accent = "indigo" }) {
  const accentMap = {
    indigo:  { bar: "bg-indigo-500",  ic: "text-indigo-600",  tile: "from-indigo-50/40" },
    emerald: { bar: "bg-emerald-500", ic: "text-emerald-600", tile: "from-emerald-50/40" },
    amber:   { bar: "bg-amber-500",   ic: "text-amber-600",   tile: "from-amber-50/40" },
    zinc:    { bar: "bg-zinc-400",    ic: "text-zinc-500",    tile: "from-zinc-50/40" },
  };
  const c = accentMap[accent] || accentMap.zinc;
  return (
    <div className={`relative bg-white border border-zinc-200 rounded-lg shadow-sm overflow-hidden bg-gradient-to-br ${c.tile} to-transparent`}>
      <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${c.bar}`}></div>
      <div className="px-3.5 py-2.5 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">{label}</div>
          <div className="tabular-nums text-2xl font-semibold text-zinc-900 leading-tight mt-0.5">{value}</div>
          {hint && <div className="text-[10.5px] text-zinc-500 mt-0.5">{hint}</div>}
        </div>
        <Icon size={16} className={`${c.ic} flex-shrink-0 mt-0.5`} />
      </div>
    </div>
  );
}
