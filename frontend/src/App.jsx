import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import Layout from "./layout/Layout";
import Replenishment from "./pages/Replenishment";
import FCAllocation from "./pages/FCAllocation";
import SalesAnalytics from "./pages/SalesAnalytics";
import RegionSales from "./pages/RegionSales";

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>

          {/* Default Redirect */}
          <Route path="/" element={<Navigate to="/replenishment" replace />} />

          {/* Main Pages */}
          <Route path="/replenishment" element={<Replenishment />} />
          <Route path="/fc-allocation" element={<FCAllocation />} />
          <Route path="/sales-analytics" element={<SalesAnalytics />} />
          <Route path="/region-sales" element={<RegionSales />} />

          {/* Catch All Route */}
          <Route path="*" element={<Navigate to="/replenishment" replace />} />

        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;