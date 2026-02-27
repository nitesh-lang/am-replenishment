import { useEffect, useMemo, useState } from "react";

/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function ChinaReorderWorking() {

  /* ============================================================
     STATE
  ============================================================ */

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [selectedBrand, setSelectedBrand] = useState("");
  const [selectedChannel, setSelectedChannel] = useState("");

  const [search, setSearch] = useState("");

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  /* Pagination */
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 20;

  /* ============================================================
     DATA LOAD
  ============================================================ */

  useEffect(() => {
    setLoading(true);

    fetch(
  `https://am-replenishment.onrender.com/api/china-reorder-working?brand=${selectedBrand}&channel=${selectedChannel}`
)
      .then((res) => res.json())
      .then((res) => {
        setData(Array.isArray(res) ? res : []);
      })
      .finally(() => setLoading(false));
  }, [selectedBrand, selectedChannel]);

  /* ============================================================
     FILTER
  ============================================================ */

 const filteredData = useMemo(() => {
  return data.filter((row) =>
    String(row.model || "")
      .toLowerCase()
      .includes(search.toLowerCase())
  );
}, [data, search]);

  /* ============================================================
     SORT
  ============================================================ */

  const sortedData = useMemo(() => {
    if (!sortConfig.key) return filteredData;

    const direction = sortConfig.direction === "asc" ? 1 : -1;

    return [...filteredData].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];

      if (aVal == null) return 1;
      if (bVal == null) return -1;

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
     KPI SECTION
  ============================================================ */

  const kpis = useMemo(() => {
    const totalUnits = sortedData.reduce(
      (sum, r) => sum + (r.units_sold || 0),
      0
    );

    const totalInventory = sortedData.reduce(
      (sum, r) => sum + (r.total_inventory || 0),
      0
    );

    return {
      totalUnits,
      totalInventory,
      rows: sortedData.length,
    };
  }, [sortedData]);

  /* ============================================================
     CSV EXPORT
  ============================================================ */

  function exportCSV() {
    if (!sortedData.length) return;

    const headers = Object.keys(sortedData[0]).join(",");
    const rows = sortedData
      .map((row) =>
        Object.values(row)
          .map((val) => `"${val}"`)
          .join(",")
      )
      .join("\n");

    const blob = new Blob([headers + "\n" + rows], {
      type: "text/csv;charset=utf-8;",
    });

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "china_reorder_working.csv";
    link.click();
  }

  /* ============================================================
     RENDER
  ============================================================ */

  return (
    <div className="space-y-10">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-indigo-900 via-indigo-800 to-indigo-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          China Reorder Working View
        </h1>
        <p className="text-indigo-200 mt-2 text-sm">
          Raw 12-Week Sales Snapshot + Inventory Universe Transparency
        </p>
      </div>

      {/* KPI SECTION */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <MetricCard title="Total Units Sold" value={kpis.totalUnits} />
        <MetricCard title="Total Inventory (Universe)" value={kpis.totalInventory} />
        <MetricCard title="Rows Loaded" value={kpis.rows} />
      </div>

      {/* FILTERS */}
      <div className="flex gap-4 items-center flex-wrap">

        <select
          value={selectedBrand}
          onChange={(e) => {
            setCurrentPage(1);
            setSelectedBrand(e.target.value);
          }}
          className="px-4 py-2 border rounded-lg"
        >
          <option value="">All Brands</option>
          <option value="Nexlev">Nexlev</option>
          <option value="Audio Array">Audio Array</option>
          <option value="Tonor">Tonor</option>
          <option value="White Mulberry">White Mulberry</option>
        </select>

        <input
          placeholder="Channel (Amazon, 1p Sales...)"
          value={selectedChannel}
          onChange={(e) => {
            setCurrentPage(1);
            setSelectedChannel(e.target.value);
          }}
          className="px-4 py-2 border rounded-lg"
        />

        <input
          value={search}
          onChange={(e) => {
            setCurrentPage(1);
            setSearch(e.target.value);
          }}
          placeholder="Search model..."
          className="px-4 py-2 border rounded-lg w-64"
        />

        <button
          onClick={exportCSV}
          className="px-4 py-2 bg-indigo-900 text-white rounded-lg"
        >
          Export CSV
        </button>
      </div>

      {/* TABLE */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-auto max-h-[65vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-xs uppercase sticky top-0">
              <tr>
                {data[0] &&
                  Object.keys(data[0]).map((col) => (
                    <th
                      key={col}
                      onClick={() => toggleSort(col)}
                      className="px-4 py-3 cursor-pointer"
                    >
                      {col} {getSortArrow(col)}
                    </th>
                  ))}
              </tr>
            </thead>

            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="100%" className="text-center py-10">
                    Loading...
                  </td>
                </tr>
              ) : (
                paginatedData.map((row, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    {Object.values(row).map((val, index) => (
                      <td key={index} className="px-4 py-3">
                        {val}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* PAGINATION */}
        <div className="flex justify-between items-center p-4 border-t">
          <button
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => p - 1)}
          >
            Previous
          </button>

          <div>
            Page {currentPage} of {totalPages || 1}
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
   KPI CARD
============================================================ */

function MetricCard({ title, value }) {
  return (
    <div className="p-6 bg-white rounded-xl shadow-sm border">
      <div className="text-xs uppercase text-slate-400">{title}</div>
      <div className="text-3xl font-semibold mt-3">{value}</div>
    </div>
  );
}