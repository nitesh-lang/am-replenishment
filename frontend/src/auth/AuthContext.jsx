import { createContext, useContext, useEffect, useState } from "react";

const AuthContext = createContext(null);

const STORAGE_KEY = "am_repl_auth";

const VALID_USERS = [
  { email: "info@cambiumretail.com", password: "Cambium@109" },
];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setUser(JSON.parse(raw));
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
    setReady(true);
  }, []);

  function login(email, password) {
    const normEmail = (email || "").trim().toLowerCase();
    const match = VALID_USERS.find(
      (u) => u.email.toLowerCase() === normEmail && u.password === password
    );
    if (!match) {
      return { ok: false, error: "Invalid email or password" };
    }
    const session = { email: match.email, loginAt: Date.now() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    setUser(session);
    return { ok: true };
  }

  function logout() {
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
  }

  function requestPasswordReset(email) {
    const normEmail = (email || "").trim().toLowerCase();
    const known = VALID_USERS.some((u) => u.email.toLowerCase() === normEmail);
    return {
      ok: true,
      message: known
        ? "If an account exists for this email, a reset link has been sent."
        : "If an account exists for this email, a reset link has been sent.",
    };
  }

  return (
    <AuthContext.Provider
      value={{ user, ready, login, logout, requestPasswordReset }}
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
