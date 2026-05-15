import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";

/**
 * Gate that lets a route render only if the user has access to the given moduleKey.
 * Otherwise, redirect to the first module the user CAN access (or /login if none).
 */
export default function ModuleGate({ moduleKey, children }) {
  const { user, canAccess } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (canAccess(moduleKey)) return children;

  // Pick first allowed module as fallback
  const allowed = user.role === "admin"
    ? ["dashboard"]
    : (user.allowedModules || []);
  const firstAllowed = allowed[0];
  if (firstAllowed) {
    return <Navigate to={`/${firstAllowed}`} replace />;
  }
  return <Navigate to="/login" replace />;
}
