import { useEffect, useMemo, useState } from "react";

export default function FossilReplenishment() {

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [coverWeeks, setCoverWeeks] = useState(8);

  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 15;

  /* LOAD DATA */

  useEffect(() => {

    setLoading(true);

    fetch(`https://am-replenishment.onrender.com/api/fossil-replenishment?weeks=${coverWeeks}`)
      .then(res => res.json())
      .then(res => setData(res.data || []))
      .finally(() => setLoading(false));

  }, [coverWeeks]);

  /* FILTER */

  const filteredData = useMemo(() => {

    return data.filter(row =>
      row["Item No"]?.toLowerCase().includes(search.toLowerCase())
    );

  }, [data, search]);

  /* PAGINATION */

  const totalPages = Math.ceil(filteredData.length / rowsPerPage);

  const paginatedData = useMemo(() => {

    const start = (currentPage - 1) * rowsPerPage;

    return filteredData.slice(start, start + rowsPerPage);

  }, [filteredData, currentPage]);

  /* KPI */

  const kpis = useMemo(() => {

    const totalRequired = filteredData.reduce(
      (sum, r) => sum + (r["Replenishment Qty"] || 0),
      0
    );

    const avgWeekly =
      filteredData.reduce((sum, r) => sum + (r["Fossil Weekly Sales"] || 0), 0) /
      (filteredData.length || 1);

    return {
      totalRequired,
      avgWeekly,
      skus: filteredData.length
    };

  }, [filteredData]);

  /* EXPORT */

  function exportCSV() {

    if (!filteredData.length) return;

    const headers = Object.keys(filteredData[0]).join(",");

    const rows = filteredData
      .map(row =>
        Object.values(row)
          .map(val => `"${val}"`)
          .join(",")
      )
      .join("\n");

    const blob = new Blob([headers + "\n" + rows], {
      type: "text/csv;charset=utf-8;"
    });

    const link = document.createElement("a");

    link.href = URL.createObjectURL(blob);
    link.download = "fossil_replenishment.csv";

    link.click();
  }

  return (
    <div className="space-y-10">

      {/* HEADER */}

      <div className="rounded-2xl p-8 bg-gradient-to-r from-indigo-900 via-indigo-800 to-indigo-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">
          Fossil Replenishment Intelligence
        </h1>
        <p className="text-indigo-200 mt-2 text-sm">
          Fossil FCY Inventory Planning
        </p>
      </div>

      {/* KPI */}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <MetricCard title="Units To Replenish" value={Math.round(kpis.totalRequired)} />
        <MetricCard title="Avg Weekly Sales" value={kpis.avgWeekly?.toFixed(2)} />
        <MetricCard title="Filtered SKUs" value={kpis.skus} />
      </div>

      {/* FILTER */}

      <div className="flex gap-4">

        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search Item No..."
          className="px-4 py-2 border rounded-lg w-64"
        />

        <select
          value={coverWeeks}
          onChange={(e) => setCoverWeeks(Number(e.target.value))}
          className="px-4 py-2 border rounded-lg"
        >
          {[4,6,8,10,12].map(w => (
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
                  "SKU",
                  "ASIN",
                  "Item No",
                  "Brand",
                  "Cambium SOH",
                  "Total Inventory",
                  "3 Months Gross Sales",
                  "Fossil Weekly Sales",
                  "Required Inventory",
                  "Replenishment Qty"
                ].map(col => (
                  <th key={col} className="px-4 py-3">{col}</th>
                ))}
              </tr>
            </thead>

            <tbody>

              {paginatedData.map((row, i) => (

                <tr key={i} className="hover:bg-slate-50">

                  <td className="px-4 py-3">{row.SKU}</td>
                  <td className="px-4 py-3">{row.ASIN}</td>
                  <td className="px-4 py-3 font-medium">{row["Item No"]}</td>
                  <td className="px-4 py-3">{row.Brand}</td>
                  <td className="px-4 py-3">{row["Cambium SOH"]}</td>
                  <td className="px-4 py-3">{row["Total Inventory"]}</td>
                  <td className="px-4 py-3">{row["3 Months Gross Sales"]}</td>
                  <td className="px-4 py-3">{row["Fossil Weekly Sales"]?.toFixed(2)}</td>
                  <td className="px-4 py-3 font-semibold text-indigo-700">
                    {Math.round(row["Required Inventory"])}
                  </td>
                  <td className="px-4 py-3 text-red-600 font-semibold">
                    {Math.round(row["Replenishment Qty"])}
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
            onClick={() => setCurrentPage(p => p - 1)}
          >
            Previous
          </button>

          <div>
            Page {currentPage} of {totalPages}
          </div>

          <button
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage(p => p + 1)}
          >
            Next
          </button>

        </div>

      </div>

    </div>
  );
}

function MetricCard({ title, value }) {

  return (
    <div className="p-6 bg-white rounded-xl shadow-sm border">
      <div className="text-xs uppercase text-slate-400">{title}</div>
      <div className="text-3xl font-semibold mt-3">{value}</div>
    </div>
  );

}