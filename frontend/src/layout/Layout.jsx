import { NavLink, useNavigate } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import {
  LayoutDashboard,
  Boxes,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  LogOut,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  const navigate = useNavigate();
  const { user, logout } = useAuth();

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

  const navItems = [
    { name: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { name: "Replenishment", path: "/replenishment", icon: LayoutDashboard },
    { name: "FC Allocation", path: "/fc-allocation", icon: Boxes },
    { name: "China Reorder", path: "/china-reorder", icon: Boxes },   // ✅ ADD THIS
    { name: "Sales Analytics", path: "/sales-analytics", icon: BarChart3 },
    { name: "Region Sales", path: "/region-sales", icon: BarChart3 }, // 👈 ADD THIS
    { name: "CB Replenishment", path: "/cb-replenishment", icon: Boxes },
    { name: "Clicktech Replenishment", path: "/wm-replenishment", icon: Boxes },
    { name: "China Reorder Working", path: "/china-reorder-working", icon: Boxes },
    { name: "Fossil Replenishment", path: "/fossil-replenishment", icon: Boxes },
  ];

  return (
    <div className="min-h-screen flex bg-[#f6f8fb]">

      {/* ================= SIDEBAR ================= */}
      <aside
        className={`${
          collapsed ? "w-20" : "w-56"
        } bg-gradient-to-b from-slate-900 to-slate-950 text-slate-200 flex flex-col transition-all duration-300 shadow-2xl`}
      >
        {/* Brand */}
        <div className="h-16 flex items-center justify-between px-5 border-b border-slate-800">
          {!collapsed && (
            <div>
              <div className="text-lg font-semibold tracking-tight">
                Nexlev
              </div>
              <div className="text-xs text-slate-400">
                Intelligence Suite
              </div>
            </div>
          )}

          <button
            onClick={() => setCollapsed(!collapsed)}
            className="text-slate-400 hover:text-white transition"
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-6 space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;

            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow"
                      : "text-slate-400 hover:bg-slate-800 hover:text-white"
                  }`
                }
              >
                <Icon size={18} />
                {!collapsed && item.name}
              </NavLink>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 text-xs text-slate-500">
          {!collapsed && "© 2026 Nexlev"}
        </div>
      </aside>

      {/* ================= MAIN AREA ================= */}
      <div className="flex-1 flex flex-col">

        {/* ===== TOP NAVBAR ===== */}
        <header className="h-10 bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center justify-end px-8 shadow-sm">
          {/* Right Controls */}
          <div className="flex items-center gap-4">
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 hover:bg-slate-100 rounded-lg px-2 py-1 transition"
              >
                <div className="h-8 w-8 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white text-xs font-semibold shadow">
                  {userInitials}
                </div>
                <div className="text-sm text-slate-600 max-w-[180px] truncate">
                  {user?.email || "Admin"}
                </div>
              </button>

              {menuOpen && (
                <div className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-50">
                  <div className="px-4 py-2 border-b border-slate-100">
                    <div className="text-xs text-slate-400">Signed in as</div>
                    <div className="text-sm text-slate-700 truncate">
                      {user?.email}
                    </div>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                  >
                    <LogOut size={14} />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* ===== PAGE CONTENT ===== */}
        <main className="flex-1 overflow-auto px-12 py-6 bg-slate-50">
          <div className="w-full">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}