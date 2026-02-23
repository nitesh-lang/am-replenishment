import { getFCFinal } from "../api/replenishment";
import { useEffect, useMemo, useState } from "react";
import {
  getReplenishment,
  getKPIs,
} from "../api/replenishment";

/* =========================================================
   DASHBOARD PAGE
   ========================================================= */
export default function Dashboard() {
  /* ================= STATE ================= */
  const [salesWindow, setSalesWindow] = useState(4);
  const [replenishWeeks, setReplenishWeeks] = useState(8);
  const [fcFinal, setFcFinal] = useState([]);

  const [kpis, setKpis] = useState(null);
  const [replenishment, setReplenishment] = useState([]);
  const [loading, setLoading] = useState(false);

  /* ================= GLOBAL SEARCH ================= */
  const [search, setSearch] = useState("");

  /* ================= COLUMN FILTERS ================= */
  const [filters, setFilters] = useState({
    model: "",
    asin: "",
    sku: "",
    category: "",
  });

  /* ================= SORTING ================= */
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  /* =========================================================
     DATA LOAD
     ========================================================= */
    useEffect(() => {
  setLoading(true);

  Promise.all([
    getKPIs(salesWindow),
    getReplenishment(salesWindow, replenishWeeks),
    getFCFinal(replenishWeeks),
  ])
  .then(([kpisRes, replRes, fcRes]) => {   // ✅ FIXED
    setKpis(kpisRes);
    setReplenishment(Array.isArray(replRes) ? replRes : []);
    setFcFinal(Array.isArray(fcRes) ? fcRes : []);   // ✅ FIXED
  })
  .finally(() => setLoading(false));

}, [salesWindow, replenishWeeks]);

  /* =========================================================
     DYNAMIC COLUMNS
     ========================================================= */
  const replenishmentColumns = useMemo(() => {
    if (!replenishment.length) return [];
    return Object.keys(replenishment[0]);
  }, [replenishment]);

  /* =========================================================
     FILTERING
     ========================================================= */
  const filteredReplenishment = useMemo(() => {
    return replenishment
      .filter((row) =>
        row.model?.toLowerCase().includes(search.toLowerCase())
      )
      .filter((row) => {
        if (
          filters.model &&
          !row.model?.toLowerCase().includes(filters.model.toLowerCase())
        )
          return false;

        if (
          filters.asin &&
          !row.asin?.toLowerCase().includes(filters.asin.toLowerCase())
        )
          return false;

        if (
          filters.sku &&
          !row.sku?.toLowerCase().includes(filters.sku.toLowerCase())
        )
          return false;

        if (
          filters.category &&
          !row.category?.toLowerCase().includes(filters.category.toLowerCase())
        )
          return false;

        return true;
      });
  }, [replenishment, search, filters]);

  /* =========================================================
     SORTING
     ========================================================= */
  const sortedReplenishment = useMemo(() => {
    if (!sortConfig.key) return filteredReplenishment;

    const direction = sortConfig.direction === "asc" ? 1 : -1;

    return [...filteredReplenishment].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];

      if (aVal == null) return 1;
      if (bVal == null) return -1;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return (aVal - bVal) * direction;
      }

      return aVal
        .toString()
        .localeCompare(bVal.toString()) * direction;
    });
  }, [filteredReplenishment, sortConfig]);

  function toggleSort(column) {
    setSortConfig((prev) => ({
      key: column,
      direction:
        prev.key === column && prev.direction === "asc"
          ? "desc"
          : "asc",
    }));
  }

  /* =========================================================
     RENDER
     ========================================================= */
  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <h1 className="text-4xl font-bold text-gray-800 mb-6">
  Amazon Replenishment Dashboard
</h1>

      {/* ================= CONTROLS ================= */}
      <div className="flex flex-wrap items-center gap-6 mb-8 bg-white p-4 rounded-xl shadow-sm border border-gray-100">
        <div>
          <strong>Sales Window:</strong>
          <select
  value={salesWindow}
  onChange={(e) => setSalesWindow(Number(e.target.value))}
            className="ml-2 px-3 py-2 border rounded-lg"
          >
            {[1, 2, 3, 4, 5,6, 7, 8].map((w) => (
              <option key={w} value={w}>
                {w} Week{w > 1 ? "s" : ""}
              </option>
            ))}
          </select>
        </div>

        <div>
          <strong>Search Model:</strong>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="SC-01, VC-01…"
            className="ml-2 px-3 py-2 border rounded-lg"
          />
        </div>
      </div>

      <div>
  <strong>Replenish For:</strong>
  <select
    value={replenishWeeks}
    onChange={(e) => setReplenishWeeks(Number(e.target.value))}
    className="ml-2 px-3 py-2 border rounded-lg"
  >
    {[1,2,3,4,5,6,7,8].map((w) => (
      <option key={w} value={w}>
        {w} Week{w > 1 ? "s" : ""}
      </option>
    ))}
  </select>
</div>

      {/* ================= FILTERS ================= */}
      <div style={{ display: "flex", gap: 12, marginBottom: 24 }}>
        <FilterInput label="Model" onChange={(v) => setFilters({ ...filters, model: v })} />
        <FilterInput label="ASIN" onChange={(v) => setFilters({ ...filters, asin: v })} />
        <FilterInput label="SKU" onChange={(v) => setFilters({ ...filters, sku: v })} />
        <FilterInput label="Category" onChange={(v) => setFilters({ ...filters, category: v })} />
      </div>

      {/* ================= KPIs ================= */}
      <h2>KPIs</h2>
      {kpis && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 16,
            marginBottom: 32,
          }}
        >
          <KpiCard label="Units to Replenish" value={kpis.total_units_to_replenish} />
          <KpiCard label="Avg Weeks of Cover" value={kpis.avg_weeks_of_cover?.toFixed(2)} />
        </div>
      )}

      {/* ================= REPLENISHMENT ================= */}
      <Section title="Replenishment (Live)">
        {loading ? (
          <p>Loading…</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-100 text-gray-600 uppercase text-xs">
              <tr>
                {replenishmentColumns.map((col) => (
                  <th
                    key={col}
                    style={{ ...thtd(), cursor: "pointer" }}
                    onClick={() => toggleSort(col)}
                  >
                    {col}
                    {sortConfig.key === col &&
                      (sortConfig.direction === "asc" ? " ▲" : " ▼")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedReplenishment.length === 0 && (
                <tr>
                  <td colSpan={replenishmentColumns.length} style={thtd()}>
                    No data
                  </td>
                </tr>
              )}

              {sortedReplenishment.map((row, i) => (
                <tr key={i} className="hover:bg-gray-50 transition">
                  {replenishmentColumns.map((col) => (
                    <td key={col} style={thtd()}>
                      {row[col]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
     <Section title="Final FC Allocation (AMPM → FC)">
  <table className="w-full text-sm">
    <thead className="bg-gray-100 text-gray-600 uppercase text-xs">
      <tr>
        <th style={thtd()}>SKU</th>
        <th style={thtd()}>FC</th>
        <th style={thtd()}>Send Qty</th>
      </tr>
    </thead>
    <tbody>
      {fcFinal.map((row, i) => (
        <tr key={i} className="hover:bg-gray-50 transition">
          <td style={thtd()}>{row.sku}</td>
          <td style={thtd()}>{row.fulfillment_center}</td>
          <td style={thtd()}>{row.send_qty}</td>
        </tr>
      ))}
    </tbody>
  </table>
</Section>
      {/* ================= CHART ================= */}
      <Section title="Sales vs Amazon Inventory (Top 10)">
        <SalesInventoryChart data={sortedReplenishment.slice(0, 10)} />
      </Section>
    </div>
  );
}

/* =========================================================
   COMPONENTS & HELPERS
   ========================================================= */

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 40 }}>
      <h2 style={{ marginBottom: 12 }}>{title}</h2>
      {children}
    </div>
  );
}

function FilterInput({ label, onChange }) {
  return (
    <input
      placeholder={label}
      onChange={(e) => onChange(e.target.value)}
      style={{ padding: 6 }}
    />
  );
}

function KpiCard({ label, value }) {
  return (
    <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 hover:shadow-md transition">
      <div className="text-sm text-gray-500 mb-2">{label}</div>
      <div className="text-3xl font-bold text-gray-800">
        {value ?? "-"}
      </div>
    </div>
  );
}

function SalesInventoryChart({ data }) {
  const max = Math.max(
    ...data.map((d) => Math.max(d.sales_velocity, d.amazon_inventory))
  );

  return (
    <div>
      {data.map((d, i) => (
        <div key={i} style={{ marginBottom: 10 }}>
          <strong>{d.model}</strong>
          <div style={{ display: "flex", gap: 6 }}>
            <Bar label="Sales" value={d.sales_velocity} max={max} color="#1976d2" />
            <Bar label="Inventory" value={d.amazon_inventory} max={max} color="#9e9e9e" />
          </div>
        </div>
      ))}
    </div>
  );
}

function Bar({ label, value, max, color }) {
  return (
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 12 }}>
        {label}: {value}
      </div>
      <div style={{ height: 10, background: "#eee" }}>
        <div
          style={{
            height: "100%",
            width: `${(value / max) * 100}%`,
            background: color,
          }}
        />
      </div>
    </div>
  );
}

function tableStyle() {
  return {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 14,
  };
}

function thtd() {
  return {
    border: "1px solid #ddd",
    padding: 8,
    textAlign: "left",
  };
}