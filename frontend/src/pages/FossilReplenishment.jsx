import { useEffect, useMemo, useState } from "react";

const BRANDS = [
  "All",
  "Fossil",
  "Armani Exchange",
  "Michael Kors",
  "Emporio Armani",
  "Diesel",
  "Skagen",
];

const WOC_MATRIX = [
  { brand: "Fossil",          fp: 9, discount: 4, vd: 6 },
  { brand: "Armani Exchange", fp: 6, discount: 4, vd: 6 },
  { brand: "Michael Kors",    fp: 6, discount: 4, vd: 6 },
  { brand: "Emporio Armani",  fp: 4, discount: 4, vd: 6 },
  { brand: "Diesel",          fp: 4, discount: 4, vd: 6 },
  { brand: "Skagen",          fp: 4, discount: 4, vd: 6 },
];

export default function FossilReplenishment() {

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showMatrix, setShowMatrix] = useState(false);

  const [search, setSearch] = useState("");
  const [brandFilter, setBrandFilter] = useState("All");
  const [assortmentFilter, setAssortmentFilter] = useState("All");

  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 15;

  /* LOAD DATA */
  useEffect(() => {
    setLoading(true);
    fetch(`https://am-replenishment.onrender.com/api/fossil-replenishment`)
      .then(res => res.json())
      .then(res => setData(res.data || []))
      .finally(() => setLoading(false));
  }, []);

  /* DYNAMIC BRAND OPTIONS
     Only show brands that actually exist in the data */
  const availableBrands = useMemo(() => {
    const brandsInData = new Set(data.map(r => r["Brand"]).filter(Boolean));
    return ["All", ...BRANDS.filter(b => b === "All" || brandsInData.has(b))];
  }, [data]);

  /* DYNAMIC ASSORTMENT OPTIONS
     Only show assortment types that exist for the currently selected brand */
  const availableAssortmentTypes = useMemo(() => {
    const subset = brandFilter === "All" ? data : data.filter(r => r["Brand"] === brandFilter);
    const types = new Set(subset.map(r => r["Assortment Type"]).filter(Boolean));
    // Preserve order: FP → Discount → VD
    const ordered = ["FP", "Discount", "VD"].filter(t => types.has(t));
    return ["All", ...ordered];
  }, [data, brandFilter]);

  /* If current assortmentFilter no longer exists in available options, reset it */
  useEffect(() => {
    if (assortmentFilter !== "All" && !availableAssortmentTypes.includes(assortmentFilter)) {
      setAssortmentFilter("All");
    }
  }, [availableAssortmentTypes]);

  /* FILTER */
  const filteredData = useMemo(() => {
    return data.filter(row => {
      const matchSearch = row["Item No"]?.toLowerCase().includes(search.toLowerCase());
      const matchBrand  = brandFilter === "All" || row["Brand"] === brandFilter;
      const matchAssort = assortmentFilter === "All" || row["Assortment Type"] === assortmentFilter;
      return matchSearch && matchBrand && matchAssort;
    });
  }, [data, search, brandFilter, assortmentFilter]);

  /* RESET PAGE ON FILTER CHANGE */
  useEffect(() => { setCurrentPage(1); }, [search, brandFilter, assortmentFilter]);

  /* RESET ALL FILTERS */
  function resetFilters() {
    setSearch("");
    setBrandFilter("All");
    setAssortmentFilter("All");
    setCurrentPage(1);
  }

  const isFiltered = search !== "" || brandFilter !== "All" || assortmentFilter !== "All";

  /* PAGINATION */
  const totalPages = Math.ceil(filteredData.length / rowsPerPage);

  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return filteredData.slice(start, start + rowsPerPage);
  }, [filteredData, currentPage]);

  /* KPI */
  const kpis = useMemo(() => {
    const totalRequired = filteredData.reduce((sum, r) => sum + (r["Replenishment Qty"] || 0), 0);
    const avgWeekly =
      filteredData.reduce((sum, r) => sum + (r["Fossil Weekly Sales"] || 0), 0) /
      (filteredData.length || 1);
    return { totalRequired, avgWeekly, skus: filteredData.length };
  }, [filteredData]);

  /* EXPORT */
  function exportCSV() {
    if (!filteredData.length) return;
    const headers = Object.keys(filteredData[0]).join(",");
    const rows = filteredData
      .map(row => Object.values(row).map(val => `"${val}"`).join(","))
      .join("\n");
    const blob = new Blob([headers + "\n" + rows], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "fossil_replenishment.csv";
    link.click();
  }

  /* HELPERS */
  function wocColor(weeks) {
    if (weeks >= 9) return "bg-purple-100 text-purple-700";
    if (weeks >= 6) return "bg-blue-100 text-blue-700";
    return "bg-green-100 text-green-700";
  }

  function assortBadgeColor(type) {
    if (type === "VD")       return "bg-orange-100 text-orange-700";
    if (type === "Discount") return "bg-yellow-100 text-yellow-700";
    return "bg-indigo-100 text-indigo-700";
  }

  return (
    <div className="space-y-8">

      {/* HEADER */}
      <div className="rounded-2xl p-8 bg-gradient-to-r from-indigo-900 via-indigo-800 to-indigo-900 text-white shadow-xl">
        <h1 className="text-3xl font-semibold">Fossil Replenishment Intelligence</h1>
        <p className="text-indigo-200 mt-2 text-sm">Fossil FCY Inventory Planning</p>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <MetricCard title="Units To Replenish" value={Math.round(kpis.totalRequired)} />
        <MetricCard title="Avg Weekly Sales"   value={kpis.avgWeekly?.toFixed(2)} />
        <MetricCard title="Filtered SKUs"      value={kpis.skus} />
      </div>

      {/* WEEKS OF COVER MATRIX */}
      <div>
        <button
          onClick={() => setShowMatrix(v => !v)}
          className="flex items-center gap-2 text-sm font-medium text-indigo-700 border border-indigo-200 px-4 py-2 rounded-lg hover:bg-indigo-50 transition"
        >
          <span>{showMatrix ? "▲" : "▼"}</span>
          Weeks of Cover Reference Matrix
        </button>

        {showMatrix && (
          <div className="mt-3 overflow-auto rounded-xl border shadow-sm">
            <table className="text-sm w-full">
              <thead className="bg-slate-100 text-xs uppercase">
                <tr>
                  <th className="px-5 py-3 text-left">Brand</th>
                  <th className="px-5 py-3 text-center">Full Price (FP)</th>
                  <th className="px-5 py-3 text-center">Discounted</th>
                  <th className="px-5 py-3 text-center">VD</th>
                </tr>
              </thead>
              <tbody>
                {WOC_MATRIX.map(row => (
                  <tr key={row.brand} className="border-t hover:bg-slate-50">
                    <td className="px-5 py-2 font-medium">{row.brand}</td>
                    <td className="px-5 py-2 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${wocColor(row.fp)}`}>{row.fp}w</span>
                    </td>
                    <td className="px-5 py-2 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${wocColor(row.discount)}`}>{row.discount}w</span>
                    </td>
                    <td className="px-5 py-2 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${wocColor(row.vd)}`}>{row.vd}w</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* FILTERS */}
      <div className="flex flex-wrap gap-4 items-end">

        {/* Search */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400 font-medium uppercase tracking-wide pl-1">Search</label>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search Item No..."
            className="px-4 py-2 border rounded-lg w-52"
          />
        </div>

        {/* Brand Dropdown — only brands present in data */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400 font-medium uppercase tracking-wide pl-1">Brand</label>
          <select
            value={brandFilter}
            onChange={(e) => { setBrandFilter(e.target.value); setAssortmentFilter("All"); }}
            className="px-4 py-2 border rounded-lg min-w-[180px] bg-white"
          >
            {availableBrands.map(b => (
              <option key={b} value={b}>{b === "All" ? "All Brands" : b}</option>
            ))}
          </select>
        </div>

        {/* Assortment Type — only types that exist for selected brand */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400 font-medium uppercase tracking-wide pl-1">
            Assortment Type
            {brandFilter !== "All" && (
              <span className="ml-1 text-indigo-500 normal-case font-normal">
                ({brandFilter})
              </span>
            )}
          </label>
          <select
            value={assortmentFilter}
            onChange={(e) => setAssortmentFilter(e.target.value)}
            className="px-4 py-2 border rounded-lg bg-white min-w-[160px]"
          >
            {availableAssortmentTypes.map(t => (
              <option key={t} value={t}>{t === "All" ? "All Types" : t}</option>
            ))}
          </select>
        </div>

        {/* Active filter pills */}
        <div className="flex gap-2 flex-wrap items-center">
          {brandFilter !== "All" && (
            <span className="flex items-center gap-1 px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-full text-xs font-medium">
              {brandFilter}
              <button onClick={() => { setBrandFilter("All"); setAssortmentFilter("All"); }} className="ml-1 hover:text-indigo-900 font-bold">✕</button>
            </span>
          )}
          {assortmentFilter !== "All" && (
            <span className="flex items-center gap-1 px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-full text-xs font-medium">
              {assortmentFilter}
              <button onClick={() => setAssortmentFilter("All")} className="ml-1 hover:text-indigo-900 font-bold">✕</button>
            </span>
          )}
        </div>

        {/* Reset button — only shown when filters are active */}
        {isFiltered && (
          <button
            onClick={resetFilters}
            className="px-4 py-2 border border-red-300 text-red-600 rounded-lg text-sm hover:bg-red-50 transition"
          >
            ↺ Reset Filters
          </button>
        )}

        {/* Export */}
        <div className="ml-auto">
          <button
            onClick={exportCSV}
            className="px-4 py-2 bg-indigo-900 text-white rounded-lg"
          >
            Export CSV
          </button>
        </div>

      </div>

      {/* SKU COUNT SUMMARY */}
      {isFiltered && (
        <div className="text-sm text-slate-500">
          Showing <span className="font-semibold text-slate-700">{filteredData.length}</span> SKUs
          {brandFilter !== "All" && <> for <span className="font-semibold text-indigo-700">{brandFilter}</span></>}
          {assortmentFilter !== "All" && <> · <span className="font-semibold text-indigo-700">{assortmentFilter}</span></>}
          {search && <> · matching <span className="font-semibold text-indigo-700">"{search}"</span></>}
        </div>
      )}

      {/* TABLE */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-auto max-h-[65vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-xs uppercase sticky top-0">
              <tr>
                {[
                  "SKU", "ASIN", "Item No", "Brand", "Assortment Type",
                  "Weeks of Cover", "Cambium SOH", "Total Inventory",
                  "3 Months Gross Sales", "Fossil Weekly Sales",
                  "Required Inventory", "Replenishment Qty"
                ].map(col => (
                  <th key={col} className="px-4 py-3 text-left whitespace-nowrap">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={12} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>
              ) : paginatedData.length === 0 ? (
                <tr><td colSpan={12} className="px-4 py-8 text-center text-slate-400">No results found.</td></tr>
              ) : paginatedData.map((row, i) => (
                <tr key={i} className="hover:bg-slate-50 border-b border-slate-100">
                  <td className="px-4 py-3">{row.SKU}</td>
                  <td className="px-4 py-3">{row.ASIN}</td>
                  <td className="px-4 py-3 font-medium">{row["Item No"]}</td>
                  <td className="px-4 py-3">{row.Brand}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${assortBadgeColor(row["Assortment Type"])}`}>
                      {row["Assortment Type"] || "FP"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${wocColor(row["Weeks of Cover"])}`}>
                      {row["Weeks of Cover"]}w
                    </span>
                  </td>
                  <td className="px-4 py-3">{row["Cambium SOH"]}</td>
                  <td className="px-4 py-3">{row["Total Inventory"]}</td>
                  <td className="px-4 py-3">{row["3 Months Gross Sales"]}</td>
                  <td className="px-4 py-3">{row["Fossil Weekly Sales"]?.toFixed(2)}</td>
                  <td className="px-4 py-3 font-semibold text-indigo-700">{Math.round(row["Required Inventory"])}</td>
                  <td className="px-4 py-3 text-red-600 font-semibold">{Math.round(row["Replenishment Qty"])}</td>
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
            className="px-3 py-1 border rounded disabled:opacity-40"
          >Previous</button>
          <div className="text-sm text-slate-500">Page {currentPage} of {totalPages || 1}</div>
          <button
            disabled={currentPage === totalPages || totalPages === 0}
            onClick={() => setCurrentPage(p => p + 1)}
            className="px-3 py-1 border rounded disabled:opacity-40"
          >Next</button>
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
