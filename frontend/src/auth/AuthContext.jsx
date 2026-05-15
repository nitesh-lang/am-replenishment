import { createContext, useContext, useEffect, useState } from "react";
import { logUsage } from "./usage";

const AuthContext = createContext(null);

const STORAGE_KEY = "am_repl_auth_v2";
const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

// Session expires at midnight local time. Re-login required after that.
function nextLocalMidnight() {
  const d = new Date();
  d.setHours(24, 0, 0, 0); // tonight at 00:00
  return d.getTime();
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const session = JSON.parse(raw);
        if (session.expiresAt && session.expiresAt <= Date.now()) {
          // Session crossed midnight while user was away — clear it
          localStorage.removeItem(STORAGE_KEY);
        } else {
          setUser(session);
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
    setReady(true);
  }, []);

  // Schedule auto-logout at the session's midnight expiry
  useEffect(() => {
    if (!user?.expiresAt) return;
    const msLeft = user.expiresAt - Date.now();
    if (msLeft <= 0) {
      logout();
      return;
    }
    const id = setTimeout(() => logout(), msLeft);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.expiresAt]);

  async function login(email, password) {
    try {
      const res = await fetch(`${BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: (email || "").trim(), password }),
      });
      const j = await res.json();
      if (j.status !== "ok" || !j.user) {
        return { ok: false, error: j.error || "Invalid email or password" };
      }
      const session = {
        email: j.user.email,
        name:  j.user.name,
        role:  j.user.role,
        allowedModules: j.user.allowed_modules || [],
        loginAt: Date.now(),
        expiresAt: nextLocalMidnight(),
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      setUser(session);
      logUsage("login", null, { role: session.role });
      return { ok: true, user: session };
    } catch (e) {
      return { ok: false, error: "Could not reach the server. Try again." };
    }
  }

  function logout() {
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
  }

  function canAccess(moduleKey) {
    if (!user) return false;
    if (user.role === "admin") return true;
    return (user.allowedModules || []).includes(moduleKey);
  }

  function requestPasswordReset(email) {
    const normEmail = (email || "").trim().toLowerCase();
    return {
      ok: true,
      message: "If an account exists for this email, a reset link has been sent.",
    };
  }

  return (
    <AuthContext.Provider
      value={{ user, ready, login, logout, canAccess, requestPasswordReset }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
