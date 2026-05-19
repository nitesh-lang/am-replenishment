import { NavLink, useNavigate } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import {
  LayoutDashboard,
  Boxes,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Users,
  Activity,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  const navigate = useNavigate();
  const { user, logout, canAccess } = useAuth();

  useEffect(() => {
    function onClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
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

  const allNavItems = [
    { name: "Dashboard",              path: "/dashboard",              moduleKey: "dashboard",              icon: LayoutDashboard },
    { name: "Replenishment",          path: "/replenishment",          moduleKey: "replenishment",          icon: LayoutDashboard },
    { name: "FC Allocation",          path: "/fc-allocation",          moduleKey: "fc-allocation",          icon: Boxes },
    { name: "Reorder",                path: "/china-reorder",          moduleKey: "china-reorder",          icon: Boxes },
    { name: "Sales Analytics",        path: "/sales-analytics",        moduleKey: "sales-analytics",        icon: BarChart3 },
    { name: "Region Sales",           path: "/region-sales",           moduleKey: "region-sales",           icon: BarChart3 },
    { name: "CB Replenishment",       path: "/cb-replenishment",       moduleKey: "cb-replenishment",       icon: Boxes },
    { name: "Clicktech Replenishment",path: "/wm-replenishment",       moduleKey: "wm-replenishment",       icon: Boxes },
    { name: "Fossil Replenishment",   path: "/fossil-replenishment",   moduleKey: "fossil-replenishment",   icon: Boxes },
    { name: "Blinkit Replenishment",  path: "/blinkit-replenishment",  moduleKey: "blinkit-replenishment",  icon: Boxes },
  ];

  const navItems = allNavItems.filter(item => canAccess(item.moduleKey));

  return (
    <div className="min-h-screen flex bg-zinc-50">

      {/* ================= SIDEBAR ================= */}
      <aside
        className={`${
          collapsed ? "w-16" : "w-56"
        } bg-zinc-950 text-zinc-300 flex flex-col transition-all duration-300 border-r border-zinc-800`}
      >
        {/* Brand */}
        <div className="h-14 flex items-center justify-between px-3 border-b border-zinc-800/80">
          {!collapsed ? (
            <div className="flex items-center gap-2.5">
              <div className="h-7 w-7 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold shadow-md shadow-indigo-500/20">
                N
              </div>
              <div>
                <div className="text-sm font-semibold text-white leading-tight tracking-tight">Nexlev</div>
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500 leading-tight">Intelligence</div>
              </div>
            </div>
          ) : (
            <div className="h-7 w-7 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold mx-auto">
              N
            </div>
          )}

          <button
            onClick={() => setCollapsed(!collapsed)}
            className="text-zinc-500 hover:text-white transition"
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;

            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-2.5 py-2 rounded-md text-[13px] font-medium transition-all group relative ${
                    isActive
                      ? "bg-zinc-800/60 text-white"
                      : "text-zinc-400 hover:bg-zinc-800/40 hover:text-zinc-100"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-gradient-to-b from-violet-500 to-indigo-600 rounded-r"></span>
                    )}
                    <Icon size={15} className={isActive ? "text-indigo-400" : "text-zinc-500 group-hover:text-zinc-300"} />
                    {!collapsed && <span className="truncate">{item.name}</span>}
                  </>
                )}
              </NavLink>
            );
          })}

          {user?.role === "admin" && (
            <>
              <div className={`mt-3 mb-1 px-2.5 text-[9px] uppercase tracking-[0.12em] text-zinc-600 font-semibold ${collapsed ? "hidden" : ""}`}>
                Admin
              </div>
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-2.5 py-2 rounded-md text-[13px] font-medium transition-all group relative ${
                    isActive
                      ? "bg-zinc-800/60 text-white"
                      : "text-zinc-400 hover:bg-zinc-800/40 hover:text-zinc-100"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-gradient-to-b from-violet-500 to-indigo-600 rounded-r"></span>
                    )}
                    <Users size={15} className={isActive ? "text-indigo-400" : "text-zinc-500 group-hover:text-zinc-300"} />
                    {!collapsed && <span className="truncate">User Management</span>}
                  </>
                )}
              </NavLink>
              <NavLink
                to="/usage"
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-2.5 py-2 rounded-md text-[13px] font-medium transition-all group relative ${
                    isActive
                      ? "bg-zinc-800/60 text-white"
                      : "text-zinc-400 hover:bg-zinc-800/40 hover:text-zinc-100"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-gradient-to-b from-violet-500 to-indigo-600 rounded-r"></span>
                    )}
                    <Activity size={15} className={isActive ? "text-indigo-400" : "text-zinc-500 group-hover:text-zinc-300"} />
                    {!collapsed && <span className="truncate">Usage Analytics</span>}
                  </>
                )}
              </NavLink>
            </>
          )}
        </nav>

        {/* Footer */}
        <div className="px-3 py-3 border-t border-zinc-800/80 text-[10px] text-zinc-500 uppercase tracking-[0.1em]">
          {!collapsed && "© 2026 Nexlev"}
        </div>
      </aside>

      {/* ================= MAIN AREA ================= */}
      <div className="flex-1 flex flex-col">

        {/* ===== TOP NAVBAR ===== */}
        <header className="h-10 bg-white/90 backdrop-blur-md border-b border-zinc-200 flex items-center justify-end px-8">
          {/* Right Controls */}
          <div className="flex items-center gap-4">
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 hover:bg-zinc-100 rounded-md px-1.5 py-1 transition group"
              >
                <div className="h-6 w-6 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-[10px] font-bold shadow-sm shadow-indigo-500/30">
                  {userInitials}
                </div>
                <div className="text-xs text-zinc-700 max-w-[180px] truncate font-medium">
                  {user?.email || "Admin"}
                </div>
                <svg className={`h-3 w-3 text-zinc-400 transition-transform ${menuOpen ? "rotate-180" : ""}`} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 4.5l3 3 3-3"/></svg>
              </button>

              {menuOpen && (
                <div className="absolute right-0 mt-1.5 w-60 bg-white border border-zinc-200 rounded-lg shadow-xl shadow-zinc-200/40 py-1 z-50 overflow-hidden">
                  <div className="px-3 py-2.5 border-b border-zinc-100 flex items-center gap-2.5">
                    <div className="h-9 w-9 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold shadow-sm shadow-indigo-500/30">
                      {userInitials}
                    </div>
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-400 font-semibold leading-tight">Signed in as</div>
                      <div className="text-xs text-zinc-900 truncate font-medium leading-tight mt-0.5">
                        {user?.email}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-zinc-700 hover:bg-zinc-50 transition font-medium"
                  >
                    <LogOut size={13} className="text-zinc-400" />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* ===== PAGE CONTENT ===== */}
        <main className="flex-1 overflow-auto px-8 py-5 bg-zinc-50">
          <div className="w-full">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}