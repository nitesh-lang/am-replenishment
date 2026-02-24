import { NavLink } from "react-router-dom";
import { useState } from "react";
import {
  LayoutDashboard,
  Boxes,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Search,
  Bell,
  User,
} from "lucide-react";

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false);

  const navItems = [
    { name: "Replenishment", path: "/replenishment", icon: LayoutDashboard },
    { name: "FC Allocation", path: "/fc-allocation", icon: Boxes },
    { name: "China Reorder", path: "/china-reorder", icon: Boxes },   // ✅ ADD THIS
    { name: "Sales Analytics", path: "/sales-analytics", icon: BarChart3 },
    { name: "Region Sales", path: "/region-sales", icon: BarChart3 }, // 👈 ADD THIS
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
        <header className="h-16 bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center justify-between px-12 shadow-sm">
          
          {/* Search */}
          <div className="relative w-80">
            <Search
              size={16}
              className="absolute left-3 top-3 text-slate-400"
            />
            <input
              type="text"
              placeholder="Search anything..."
              className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>

          {/* Right Controls */}
          <div className="flex items-center gap-6">
            <Bell
              size={18}
              className="text-slate-500 hover:text-slate-800 cursor-pointer"
            />

            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white text-xs font-semibold shadow">
                NX
              </div>
              <div className="text-sm text-slate-600">
                Admin
              </div>
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