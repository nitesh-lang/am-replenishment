import { useEffect, useMemo, useState, useRef } from "react";

/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function CBReplenishment() {

  /* STATE */

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [selectedBrand, setSelectedBrand] = useState("All");

  const [fromWeek, setFromWeek] = useState(52);
  const [toWeek, setToWeek] = useState(11);
  const [coverWeeks, setCoverWeeks] = useState(8);

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  const [currentPage, setCurrentPage] = useState(1);
const rowsPerPage = 15;
const remarkTimerRef = useRef(null);

// Generate valid "To" weeks — max 12 weeks from fromWeek (with wraparound)
const validToWeeks = useMemo(() => {
  const weeks = [];
  for (let i = 0; i < 12; i++) {
    const week = ((fromWeek - 1 + i) % 52) + 1;
    weeks.push(week);
  }
  return weeks;
}, [fromWeek]);

// Valid "From" weeks — 12 options ending at toWeek
const validFromWeeks = useMemo(() => {
  const weeks = [];
  for (let i = 11; i >= 0; i--) {
    const week = ((toWeek - 1 - i + 52) % 52) + 1;
    weeks.push(week);
  }
  return weeks;
}, [toWeek]);

  /* ============================================================
     LOAD DATA
  ============================================================ */

  useEffect(() => {
    setLoading(true);

    const params = new URLSearchParams({
      from_week: fromWeek,
      to_week: toWeek,
      cover_weeks: coverWeeks,
    });

    fetch(`https://am-replenishment.onrender.com/api/cb-replenishment/?${params}`)
      .then((res) => res.json())
      .then((res) => {
        setData(res.data || []);
      })
      .finally(() => setLoading(false));

  }, [fromWeek, toWeek, coverWeeks]);

  /* ============================================================
     FILTER
  ============================================================ */

  const filteredData = useMemo(() => {
    return data
      .filter((row) => selectedBrand === "All" || row.brand === selectedBrand)
      .filter((row) =>
        row.model?.toLowerCase().includes(search.toLowerCase())
      );
  }, [data, search, selectedBrand]);

  /* ============================================================
     CALCULATIONS
     avg_weekly_sales is recalculated from cb_3m_sales using
     the selected sales window (fromWeek → toWeek).
     coverWeeks remains a separate control for estimated_qty.
  ============================================================ */

  // Backend handles all calculations using from_week, to_week, cover_weeks.
  // Frontend just passes filtered data through unchanged.
  const calculatedData = filteredData;

  /* ============================================================
     SORT
  ============================================================ */

  const sortedData = useMemo(() => {

    if (!sortConfig.key) return calculatedData;

    const direction = sortConfig.direction === "asc" ? 1 : -1;

    return [...calculatedData].sort((a, b) => {

      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];

      if (aVal == null) return 1;
      if (bVal == null) return -1;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return (aVal - bVal) * direction;
      }

      return aVal.toString().localeCompare(bVal.toString()) * direction;

    });

  }, [calculatedData, sortConfig]);

  function toggleSort(column) {
    setSortConfig((prev) => ({
      key: column,
      direction:
        prev.key === column && prev.direction === "asc"
          ? "desc"
          : "asc",
    }));
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
     KPI
  ============================================================ */

  const kpis = useMemo(() => {

    const totalRequired = sortedData.reduce(
      (sum, r) => sum + (r.deficiency || 0),
      0
    );

    const avgVelocity =
      sortedData.reduce((sum, r) => sum + (r.avg_weekly_sales || 0), 0) /
      (sortedData.length || 1);

    return {
      totalRequired,
      avgVelocity,
      models: sortedData.length,
    };

  }, [sortedData]);

  /* ============================================================
     EXPORT
  ============================================================ */

  function exportCSV() {

    if (!sortedData.length) return;

    const headerMap = { "hazmat_type": "ASIN Sort Details" };
    const headers = Object.keys(sortedData[0]).map(k => headerMap[k] || k).join(",");

    const rows = sortedData
      .map((row) =>
        Object.keys(row).map(key => {
          const val = row[key];
          if (["avg_weekly_sales","estimated_qty","deficiency"].includes(key)) {
            return `"${Math.round(val)}"`;
          }
          return `"${val ?? ""}"`;
        }).join(",")
      )
      .join("\n");

    const blob = new Blob([headers + "\n" + rows], {
      type: "text/csv;charset=utf-8;",
    });

    const link = document.createElement("a");

    link.href = URL.createObjectURL(blob);

    link.download = "cb_replenishment.csv";

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
          CB Replenishment Intelligence
        </h1>
        <p className="text-indigo-200 mt-2 text-sm">
          Cambium / CB Inventory Planning
        </p>
      </div>

      {/* KPI */}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <MetricCard title="Units Required" value={Math.round(kpis.totalRequired)} />
        <MetricCard title="Avg Weekly Sales" value={kpis.avgVelocity?.toFixed(2)} />
        <MetricCard title="Models" value={kpis.models} />
      </div>

      {/* SALES WINDOW + COVER WEEKS */}

      <div className="card grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Sales Window */}
        <div>
          <label className="text-xs uppercase text-slate-400">
            Sales Window (Range)
          </label>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">From</div>
              <select
                value={fromWeek}
                onChange={(e) => {
                  setCurrentPage(1);
                  const newFrom = Number(e.target.value);
                  setFromWeek(newFrom);
                  const autoTo = ((newFrom - 1 + 11) % 52) + 1;
                  setToWeek(autoTo);
                }}
                className="w-full px-4 py-2 border rounded-lg"
              >
                {validFromWeeks.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div className="text-xs text-slate-400 mb-1">To</div>
              <select
                value={toWeek}
                onChange={(e) => {
                  setCurrentPage(1);
                  setToWeek(Number(e.target.value));
                }}
                className="w-full px-4 py-2 border rounded-lg"
              >
                {validToWeeks.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Cover Weeks */}
        <div>
          <label className="text-xs uppercase tracking-wider text-slate-400">
            Cover Weeks
          </label>
          <select
            value={coverWeeks}
            onChange={(e) => {
              setCurrentPage(1);
              setCoverWeeks(Number(e.target.value));
            }}
            className="mt-2 w-full px-4 py-2 border border-slate-200 rounded-lg"
          >
            {[4,5,6,7,8,9,10,11,12].map(w => (
              <option key={w} value={w}>
                {w} Week{w > 1 ? "s" : ""}
              </option>
            ))}
          </select>
        </div>

      </div>

      {/* FILTER */}

      <div className="flex gap-4">

        <select
          value={selectedBrand}
          onChange={(e) => setSelectedBrand(e.target.value)}
          className="px-4 py-2 border rounded-lg"
        >
          <option value="All">All</option>
          <option>Audio Array</option>
          <option>Tonor</option>
        </select>

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
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
                {[
                  "model",
                  "china_in_transit",
                  "final_cb_qty",
                  "ampm_inventory",
                  "cb_3m_sales",
                  "cambium_3m_sales",
                  "avg_weekly_sales",
                  "estimated_qty",
                  "deficiency",
                  "open_po",
                  "in_transit",
                  "asin_sort_details",
                  "po_requirement",
                  "remarks",
                ].map((col) => (
                  <th
                    key={col}
                    onClick={() => toggleSort(col)}
                    className="px-4 py-3 cursor-pointer"
                  >
                    {col === "hazmat_type" ? "ASIN Sort Details" : col}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>

              {paginatedData.map((row, i) => (

                <tr key={i} className="hover:bg-slate-50">

                  <td className="px-4 py-3 font-medium">
                    {row.model}
                  </td>

                  <td className="px-4 py-3">
                    {row.china_in_transit ?? 0}
                  </td>

                  <td className="px-4 py-3">
                    {row.final_cb_qty}
                  </td>

                  <td className="px-4 py-3">
                    {row.ampm_inventory ?? 0}
                  </td>

                  <td className="px-4 py-3">
                    {row.cb_3m_sales}
                  </td>

                  <td className="px-4 py-3">
                    {row.cambium_3m_sales}
                  </td>

                  <td className="px-4 py-3">
                    {Math.round(row.avg_weekly_sales)}
                  </td>

                  <td className="px-4 py-3 font-semibold text-indigo-700">
                    {Math.round(row.estimated_qty)}
                  </td>

                  <td className="px-4 py-3 text-red-600 font-semibold">
                    {Math.round(row.deficiency)}
                  </td>

                  <td className="px-4 py-3">
                    {row.open_po}
                  </td>

                  <td className="px-4 py-3">
                    {row.in_transit}
                  </td>

                  <td className="px-4 py-3">
                    {row.hazmat_type || "-"}
                  </td>

                  <td className="px-4 py-3">
                    <input
                      type="number"
                      value={row.po_requirement || 0}
                      onChange={(e) => {
                        const value = Number(e.target.value);

                        const newData = data.map(d =>
                          d.model === row.model ? { ...d, po_requirement: value } : d
                        );
                        setData(newData);

                        fetch("https://am-replenishment.onrender.com/api/cb-replenishment/save", {
                          method: "POST",
                          headers: {"Content-Type": "application/json"},
                          body: JSON.stringify({
                            model: row.model,
                            po_requirement: value,
                            remarks: row.remarks || ""
                          })
                        });
                      }}
                      className="border rounded px-2 py-1 w-24"
                    />
                  </td>

                  <td className="px-4 py-3">
                    <input
                      type="text"
                      defaultValue={row.remarks ?? ""}
                      onBlur={(e) => {
                        const value = e.target.value;
                        fetch("https://am-replenishment.onrender.com/api/cb-replenishment/save", {
                          method: "POST",
                          headers: {"Content-Type": "application/json"},
                          body: JSON.stringify({
                            model: row.model,
                            po_requirement: row.po_requirement || 0,
                            remarks: value
                          })
                        });
                      }}
                      className="border rounded px-2 py-1 w-full"
                    />
                  </td>

                </tr>

              ))}

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
   COMPONENTS
============================================================ */

function MetricCard({ title, value }) {

  return (
    <div className="p-6 bg-white rounded-xl shadow-sm border">
      <div className="text-xs uppercase text-slate-400">{title}</div>
      <div className="text-3xl font-semibold mt-3">{value}</div>
    </div>
  );

}
