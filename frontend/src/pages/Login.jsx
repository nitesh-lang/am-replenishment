import { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { Lock, Mail, Eye, EyeOff, ArrowRight } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const res = await login(email, password);
      if (!res.ok) {
        setError(res.error);
        return;
      }
      // Land on first allowed module — Dashboard is admin-only-ish
      const fallback = res.user?.role === "admin"
        ? "/dashboard"
        : `/${(res.user?.allowedModules || [])[0] || "login"}`;
      navigate(from === "/" ? fallback : from, { replace: true });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen relative overflow-hidden bg-zinc-50 flex items-center justify-center px-4">
      {/* Decorative gradient blobs — subtle */}
      <div className="absolute -top-32 -left-32 w-96 h-96 bg-indigo-200/30 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute -bottom-32 -right-32 w-96 h-96 bg-violet-200/30 rounded-full blur-3xl pointer-events-none"></div>

      <div className="relative w-full max-w-sm">

        {/* Brand */}
        <div className="flex items-center gap-2.5 mb-8 justify-center">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-sm font-bold shadow-md shadow-indigo-500/30">
            N
          </div>
          <div className="text-left">
            <div className="text-sm font-semibold text-zinc-900 leading-tight tracking-tight">Nexlev</div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-500 leading-tight">Intelligence Suite</div>
          </div>
        </div>

        <div className="bg-white border border-zinc-200 rounded-xl shadow-xl shadow-zinc-200/40 p-7">
          <div className="mb-5">
            <h1 className="text-lg font-semibold text-zinc-900 tracking-tight">Welcome back</h1>
            <p className="text-xs text-zinc-500 mt-0.5">Sign in to continue to your dashboard</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div>
              <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">
                Email
              </label>
              <div className="relative mt-1">
                <Mail
                  size={14}
                  className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none"
                />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                  placeholder="you@example.com"
                  className="w-full pl-8 pr-3 py-2 text-sm bg-zinc-50 border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 focus:bg-white transition-colors placeholder:text-zinc-400"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">
                  Password
                </label>
                <Link
                  to="/forgot-password"
                  className="text-[10px] text-indigo-600 hover:text-indigo-700 font-medium"
                >
                  Forgot?
                </Link>
              </div>
              <div className="relative mt-1">
                <Lock
                  size={14}
                  className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none"
                />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  placeholder="Enter your password"
                  className="w-full pl-8 pr-9 py-2 text-sm bg-zinc-50 border border-zinc-200 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 focus:bg-white transition-colors placeholder:text-zinc-400"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-700 p-1"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-2.5 py-2 flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-red-500 flex-shrink-0"></span>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-zinc-900 hover:bg-zinc-800 text-white text-sm font-semibold py-2 rounded-md shadow-sm transition disabled:opacity-50 flex items-center justify-center gap-1.5 group"
            >
              {submitting ? (
                "Signing in…"
              ) : (
                <>
                  Sign in
                  <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
                </>
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-[10px] text-zinc-400 mt-6 uppercase tracking-[0.12em]">
          © 2026 Nexlev Intelligence Suite
        </p>
      </div>
    </div>
  );
}
