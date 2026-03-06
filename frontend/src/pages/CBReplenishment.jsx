import { useEffect, useMemo, useState } from "react";

/* ============================================================
   MAIN COMPONENT
============================================================ */

export default function CBReplenishment() {

  /* STATE */

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [selectedBrand, setSelectedBrand] = useState("Audio Array");

  const [coverWeeks, setCoverWeeks] = useState(8);

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: "asc",
  });

  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 15;

  /* ============================================================
     LOAD DATA
  ============================================================ */

  useEffect(() => {
    setLoading(true);

    fetch("https://am-replenishment.onrender.com/api/cb-replenishment/")
      .then((res) => res.json())
      .then((res) => {
        setData(res.data || []);
      })
      .finally(() => setLoading(false));

  }, []);

  /* ============================================================
     FILTER
  ============================================================ */

  const filteredData = useMemo(() => {
    return data
      .filter((row) => row.brand === selectedBrand)
      .filter((row) =>
        row.model?.toLowerCase().includes(search.toLowerCase())
      );
  }, [data, search, selectedBrand]);

  /* ============================================================
     CALCULATIONS
  ============================================================ */

  const calculatedData = useMemo(() => {

    return filteredData.map((row) => {

      const avgWeekly = row.avg_weekly_sales || 0;

      const estimated = avgWeekly * coverWeeks;

      const deficiency = Math.max(
        0,
        estimated - (row.final_cb_qty || 0)
      );

      const poRequirement = deficiency;

      return {
        ...row,
        estimated_qty: estimated,
        deficiency,
        po_requirement: poRequirement,
        };

    });

  }, [filteredData, coverWeeks]);

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

      {/* FILTER */}

      <div className="flex gap-4">

        <select
          value={selectedBrand}
          onChange={(e) => setSelectedBrand(e.target.value)}
          className="px-4 py-2 border rounded-lg"
        >
          <option>Audio Array</option>
          <option>Tonor</option>
        </select>

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search model..."
          className="px-4 py-2 border rounded-lg w-64"
        />

        <select
          value={coverWeeks}
          onChange={(e) => setCoverWeeks(Number(e.target.value))}
          className="px-4 py-2 border rounded-lg"
        >
          {[4,5,6,7,8,9,10,11,12].map(w => (
            <option key={w}>{w}</option>
          ))}
        </select>

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
                  "final_cb_qty",
                  "cb_3m_sales",
                  "cambium_3m_sales",
                  "avg_weekly_sales",
                  "estimated_qty",
                  "deficiency",
                  "po_requirement",
                  "remarks"
                ].map((col) => (
                  <th
                    key={col}
                    onClick={() => toggleSort(col)}
                    className="px-4 py-3 cursor-pointer"
                  >
                    {col}
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
                    {row.final_cb_qty}
                  </td>

                  <td className="px-4 py-3">
                    {row.cb_3m_sales}
                  </td>

                  <td className="px-4 py-3">
                    {row.cambium_3m_sales}
                  </td>

                  <td className="px-4 py-3">
                    {row.avg_weekly_sales?.toFixed(2)}
                  </td>

                  <td className="px-4 py-3 font-semibold text-indigo-700">
                    {Math.round(row.estimated_qty)}
                  </td>

                  <td className="px-4 py-3 text-red-600 font-semibold">
                    {Math.round(row.deficiency)}
                  </td>

                  <td className="px-4 py-3 font-semibold">
  {Math.round(row.po_requirement)}
</td>

<td className="px-4 py-3">
  <input
    type="text"
    placeholder="Remarks"
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