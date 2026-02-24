import { useEffect, useMemo, useState } from "react";

/* ============================================================
   REGION SALES – SAAS VERSION
============================================================ */

export default function RegionSales() {

  /* ============================================================
     STATE
  ============================================================ */

  const [account, setAccount] = useState("NEXLEV");
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "desc",
  });

  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 15;

  /* ============================================================
     DATA LOAD
  ============================================================ */

  useEffect(() => {
    setLoading(true);

    fetch(`https://am-replenishment.onrender.com/region-sales?account=${account}`)
      .then((res) => res.json())
      .then((res) => {
        setData(Array.isArray(res) ? res : []);
      })
      .finally(() => setLoading(false));
  }, [account]);

  /* ============================================================
     FILTER
  ============================================================ */

  const filteredData = useMemo(() => {
    return data.filter((row) =>
      row.sku?.toLowerCase().includes(search.toLowerCase()) ||
      row.region?.toLowerCase().includes(search.toLowerCase())
    );
  }, [data, search]);

  /* ============================================================
     SORT
  ============================================================ */

  const sortedData = useMemo(() => {
    if (!sortConfig.key) return filteredData;

    const direction = sortConfig.direction === "asc" ? 1 : -1;

    return [...filteredData].sort((a, b) => {
      const aVal = a[sortConfig.key] ?? 0;
      const bVal = b[sortConfig.key] ?? 0;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return (aVal - bVal) * direction;
      }

      return aVal.toString().localeCompare(bVal.toString()) * direction;
    });
  }, [filteredData, sortConfig]);

  function toggleSort(column) {
    setSortConfig((prev) => ({
      key: column,
      direction:
        prev.key === column && prev.direction === "asc"
          ? "desc"
          : "asc",
    }));
  }

  function getSortArrow(column) {
    if (sortConfig.key !== column) return "";
    return sortConfig.direction === "asc" ? "▲" : "▼";
  }

  /* ============================================================
     PAGINATION
  ============================================================ */

  const totalPages = Math.ceil(sortedData.length / rowsPerPage);

  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return sortedData.slice(start, start + rowsPerPage);
  }, [sortedData, currentPage]);

  /* ============================================================
     KPI CALCULATIONS
  ============================================================ */

  const kpis = useMemo(() => {

    const totalUnits = filteredData.reduce(
      (sum, row) => sum + (row.total_units_30d || 0),
      0
    );
    const totalRevenue = filteredData.reduce(
  (sum, row) => sum + (row.revenue_30d || 0),
  0
);

    const uniqueSKUs = new Set(filteredData.map((r) => r.sku)).size;
    const uniqueRegions = new Set(filteredData.map((r) => r.region)).size;

    const topRegion =
      Object.entries(
        filteredData.reduce((acc, row) => {
          acc[row.region] =
            (acc[row.region] || 0) + (row.total_units_30d || 0);
          return acc;
        }, {})
      )
        .sort((a, b) => b[1] - a[1])[0]?.[0] || "-";

    return { totalUnits, totalRevenue, uniqueSKUs, uniqueRegions, topRegion };

  }, [filteredData]);

  /* ============================================================
     REGION STATUS LOGIC
  ============================================================ */

  function getRegionStatus(row) {
    if (row.weekly_velocity > 5) return "HOT";
    if (row.weekly_velocity < 1) return "SLOW";
    return "STABLE";
  }

  function statusBadge(status) {
    if (status === "HOT") return "bg-red-100 text-red-700";
    if (status === "SLOW") return "bg-yellow-100 text-yellow-700";
    return "bg-emerald-100 text-emerald-700";
  }

  function statusRowColor(status) {
    if (status === "HOT") return "bg-red-50";
    if (status === "SLOW") return "bg-yellow-50";
    return "bg-emerald-50/40";
  }

  /* ============================================================
     EXPORT CSV
  ============================================================ */

  function exportCSV() {
    const headers = [
      "sku",
      "region",
      "total_units_30d",
      "weekly_velocity",
      "revenue_30d",
    ];

    const rows = filteredData
      .map((row) =>
        headers.map((col) => row[col]).join(",")
      )
      .join("\n");

    const blob = new Blob(
      [headers.join(",") + "\n" + rows],
      { type: "text/csv;charset=utf-8;" }
    );

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "region_sales_export.csv";
    link.click();
  }

  /* ============================================================
     RENDER
  ============================================================ */

  return (
    <div className="space-y-10">

      <div className="rounded-2xl p-8 bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          Nexlev Region Sales Intelligence
        </h1>
        <p className="text-slate-300 mt-2 text-sm">
          30-day regional performance & velocity insights
        </p>
      </div>

      <div className="card grid grid-cols-1 md:grid-cols-3 gap-6">
        <div>
          <label className="text-xs uppercase text-slate-400">
            Search SKU or Region
          </label>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mt-2 w-full px-4 py-2 border rounded-lg"
          />
        </div>
        <div>
  <label className="text-xs uppercase text-slate-400">
    Account
  </label>
  <select
    value={account}
    onChange={(e) => setAccount(e.target.value)}
    className="mt-2 w-full px-4 py-2 border rounded-lg"
  >
    <option value="NEXLEV">Nexlev</option>
    <option value="VIOMI">Viomi</option>
  </select>
</div>
        <div className="flex items-end">
          <button
            onClick={exportCSV}
            className="px-4 py-2 bg-slate-900 text-white rounded-lg"
          >
            Export CSV
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <MetricCard title="Total Units (30d)" value={kpis.totalUnits} />
        <MetricCard title="Unique SKUs" value={kpis.uniqueSKUs} />
        <MetricCard title="Regions Covered" value={kpis.uniqueRegions} />
        <MetricCard title="Top Region" value={kpis.topRegion} />
        <MetricCard title="Total Revenue (30d)" value={`₹ ${kpis.totalRevenue?.toFixed(0)}`} />
      </div>

      <div className="card p-0 overflow-hidden">

        {loading ? (
          <div className="p-8 text-slate-400">Loading data...</div>
        ) : (
          <div className="overflow-auto max-h-[65vh]">
            <table className="w-full text-sm">

              <thead className="bg-slate-100 sticky top-0 z-20">
                <tr>
                  <th className="px-4 py-3">Status</th>

                  <th onClick={() => toggleSort("sku")} className="px-4 py-3 cursor-pointer">
                    SKU {getSortArrow("sku")}
                  </th>

                  <th onClick={() => toggleSort("region")} className="px-4 py-3 cursor-pointer">
                    Region {getSortArrow("region")}
                  </th>

                  <th onClick={() => toggleSort("total_units_30d")} className="px-4 py-3 cursor-pointer">
                    Total 30d {getSortArrow("total_units_30d")}
                  </th>

                  <th onClick={() => toggleSort("weekly_velocity")} className="px-4 py-3 cursor-pointer">
                    Weekly {getSortArrow("weekly_velocity")}
                  </th>

                  <th onClick={() => toggleSort("revenue_30d")} className="px-4 py-3 cursor-pointer">
                    Revenue (30d) {getSortArrow("revenue_30d")}
                  </th>
                </tr>
              </thead>

              <tbody>
                {paginatedData.map((row, i) => {
                  const status = getRegionStatus(row);

                  return (
                    <tr
                      key={i}
                      className={`border-b hover:bg-slate-50 transition ${statusRowColor(status)}`}
                    >
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-1 text-xs rounded ${statusBadge(status)}`}
                        >
                          {status}
                        </span>
                      </td>

                      <td className="px-4 py-3">{row.sku}</td>
                      <td className="px-4 py-3">{row.region}</td>

                      <td className="px-4 py-3 font-semibold">
                        {row.total_units_30d}
                      </td>

                      <td className="px-4 py-3">
                        {row.weekly_velocity?.toFixed(2)}
                      </td>

                      <td className="px-4 py-3 font-semibold">
                        ₹ {row.revenue_30d?.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>

            </table>
          </div>
        )}

        <div className="flex justify-between items-center p-4 border-t">
          <button
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => p - 1)}
          >
            Previous
          </button>

          <div>
            Page {currentPage} of {totalPages}
          </div>

          <button
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage((p) => p + 1)}
          >
            Next
          </button>
        </div>

      </div>

    </div>
  );
}

/* ============================================================
   COMPONENT
============================================================ */

function MetricCard({ title, value }) {
  return (
    <div className="p-6 bg-white border rounded-xl shadow-sm hover:shadow-md transition">
      <div className="text-xs uppercase text-slate-400">
        {title}
      </div>
      <div className="text-2xl font-semibold mt-3">
        {value ?? "-"}
      </div>
    </div>
  );
}