import { useState } from "react";
import { Link } from "react-router-dom";
import { Mail, ArrowLeft, KeyRound } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

export default function ForgotPassword() {
  const { requestPasswordReset } = useAuth();
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    const res = requestPasswordReset(email);
    setSubmitting(false);
    setMessage(res.message);
    setSubmitted(true);
  }

  return (
    <div className="min-h-screen relative overflow-hidden bg-zinc-50 flex items-center justify-center px-4">
      <div className="absolute -top-32 -left-32 w-96 h-96 bg-indigo-200/30 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute -bottom-32 -right-32 w-96 h-96 bg-violet-200/30 rounded-full blur-3xl pointer-events-none"></div>

      <div className="relative w-full max-w-sm">

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
          <div className="mb-5 flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-md bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <KeyRound size={16} />
            </div>
            <div>
              <h1 className="text-base font-semibold text-zinc-900 tracking-tight leading-tight">Reset password</h1>
              <p className="text-xs text-zinc-500 leading-tight mt-0.5">We'll send a reset link to your email</p>
            </div>
          </div>

          {!submitted ? (
            <form onSubmit={handleSubmit} className="space-y-3.5">
              <div>
                <label className="text-[10px] uppercase tracking-[0.08em] font-semibold text-zinc-500">Email</label>
                <div className="relative mt-1">
                  <Mail size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none" />
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

              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-zinc-900 hover:bg-zinc-800 text-white text-sm font-semibold py-2 rounded-md shadow-sm transition disabled:opacity-50"
              >
                {submitting ? "Sending…" : "Send reset link"}
              </button>
            </form>
          ) : (
            <div className="text-xs text-zinc-700 bg-indigo-50/60 border border-indigo-100 rounded-md px-3 py-2.5 leading-relaxed">
              {message}
            </div>
          )}

          <div className="mt-5 pt-4 border-t border-zinc-100 text-center">
            <Link
              to="/login"
              className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-900 transition"
            >
              <ArrowLeft size={12} />
              Back to sign in
            </Link>
          </div>
        </div>

        <p className="text-center text-[10px] text-zinc-400 mt-6 uppercase tracking-[0.12em]">
          © 2026 Nexlev Intelligence Suite
        </p>
      </div>
    </div>
  );
}
