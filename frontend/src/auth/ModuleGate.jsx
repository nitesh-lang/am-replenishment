import { Navigate } from "react-router-dom";
import { useEffect } from "react";
import { useAuth } from "./AuthContext";
import { logUsage } from "./usage";

/**
 * Gate that lets a route render only if the user has access to the given moduleKey.
 * Otherwise, redirect to the first module the user CAN access (or /login if none).
 * Also fires a page_view usage event on each authorized mount.
 */
export default function ModuleGate({ moduleKey, children }) {
  const { user, canAccess } = useAuth();
  const allowed = !!user && canAccess(moduleKey);

  useEffect(() => {
    if (allowed) logUsage("page_view", moduleKey);
  }, [allowed, moduleKey]);

  if (!user) return <Navigate to="/login" replace />;
  if (allowed) return children;

  // Pick first allowed module as fallback
  const allowedList = user.role === "admin"
    ? ["dashboard"]
    : (user.allowedModules || []);
  const firstAllowed = allowedList[0];
  if (firstAllowed) {
    return <Navigate to={`/${firstAllowed}`} replace />;
  }
  return <Navigate to="/login" replace />;
}
