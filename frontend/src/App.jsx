import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";
import ModuleGate from "./auth/ModuleGate";

import Layout from "./layout/Layout";
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";
import Replenishment from "./pages/Replenishment";
import ReplenishmentV2 from "./pages/ReplenishmentV2";
import FCAllocation from "./pages/FCAllocation";
import FCAllocationV2 from "./pages/FCAllocationV2";
import SalesAnalytics from "./pages/SalesAnalytics";
import RegionSales from "./pages/RegionSales";
import ChinaReorder from "./pages/ChinaReorder";
import CBReplenishment from "./pages/CBReplenishment";
import CBReplenishmentV2 from "./pages/CBReplenishmentV2";
import WMReplenishment from "./pages/WMReplenishment";
import FossilReplenishment from "./pages/FossilReplenishment";
import BlinkitReplenishment from "./pages/BlinkitReplenishment";
import Dashboard from "./pages/Dashboard";
import Admin from "./pages/Admin";
import UsageAnalytics from "./pages/UsageAnalytics";

function Gated({ moduleKey, children }) {
  return (
    <ProtectedRoute>
      <ModuleGate moduleKey={moduleKey}>
        <Layout>{children}</Layout>
      </ModuleGate>
    </ProtectedRoute>
  );
}

function AdminOnly({ children }) {
  return (
    <ProtectedRoute>
      <RequireAdmin>
        <Layout>{children}</Layout>
      </RequireAdmin>
    </ProtectedRoute>
  );
}

function RequireAdmin({ children }) {
  const { user } = useAuth();
  if (!user || user.role !== "admin") return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>

          {/* Public */}
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />

          {/* Root */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Module-gated pages */}
          <Route path="/dashboard"             element={<Gated moduleKey="dashboard"><Dashboard /></Gated>} />
          <Route path="/replenishment"         element={<Gated moduleKey="replenishment"><Replenishment /></Gated>} />
          <Route path="/replenishment-v2"      element={<Gated moduleKey="replenishment"><ReplenishmentV2 /></Gated>} />
          <Route path="/fc-allocation"         element={<Gated moduleKey="fc-allocation"><FCAllocation /></Gated>} />
          <Route path="/fc-allocation-v2"      element={<Gated moduleKey="fc-allocation"><FCAllocationV2 /></Gated>} />
          <Route path="/sales-analytics"       element={<Gated moduleKey="sales-analytics"><SalesAnalytics /></Gated>} />
          <Route path="/region-sales"          element={<Gated moduleKey="region-sales"><RegionSales /></Gated>} />
          <Route path="/china-reorder"         element={<Gated moduleKey="china-reorder"><ChinaReorder /></Gated>} />
          <Route path="/cb-replenishment"      element={<Gated moduleKey="cb-replenishment"><CBReplenishment /></Gated>} />
          <Route path="/cb-replenishment-v2"   element={<Gated moduleKey="cb-replenishment"><CBReplenishmentV2 /></Gated>} />
          <Route path="/wm-replenishment"      element={<Gated moduleKey="wm-replenishment"><WMReplenishment /></Gated>} />
          <Route path="/fossil-replenishment"  element={<Gated moduleKey="fossil-replenishment"><FossilReplenishment /></Gated>} />
          <Route path="/blinkit-replenishment" element={<Gated moduleKey="blinkit-replenishment"><BlinkitReplenishment /></Gated>} />

          {/* Admin-only */}
          <Route path="/admin" element={<AdminOnly><Admin /></AdminOnly>} />
          <Route path="/usage" element={<AdminOnly><UsageAnalytics /></AdminOnly>} />

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />

        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
