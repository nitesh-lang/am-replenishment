import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { Users, Plus, Pencil, Trash2, X, Check, Shield, User as UserIcon, KeyRound, Eye, EyeOff } from "lucide-react";

const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

const MODULE_LABELS = {
  "dashboard":              "Dashboard",
  "replenishment":          "Replenishment",
  "fc-allocation":          "FC Allocation",
  "sales-analytics":        "Sales Analytics",
  "region-sales":           "Region Sales",
  "china-reorder":          "China Reorder",
  "cb-replenishment":       "CB Replenishment",
  "wm-replenishment":       "Clicktech Replenishment",
  "fossil-replenishment":   "Fossil Replenishment",
  "blinkit-replenishment":  "Blinkit Replenishment",
};

export default function Admin() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [modules, setModules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null); // user object or {} for new
  const [resetting, setResetting] = useState(null); // user object for password reset

  const authHeader = useMemo(
    () => (user?.token ? { Authorization: `Bearer ${user.token}` } : {}),
    [user]
  );

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${BASE}/admin/users`, { headers: authHeader });
      const j = await res.json();
      if (j.status === "ok") {
        setUsers(j.users || []);
        setModules(j.modules || []);
      } else {
        setError(j.error || "Failed to load users");
      }
    } catch (e) {
      setError("Could not reach the server");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function saveUser(payload) {
    setError("");
    try {
      const res = await fetch(`${BASE}/admin/users`, {
        method: "POST",
        headers: { ...authHeader, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const j = await res.json();
      if (!res.ok) {
        setError(j.detail || j.error || "Save failed");
        return false;
      }
      await load();
      return true;
    } catch (e) {
      setError("Save failed");
      return false;
    }
  }

  async function deleteUser(email) {
    if (!window.confirm(`Delete user ${email}? This cannot be undone.`)) return;
    setError("");
    try {
      const res = await fetch(`${BASE}/admin/users/${encodeURIComponent(email)}`, {
        method: "DELETE",
        headers: authHeader,
      });
      const j = await res.json();
      if (!res.ok) {
        setError(j.detail || j.error || "Delete failed");
        return;
      }
      await load();
    } catch (e) {
      setError("Delete failed");
    }
  }

  return (
    <div className="space-y-4">
      {/* HEADER */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white shadow-sm shadow-indigo-500/20">
            <Users size={15} />
          </div>
          <div>
            <h1 className="text-[15px] font-semibold text-zinc-900 tracking-tight leading-tight">User Management</h1>
            <p className="text-[11px] text-zinc-500">Add, edit and remove users. Control which modules each user can see.</p>
          </div>
        </div>
        <button
          onClick={() => setEditing({})}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-semibold bg-zinc-900 text-white rounded-md hover:bg-zinc-800 shadow-sm transition"
        >
          <Plus size={14} />
          Add User
        </button>
      </div>

      {error && (
        <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-red-500 flex-shrink-0"></span>
          {error}
        </div>
      )}

      {/* USER LIST */}
      <div className="bg-white border border-zinc-200 rounded-lg shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 border-b border-zinc-200 text-[10px] uppercase tracking-[0.06em] text-zinc-600">
            <tr>
              <th className="text-left px-3 py-2.5 font-semibold">User</th>
              <th className="text-left px-3 py-2.5 font-semibold">Role</th>
              <th className="text-left px-3 py-2.5 font-semibold">Modules</th>
              <th className="text-right px-3 py-2.5 font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-zinc-400 text-xs">Loading…</td></tr>
            )}
            {!loading && users.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-zinc-400 text-xs">No users.</td></tr>
            )}
            {users.map(u => (
              <tr key={u.email} className="border-b border-zinc-100 last:border-0 hover:bg-zinc-50/60">
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-2.5">
                    <div className="h-7 w-7 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-[10px] font-bold shadow-sm shadow-indigo-500/20">
                      {(u.email || "").slice(0,2).toUpperCase()}
                    </div>
                    <div>
                      <div className="text-[13px] font-medium text-zinc-900">{u.name || "—"}</div>
                      <div className="text-[11px] text-zinc-500">{u.email}</div>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2.5">
                  {u.role === "admin" ? (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-violet-50 text-violet-700 border border-violet-200 rounded">
                      <Shield size={10} />
                      Admin
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-zinc-50 text-zinc-600 border border-zinc-200 rounded">
                      <UserIcon size={10} />
                      User
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  {u.role === "admin" ? (
                    <span className="text-[11px] text-zinc-500 italic">All modules (admin)</span>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {(u.allowed_modules || []).length === 0 && (
                        <span className="text-[11px] text-zinc-400 italic">No access</span>
                      )}
                      {(u.allowed_modules || []).map(m => (
                        <span key={m} className="text-[10px] px-1.5 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded">
                          {MODULE_LABELS[m] || m}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <div className="inline-flex items-center gap-1">
                    <button
                      onClick={() => setResetting(u)}
                      className="p-1.5 rounded text-zinc-500 hover:text-indigo-600 hover:bg-indigo-50 transition"
                      title="Reset password"
                    >
                      <KeyRound size={14} />
                    </button>
                    <button
                      onClick={() => setEditing(u)}
                      className="p-1.5 rounded text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 transition"
                      title="Edit"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => deleteUser(u.email)}
                      className="p-1.5 rounded text-zinc-500 hover:text-red-600 hover:bg-red-50 transition"
                      title="Delete"
                      disabled={u.email === user?.email}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <UserEditModal
          initial={editing}
          modules={modules}
          isExisting={!!editing.email}
          onSave={async (payload) => {
            const ok = await saveUser(payload);
            if (ok) setEditing(null);
          }}
          onClose={() => setEditing(null)}
        />
      )}

      {resetting && (
        <PasswordResetModal
          user={resetting}
          onSave={async (newPassword) => {
            const ok = await saveUser({
              email: resetting.email,
              name: resetting.name || "",
              password: newPassword,
              role: resetting.role,
              allowed_modules: resetting.allowed_modules || [],
            });
            if (ok) setResetting(null);
          }}
          onClose={() => setResetting(null)}
        />
      )}
    </div>
  );
}


function PasswordResetModal({ user, onSave, onClose }) {
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    if (pw.length < 6) {
      setErr("Password must be at least 6 characters.");
      return;
    }
    if (pw !== confirm) {
      setErr("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    await onSave(pw);
    setSubmitting(false);
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-sm flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-md bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <KeyRound size={14} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-zinc-900 leading-tight">Reset password</h2>
              <p className="text-[11px] text-zinc-500 leading-tight mt-0.5 truncate max-w-[220px]">{user.email}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 text-zinc-400 hover:text-zinc-700 rounded">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={submit} className="p-4 space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">New password</label>
            <div className="relative mt-1">
              <input
                type={show ? "text" : "password"}
                value={pw}
                onChange={e => setPw(e.target.value)}
                autoFocus
                required
                placeholder="Min 6 characters"
                className="w-full pl-2.5 pr-9 py-1.5 text-sm bg-zinc-50 border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 focus:bg-white transition-colors"
              />
              <button
                type="button"
                onClick={() => setShow(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-700 p-1"
                tabIndex={-1}
              >
                {show ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Confirm password</label>
            <input
              type={show ? "text" : "password"}
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              required
              placeholder="Re-enter"
              className="mt-1 w-full px-2.5 py-1.5 text-sm bg-zinc-50 border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 focus:bg-white transition-colors"
            />
          </div>

          {err && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-2.5 py-1.5 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-red-500 flex-shrink-0"></span>
              {err}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-sm bg-white text-zinc-700 border border-zinc-200 rounded-md hover:border-zinc-400"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-3 py-1.5 text-sm font-semibold bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
            >
              <Check size={13} />
              {submitting ? "Saving…" : "Update password"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


function UserEditModal({ initial, modules, isExisting, onSave, onClose }) {
  const [email, setEmail] = useState(initial.email || "");
  const [name, setName]   = useState(initial.name || "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(initial.role || "user");
  const [allowed, setAllowed] = useState(initial.allowed_modules || []);

  function toggle(mod) {
    setAllowed(prev => prev.includes(mod) ? prev.filter(x => x !== mod) : [...prev, mod]);
  }

  function submit(e) {
    e.preventDefault();
    onSave({
      email: email.trim(),
      name: name.trim(),
      password: password || undefined,
      role,
      allowed_modules: role === "admin" ? modules : allowed,
    });
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-zinc-200">
          <h2 className="text-base font-semibold text-zinc-900">
            {isExisting ? "Edit user" : "Add user"}
          </h2>
          <button onClick={onClose} className="p-1 text-zinc-400 hover:text-zinc-700 rounded">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={submit} className="overflow-auto flex-1 min-h-0 p-4 space-y-3">

          <div>
            <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              disabled={isExisting}
              placeholder="user@cambiumretail.com"
              className="mt-1 w-full px-2.5 py-1.5 text-sm bg-zinc-50 border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 focus:bg-white transition-colors disabled:bg-zinc-100 disabled:text-zinc-500"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Display name"
              className="mt-1 w-full px-2.5 py-1.5 text-sm bg-zinc-50 border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 focus:bg-white transition-colors"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">
              {isExisting ? "New password (leave blank to keep)" : "Password"}
            </label>
            <input
              type="text"
              required={!isExisting}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder={isExisting ? "•••••••• unchanged" : "Set password"}
              className="mt-1 w-full px-2.5 py-1.5 text-sm bg-zinc-50 border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 focus:bg-white transition-colors"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Role</label>
            <div className="mt-1 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setRole("user")}
                className={`px-2.5 py-1.5 text-sm rounded-md border transition flex items-center justify-center gap-1.5 ${
                  role === "user"
                    ? "bg-zinc-900 text-white border-zinc-900"
                    : "bg-white text-zinc-600 border-zinc-200 hover:border-zinc-400"
                }`}
              >
                <UserIcon size={13} />
                User
              </button>
              <button
                type="button"
                onClick={() => setRole("admin")}
                className={`px-2.5 py-1.5 text-sm rounded-md border transition flex items-center justify-center gap-1.5 ${
                  role === "admin"
                    ? "bg-violet-600 text-white border-violet-600"
                    : "bg-white text-zinc-600 border-zinc-200 hover:border-zinc-400"
                }`}
              >
                <Shield size={13} />
                Admin
              </button>
            </div>
          </div>

          {role !== "admin" && (
            <div>
              <div className="flex items-center justify-between">
                <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Modules</label>
                <div className="flex gap-1.5 text-[10px]">
                  <button type="button" onClick={() => setAllowed(modules)} className="text-indigo-600 hover:underline">all</button>
                  <span className="text-zinc-300">·</span>
                  <button type="button" onClick={() => setAllowed([])} className="text-zinc-500 hover:underline">none</button>
                </div>
              </div>
              <div className="mt-1 border border-zinc-200 rounded-md bg-zinc-50/50 divide-y divide-zinc-100">
                {modules.map(m => (
                  <label
                    key={m}
                    className="flex items-center gap-2 px-2.5 py-1.5 text-sm hover:bg-white cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={allowed.includes(m)}
                      onChange={() => toggle(m)}
                      className="rounded text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-zinc-700">{MODULE_LABELS[m] || m}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-3 border-t border-zinc-100">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-sm bg-white text-zinc-700 border border-zinc-200 rounded-md hover:border-zinc-400"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-3 py-1.5 text-sm font-semibold bg-zinc-900 text-white rounded-md hover:bg-zinc-800 flex items-center gap-1.5 shadow-sm"
            >
              <Check size={13} />
              {isExisting ? "Save" : "Create user"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
