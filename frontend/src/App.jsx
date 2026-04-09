import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import Layout from "./layout/Layout";
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

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>

          {/* Default Redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Main Pages */}
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/replenishment" element={<Replenishment />} />
          <Route path="/fc-allocation" element={<FCAllocation />} />
          <Route path="/sales-analytics" element={<SalesAnalytics />} />
          <Route path="/region-sales" element={<RegionSales />} />
          <Route path="/china-reorder" element={<ChinaReorder />} />
          <Route path="/china-reorder-working" element={<ChinaReorderWorking />} />
          <Route path="/cb-replenishment" element={<CBReplenishment />} />
          <Route path="/wm-replenishment" element={<WMReplenishment />} />
          <Route path="/fossil-replenishment" element={<FossilReplenishment />} />

          {/* Catch All Route */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />

        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;