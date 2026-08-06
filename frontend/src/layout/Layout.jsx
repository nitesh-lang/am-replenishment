import { NavLink, useNavigate } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import { LogOut, ChevronDown, Search } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

/**
 * Horizontal-nav app shell (replaces the prior sidebar layout).
 * - Dark slate-950 top bar with brand + module nav + ⌘K + user
 * - No sidebar — content goes full-width below
 */
export default function Layout({ children }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  const navigate = useNavigate();
  const { user, logout, canAccess } = useAuth();

  useEffect(() => {
    function onClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  const userInitials = (user?.email || "NX")
    .split("@")[0]
    .slice(0, 2)
    .toUpperCase();

  // Every visible link renders directly in the top nav (no "More" dropdown).
  // Order: operational modules first, then analytics, then admin-only tools.
  const navItems = [
    { name: "Dashboard",       path: "/dashboard",             show: canAccess("dashboard") },
    { name: "Replenishment",   path: "/replenishment",         show: canAccess("replenishment") },
    { name: "FBA Inbound",     path: "/fba-inbound",           show: canAccess("replenishment") },
    { name: "FC Allocation",   path: "/fc-allocation",         show: canAccess("fc-allocation") },
    { name: "PO Creation",     path: "/po-creation",           show: canAccess("fc-allocation") },
    { name: "Reorder",         path: "/china-reorder",         show: canAccess("china-reorder") },
    { name: "CB",              path: "/cb-replenishment",      show: canAccess("cb-replenishment") },
    { name: "Clicktech",       path: "/wm-replenishment",      show: canAccess("wm-replenishment") },
    { name: "Fossil",          path: "/fossil-replenishment",  show: canAccess("fossil-replenishment") },
    { name: "Blinkit",         path: "/blinkit-replenishment", show: canAccess("blinkit-replenishment") },
    { name: "Plans",           path: "/plans",                 show: canAccess("plans-editor") || canAccess("plans-approver") || user?.role === "admin" },
    { name: "Usage",           path: "/usage",                 show: user?.role === "admin" },
    { name: "Users",           path: "/admin",                 show: user?.role === "admin" },
  ].filter(i => i.show);

  function openCommandPalette() {
    // Pages that mount the CommandPalette listen for Cmd/Ctrl+K globally
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
  }

  return (
    <div className="min-h-screen bg-slate-100">
      {/* ===== TOP DARK NAV (horizontal) ===== */}
      <header className="bg-slate-950 text-white sticky top-0 z-40 shadow-sm">
        <div className="px-6 py-2.5 flex items-center justify-between gap-6">
          {/* Brand */}
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-7 h-7 rounded bg-gradient-to-br from-violet-500 to-indigo-600 grid place-items-center text-xs font-bold shadow-md shadow-indigo-500/20">
              N
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-tight">Nexlev</div>
              <div className="text-[9px] uppercase tracking-[0.1em] text-white/40 -mt-0.5">Intelligence</div>
            </div>
          </div>

          {/* Module nav — everything in one horizontal strip, scrollable if crowded */}
          <nav className="flex items-center gap-0.5 overflow-x-auto flex-1 min-w-0">
            {navItems.map(item => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-[13px] font-medium whitespace-nowrap transition-colors ${
                    isActive
                      ? "bg-white/10 text-white"
                      : "text-white/70 hover:bg-white/5 hover:text-white"
                  }`
                }
              >
                {item.name}
              </NavLink>
            ))}
          </nav>

          {/* Right controls */}
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={openCommandPalette}
              className="hidden md:flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-sm"
              title="Quick find"
            >
              <Search className="w-3.5 h-3.5 text-white/60" />
              <span className="text-white/60 text-xs">Quick find</span>
              <kbd className="ml-1 px-1.5 py-0.5 rounded bg-white/10 text-[10px] text-white/70 font-mono">⌘K</kbd>
            </button>

            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen(v => !v)}
                className="flex items-center gap-2 hover:bg-white/5 rounded-md px-1.5 py-1 transition"
              >
                <div className="h-7 w-7 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 grid place-items-center text-[11px] font-bold shadow-sm">
                  {userInitials}
                </div>
                <span className="hidden md:inline text-xs text-white/80 max-w-[160px] truncate font-medium">
                  {user?.email || "Admin"}
                </span>
                <ChevronDown className={`w-3 h-3 text-white/40 transition-transform ${menuOpen ? "rotate-180" : ""}`} />
              </button>

              {menuOpen && (
                <div className="absolute right-0 mt-1.5 w-60 bg-white border border-slate-200 rounded-lg shadow-xl py-1 z-50 overflow-hidden">
                  <div className="px-3 py-2.5 border-b border-slate-100 flex items-center gap-2.5">
                    <div className="h-9 w-9 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 grid place-items-center text-white text-xs font-bold shadow-sm">
                      {userInitials}
                    </div>
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-[0.08em] text-slate-400 font-semibold leading-tight">Signed in as</div>
                      <div className="text-xs text-slate-900 truncate font-medium leading-tight mt-0.5">{user?.email}</div>
                    </div>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 transition font-medium"
                  >
                    <LogOut className="w-3.5 h-3.5 text-slate-400" />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* ===== PAGE CONTENT (full width) ===== */}
      <main className="w-full">
        {children}
      </main>
    </div>
  );
}
