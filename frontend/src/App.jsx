import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";

import Layout from "./layout/Layout";
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";
import Replenishment from "./pages/Replenishment";
import FCAllocation from "./pages/FCAllocation";
import SalesAnalytics from "./pages/SalesAnalytics";
import RegionSales from "./pages/RegionSales";
import ChinaReorder from "./pages/ChinaReorder";
import ChinaReorderWorking from "./pages/ChinaReorderWorking";
import CBReplenishment from "./pages/CBReplenishment";
import WMReplenishment from "./pages/WMReplenishment";
import FossilReplenishment from "./pages/FossilReplenishment";
import Dashboard from "./pages/Dashboard";

function ProtectedLayout({ children }) {
  return (
    <ProtectedRoute>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>

          {/* Public Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />

          {/* Default Redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Protected Pages */}
          <Route
            path="/dashboard"
            element={<ProtectedLayout><Dashboard /></ProtectedLayout>}
          />
          <Route
            path="/replenishment"
            element={<ProtectedLayout><Replenishment /></ProtectedLayout>}
          />
          <Route
            path="/fc-allocation"
            element={<ProtectedLayout><FCAllocation /></ProtectedLayout>}
          />
          <Route
            path="/sales-analytics"
            element={<ProtectedLayout><SalesAnalytics /></ProtectedLayout>}
          />
          <Route
            path="/region-sales"
            element={<ProtectedLayout><RegionSales /></ProtectedLayout>}
          />
          <Route
            path="/china-reorder"
            element={<ProtectedLayout><ChinaReorder /></ProtectedLayout>}
          />
          <Route
            path="/china-reorder-working"
            element={<ProtectedLayout><ChinaReorderWorking /></ProtectedLayout>}
          />
          <Route
            path="/cb-replenishment"
            element={<ProtectedLayout><CBReplenishment /></ProtectedLayout>}
          />
          <Route
            path="/wm-replenishment"
            element={<ProtectedLayout><WMReplenishment /></ProtectedLayout>}
          />
          <Route
            path="/fossil-replenishment"
            element={<ProtectedLayout><FossilReplenishment /></ProtectedLayout>}
          />

          {/* Catch All Route */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />

        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
