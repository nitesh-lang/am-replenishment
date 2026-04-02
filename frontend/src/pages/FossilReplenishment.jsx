import { useEffect, useMemo, useState } from "react";

const BRAND_ORDER = [
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
  const [assortmentFilter, setAssortmentFilter] = useState("All");
  const [brandFilter, setBrandFilter] = useState("All");

  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek, setToWeek] = useState(null);
  const [coverWeeks, setCoverWeeks] = useState(6);
  const [availableWeeks, setAvailableWeeks] = useState([]);

  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;

  /* LOAD DATA */
  useEffect(() => {
    setLoading(true);

    const params = new URLSearchParams({ cover_weeks: coverWeeks });
    if (fromWeek) params.append("from_week", fromWeek);
    if (toWeek) params.append("to_week", toWeek);

    fetch(`https://am-replenishment.onrender.com/api/fossil-replenishment?${params}`)
      .then(res => res.json())
      .then(res => {
        setData(res.data || []);
        if (res.available_weeks?.length) {
          const weeks = res.available_weeks;
          setAvailableWeeks(weeks);
          if (!fromWeek) setFromWeek(weeks[0]);
          if (!toWeek) setToWeek(weeks[weeks.length - 1]);
        }
      })
      .finally(() => setLoading(false));
  }, [fromWeek, toWeek, coverWeeks]);

  /* STEP 1 — ASSORTMENT TYPE OPTIONS
     Only show types that actually exist in the data */
  const availableAssortmentTypes = useMemo(() => {
    const types = new Set(data.map(r => r["Assortment Type"]).filter(Boolean));
    return ["All", ...["FP", "Discount", "VD"].filter(t => types.has(t))];
  }, [data]);

  /* STEP 2 — BRAND OPTIONS
     Only show brands that exist for the selected assortment type */
  const availableBrands = useMemo(() => {
    const subset = assortmentFilter === "All"
      ? data
      : data.filter(r => r["Assortment Type"] === assortmentFilter);
    const brandsInSubset = new Set(subset.map(r => r["Brand"]).filter(Boolean));
    // Preserve defined brand order
    return ["All", ...BRAND_ORDER.filter(b => brandsInSubset.has(b))];
  }, [data, assortmentFilter]);

  /* If current brandFilter no longer valid after assortment change, reset it */
  useEffect(() => {
    if (brandFilter !== "All" && !availableBrands.includes(brandFilter)) {
      setBrandFilter("All");
    }
  }, [availableBrands]);

  /* RESET PAGE ON FILTER CHANGE */
  useEffect(() => { setCurrentPage(1); }, [search, assortmentFilter, brandFilter]);

  /* FILTER DATA */
  const filteredData = useMemo(() => {
    return data.filter(row => {
      const matchSearch = row["Item No"]?.toLowerCase().includes(search.toLowerCase());
      const matchAssort = assortmentFilter === "All" || row["Assortment Type"] === assortmentFilter;
      const matchBrand  = brandFilter === "All" || row["Brand"] === brandFilter;
      return matchSearch && matchAssort && matchBrand;
    });
  }, [data, search, assortmentFilter, brandFilter]);

  /* RESET ALL */
  function resetFilters() {
    setSearch("");
    setAssortmentFilter("All");
    setBrandFilter("All");
    setCurrentPage(1);
  }

  const isFiltered = search !== "" || assortmentFilter !== "All" || brandFilter !== "All";

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

      {/* SALES WINDOW + COVER WEEKS */}
      <div className="card grid grid-cols-1 md:grid-cols-2 gap-3 py-3">

        {/* Sales Window */}
        <div>
          <label className="text-xs uppercase text-slate-400">
            Sales Window (Range)
          </label>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">From</div>
              <select
                value={fromWeek ?? ""}
                onChange={(e) => {
                  setCurrentPage(1);
                  setFromWeek(Number(e.target.value));
                }}
                className="w-full px-4 py-2 border rounded-lg"
              >
                {availableWeeks.map((w) => (
                  <option key={w} value={w}>{w}</option>
                ))}
              </select>
            </div>
            <div>
              <div className="text-xs text-slate-400 mb-1">To</div>
              <select
                value={toWeek ?? ""}
                onChange={(e) => {
                  setCurrentPage(1);
                  setToWeek(Number(e.target.value));
                }}
                className="w-full px-4 py-2 border rounded-lg"
              >
                {availableWeeks.map((w) => (
                  <option key={w} value={w}>{w}</option>
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
          <div className="grid grid-cols-1 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">&nbsp;</div>
              <select
                value={coverWeeks}
                onChange={(e) => {
                  setCurrentPage(1);
                  setCoverWeeks(Number(e.target.value));
                }}
                className="w-full px-4 py-2 border border-slate-200 rounded-lg"
              >
                {[4, 6, 8, 10, 12].map(w => (
                  <option key={w} value={w}>{w} Weeks</option>
                ))}
              </select>
            </div>
          </div>
        </div>

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

      {/* FILTERS — Assortment Type first, then Brand */}
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

        {/* STEP 1: Assortment Type */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400 font-medium uppercase tracking-wide pl-1">
            Assortment Type <span className="text-indigo-400 normal-case font-normal">(select first)</span>
          </label>
          <select
            value={assortmentFilter}
            onChange={(e) => { setAssortmentFilter(e.target.value); setBrandFilter("All"); }}
            className="px-4 py-2 border rounded-lg bg-white min-w-[160px]"
          >
            {availableAssortmentTypes.map(t => (
              <option key={t} value={t}>{t === "All" ? "All Types" : t}</option>
            ))}
          </select>
        </div>

        {/* STEP 2: Brand — filtered by assortment type */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400 font-medium uppercase tracking-wide pl-1">
            Brand
            {assortmentFilter !== "All" && (
              <span className="ml-1 text-indigo-400 normal-case font-normal">
                ({availableBrands.length - 1} available)
              </span>
            )}
          </label>
          <select
            value={brandFilter}
            onChange={(e) => setBrandFilter(e.target.value)}
            className="px-4 py-2 border rounded-lg min-w-[180px] bg-white"
          >
            {availableBrands.map(b => (
              <option key={b} value={b}>{b === "All" ? "All Brands" : b}</option>
            ))}
          </select>
        </div>

        {/* Active filter pills */}
        <div className="flex gap-2 flex-wrap items-center">
          {assortmentFilter !== "All" && (
            <span className="flex items-center gap-1 px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-full text-xs font-medium">
              {assortmentFilter}
              <button onClick={() => { setAssortmentFilter("All"); setBrandFilter("All"); }} className="ml-1 hover:text-indigo-900 font-bold">✕</button>
            </span>
          )}
          {brandFilter !== "All" && (
            <span className="flex items-center gap-1 px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-full text-xs font-medium">
              {brandFilter}
              <button onClick={() => setBrandFilter("All")} className="ml-1 hover:text-indigo-900 font-bold">✕</button>
            </span>
          )}
        </div>

        {/* Reset */}
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
          <button onClick={exportCSV} className="px-4 py-2 bg-indigo-900 text-white rounded-lg">
            Export CSV
          </button>
        </div>

      </div>

      {/* SKU COUNT SUMMARY */}
      {isFiltered && (
        <div className="text-sm text-slate-500">
          Showing <span className="font-semibold text-slate-700">{filteredData.length}</span> SKUs
          {assortmentFilter !== "All" && <> · <span className="font-semibold text-indigo-700">{assortmentFilter}</span></>}
          {brandFilter !== "All" && <> · <span className="font-semibold text-indigo-700">{brandFilter}</span></>}
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
                  "Weeks of Cover", "Fossil SOH", "Total Inventory",
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
                  <td className="px-4 py-3">{row["Fossil SOH"]}</td>
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