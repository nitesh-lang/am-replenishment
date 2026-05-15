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

  const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8060";

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showMatrix, setShowMatrix] = useState(false);

  const [search, setSearch] = useState("");
  const [assortmentFilter, setAssortmentFilter] = useState("All");
  const [brandFilter, setBrandFilter] = useState("All");

  const [fromWeek, setFromWeek] = useState(null);
  const [toWeek, setToWeek] = useState(null);
  const [coverWeeks, setCoverWeeks] = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);

  const [sortConfig, setSortConfig] = useState({ key: null, direction: "asc" });
  const [currentPage, setCurrentPage] = useState(1);
  const rowsPerPage = 50;
  const [sopOpen, setSopOpen] = useState(false);

  /* LOAD DATA */
  useEffect(() => {
    setLoading(true);

    const params = new URLSearchParams();
    if (coverWeeks) params.append("cover_weeks", coverWeeks);
    if (fromWeek) params.append("from_week", fromWeek);
    if (toWeek) params.append("to_week", toWeek);

    fetch(`${BASE}/api/fossil-replenishment?${params}`)
      .then(res => res.json())
      .then(res => {
        setData(res.data || []);
        if (res.available_weeks?.length) {
          const weeks = res.available_weeks;
          setAvailableWeeks(weeks);
          if (!fromWeek) {
            // Default to last 12 weeks (e.g. weeks 8-19 when data is 6-19)
            const defaultFrom = weeks.length > 12 ? weeks[weeks.length - 12] : weeks[0];
            setFromWeek(defaultFrom);
          }
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
      const matchSearch =
        String(row["Item No"] ?? "").toLowerCase().includes(search.toLowerCase()) ||
        String(row["SKU"] ?? "").toLowerCase().includes(search.toLowerCase()) ||
        String(row["ASIN"] ?? "").toLowerCase().includes(search.toLowerCase());
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

  /* SORT */
  function toggleSort(col) {
    setSortConfig(prev => ({
      key: col,
      direction: prev.key === col && prev.direction === "asc" ? "desc" : "asc",
    }));
  }

  const sortedData = useMemo(() => {
    if (!sortConfig.key) return filteredData;
    const dir = sortConfig.direction === "asc" ? 1 : -1;
    return [...filteredData].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === "number" && typeof bVal === "number") return (aVal - bVal) * dir;
      return aVal.toString().localeCompare(bVal.toString()) * dir;
    });
  }, [filteredData, sortConfig]);

  /* PAGINATION */
  const totalPages = Math.ceil(sortedData.length / rowsPerPage);
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return sortedData.slice(start, start + rowsPerPage);
  }, [sortedData, currentPage]);

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

    const columns = [
      { label: "SKU",                             key: "SKU" },
      { label: "ASIN",                            key: "ASIN" },
      { label: "Item No",                         key: "Item No" },
      { label: "Brand",                           key: "Brand" },
      { label: "Assortment Type",                 key: "Assortment Type" },
      { label: "Total Units Sold",                key: "3 Months Gross Sales" },
      { label: "Fossil Weekly Sales",             key: "Fossil Weekly Sales" },
      { label: "Last 4 Weeks Top Avg",            key: "Last 4 Weeks Top Avg" },
      { label: "Cambium SOH",                     key: "Cambium SOH" },
      { label: "Andheri/Goregaon sellable Stock", key: "Andheri/Goregaon sellable Stock" },
      { label: "In Transit PO",                   key: "In Transit PO" },
      { label: "Open PO",                         key: "Open PO" },
      { label: "Total Inventory",                 key: "Total Inventory" },
      { label: "Fossil SOH",                      key: "Fossil SOH" },
      { label: "Required Inventory",              key: "Required Inventory" },
      { label: "PO Qty",               key: "Replenishment Qty" },
    ];

    const headers = columns.map(c => `"${c.label}"`).join(",");
    const rows = filteredData.map(row =>
      columns.map(({ key }) => {
        const val = row[key];
        if (key === "Last 4 Weeks Top Avg") {
          return row["Assortment Type"] === "VD" ? `""` : `"${Number(val || 0).toFixed(2)}"`;
        }
        if (key === "Fossil Weekly Sales") return `"${Number(val || 0).toFixed(2)}"`;
        if (["Required Inventory", "Replenishment Qty"].includes(key)) return `"${Math.round(val)}"`;
        return `"${val ?? ""}"`;
      }).join(",")
    ).join("\n");

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
    <div className="space-y-4">

      {/* HEADER */}
      <div className="rounded-xl px-5 py-3 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold">Fossil Replenishment Intelligence</h1>
          <p className="text-slate-300 text-xs">Fossil FCY Inventory Planning</p>
        </div>
        <button
          onClick={() => setSopOpen(true)}
          className="px-3 py-1 text-xs bg-white/10 hover:bg-white/20 border border-white/20 rounded transition flex items-center gap-1.5"
          title="Read the SOP for this page"
        >
          📘 How is this calculated?
        </button>
      </div>

      {/* SOP MODAL */}
      <FossilSOPModal open={sopOpen} onClose={() => setSopOpen(false)} />

      {/* KPI */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
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
            Cover Weeks <span className="normal-case font-normal text-indigo-400">(override matrix)</span>
          </label>
          <div className="grid grid-cols-1 mt-2">
            <div>
              <div className="text-xs text-slate-400 mb-1">&nbsp;</div>
              <select
                value={coverWeeks ?? ""}
                onChange={(e) => {
                  setCurrentPage(1);
                  setCoverWeeks(e.target.value === "" ? null : Number(e.target.value));
                }}
                className="w-full px-4 py-2 border border-slate-200 rounded-lg"
              >
                <option value="">Use Matrix (default)</option>
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
            placeholder="Search Item No, SKU, ASIN..."
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
          <button onClick={exportCSV} className="px-4 py-2 bg-slate-900 text-white rounded-lg">
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
                  { label: "SKU",                             key: "SKU" },
                  { label: "ASIN",                            key: "ASIN" },
                  { label: "Item No",                         key: "Item No" },
                  { label: "Brand",                           key: "Brand" },
                  { label: "Assortment Type",                 key: "Assortment Type" },
                  { label: "Total Units Sold",                key: "3 Months Gross Sales" },
                  { label: "Fossil Weekly Sales",             key: "Fossil Weekly Sales" },
                  { label: "Last 4 Weeks Top Avg",            key: "Last 4 Weeks Top Avg" },
                  { label: "Cambium SOH",                     key: "Cambium SOH" },
                  { label: "Andheri/Goregaon sellable Stock", key: "Andheri/Goregaon sellable Stock" },
                  { label: "In Transit PO",                   key: "In Transit PO" },
                  { label: "Open PO",                         key: "Open PO" },
                  { label: "Total Inventory",                 key: "Total Inventory" },
                  { label: "Fossil SOH",                      key: "Fossil SOH" },
                  { label: "Required Inventory",              key: "Required Inventory" },
                  { label: "PO Qty",               key: "Replenishment Qty" },
                ].map(({ label, key }) => (
                  <th
                    key={key}
                    onClick={() => toggleSort(key)}
                    className="px-4 py-3 text-left whitespace-nowrap cursor-pointer hover:bg-slate-200 select-none"
                  >
                    {label}{sortConfig.key === key ? (sortConfig.direction === "asc" ? " ▲" : " ▼") : " ↕"}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={17} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>
              ) : paginatedData.length === 0 ? (
                <tr><td colSpan={17} className="px-4 py-8 text-center text-slate-400">No results found.</td></tr>
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
                  <td className="px-4 py-3">{row["3 Months Gross Sales"]}</td>
                  <td className="px-4 py-3">{row["Fossil Weekly Sales"]?.toFixed(2)}</td>
                  <td className="px-4 py-3">
                    {row["Assortment Type"] === "VD" ? "-" : row["Last 4 Weeks Top Avg"]?.toFixed(2)}
                  </td>
                  <td className="px-4 py-3">{row["Cambium SOH"]}</td>
                  <td className="px-4 py-3">{row["Andheri/Goregaon sellable Stock"]}</td>
                  <td className="px-4 py-3">{row["In Transit PO"]}</td>
                  <td className="px-4 py-3">{row["Open PO"]}</td>
                  <td className="px-4 py-3">{row["Total Inventory"]}</td>
                  <td className="px-4 py-3 text-red-600 font-semibold">{row["Fossil SOH"]}</td>
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
            className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50"
          >Previous</button>
          <div className="text-sm text-slate-500">Page {currentPage} of {totalPages || 1}</div>
          <button
            disabled={currentPage === totalPages || totalPages === 0}
            onClick={() => setCurrentPage(p => p + 1)}
            className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50"
          >Next</button>
        </div>
      </div>

    </div>
  );
}

function MetricCard({ title, value }) {
  return (
    <div className="px-3 py-2 bg-white rounded-lg shadow-sm border border-slate-100">
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{title}</div>
      <div className="text-base font-semibold text-slate-800">{value ?? "-"}</div>
    </div>
  );
}

function FossilSOPModal({ open, onClose }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              How Fossil Replenishment is Calculated
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Brands: Fossil · Armani Exchange · Michael Kors · Emporio Armani · Diesel · Skagen
            </p>
          </div>
          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-slate-100 text-slate-700 text-xs rounded hover:bg-slate-200"
          >
            Close
          </button>
        </div>

        <div className="overflow-auto p-5 text-sm text-slate-700 space-y-4 leading-relaxed">

          <p className="text-slate-600">
            Tells you how many units to send from Fossil's dispatch warehouse to Amazon FBA for each SKU. Math respects Assortment Type, Brand-specific Weeks of Cover, and a Fossil SOH cap.
          </p>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Top controls</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>Sales Window (From / To)</b> — Range from available weeks (default: last 12 weeks)</li>
              <li><b>Cover Weeks</b> — Override the brand × assortment matrix value (leave on default to use the matrix)</li>
              <li><b>Assortment Type</b> filter (FP / Discount / VD), then <b>Brand</b> filter, plus Search</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Weeks of Cover matrix (per Brand × Assortment Type)</h3>
            <div className="overflow-auto">
              <table className="w-full text-xs border-collapse">
                <thead className="bg-slate-100">
                  <tr>
                    <th className="border border-slate-300 px-2 py-1.5 text-left font-semibold">Brand</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-center font-semibold">FP</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-center font-semibold">Discount</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-center font-semibold">VD</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td className="border border-slate-300 px-2 py-1 font-medium">Fossil</td><td className="border border-slate-300 px-2 py-1 text-center">9</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">6</td></tr>
                  <tr><td className="border border-slate-300 px-2 py-1 font-medium">Armani Exchange</td><td className="border border-slate-300 px-2 py-1 text-center">6</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">6</td></tr>
                  <tr><td className="border border-slate-300 px-2 py-1 font-medium">Michael Kors</td><td className="border border-slate-300 px-2 py-1 text-center">6</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">6</td></tr>
                  <tr><td className="border border-slate-300 px-2 py-1 font-medium">Emporio Armani</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">6</td></tr>
                  <tr><td className="border border-slate-300 px-2 py-1 font-medium">Diesel</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">6</td></tr>
                  <tr><td className="border border-slate-300 px-2 py-1 font-medium">Skagen</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">4</td><td className="border border-slate-300 px-2 py-1 text-center">6</td></tr>
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              <b>Core SKUs always get 12 weeks</b> — overrides BOTH the matrix and any manual Cover Weeks override.<br/>
              Core SKUs: FBA66963, FBA66636, FBA69595, FBA79633, FBA79527, FBA79882
            </p>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Columns</h3>
            <table className="w-full text-xs border-collapse">
              <tbody>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium w-44">Total Units Sold</td><td className="border border-slate-300 px-2 py-1">Units sold in the selected window (Amazon channel only)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Fossil Weekly Sales</td><td className="border border-slate-300 px-2 py-1">Total Sold ÷ window weeks</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Last 4 Weeks Top Avg</td><td className="border border-slate-300 px-2 py-1">Avg of the most recent <b>4 weeks of data</b> (independent of your window). Shown only for FP / Discount.</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Cambium SOH</td><td className="border border-slate-300 px-2 py-1">Cambium warehouse stock (from master)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Andheri/Goregaon</td><td className="border border-slate-300 px-2 py-1">Sellable stock at those locations (from master)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">In Transit PO</td><td className="border border-slate-300 px-2 py-1">PO units in transit (from master)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Open PO</td><td className="border border-slate-300 px-2 py-1">Open PO units (from master)</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Total Inventory</td><td className="border border-slate-300 px-2 py-1">Cambium SOH + Andheri/Goregaon + In Transit PO + Open PO</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Fossil SOH</td><td className="border border-slate-300 px-2 py-1">Stock available at Fossil's dispatch warehouse</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium">Required Inventory</td><td className="border border-slate-300 px-2 py-1">Effective Weekly Sales × Weeks of Cover</td></tr>
                <tr><td className="border border-slate-300 px-2 py-1 font-medium bg-amber-50">PO Qty (Replenishment)</td><td className="border border-slate-300 px-2 py-1 bg-amber-50">Required − Total Inventory, <b>capped at Fossil SOH</b>. Forced to 0 if Fossil SOH = 0.</td></tr>
              </tbody>
            </table>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Effective Weekly Sales rule</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li><b>FP / Discount</b> → use the <b>higher</b> of Fossil Weekly Sales vs Last 4 Weeks Top Avg (recent demand spikes flow through)</li>
              <li><b>VD</b> → use Fossil Weekly Sales only (the Last 4 Weeks Top Avg column shows "-" for VD rows)</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Filter rules</h3>
            <ul className="list-disc pl-5 space-y-0.5 text-xs">
              <li>Sales counted: brand = <b>Fossil</b>, channel = <b>Amazon</b> only</li>
              <li>Inventory fields: all sourced from the master xlsx (Cambium SOH, Andheri/Goregaon, In Transit PO, Open PO, Fossil SOH)</li>
              <li>Amazon Inventory (computed from FBA file) is read but <b>not</b> in Total Inventory — Total uses Cambium SOH + 3 master columns only</li>
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Example (Fossil FP, non-core)</h3>
            <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
              FBA12345: sold 108 over 12 weeks → Fossil Weekly = 9 →
              Last 4 Weeks Top Avg = 12 → <b>Effective = max(9, 12) = 12</b> →
              Fossil FP cover = 9 weeks → Required = 108 →
              Total Inventory = 60 → Replen need = 48 →
              Fossil SOH = 40 → <b>PO Qty = 40</b> (capped at Fossil SOH).
            </p>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Example (Core SKU)</h3>
            <p className="bg-slate-50 border border-slate-200 rounded p-2 text-xs">
              FBA66636 (core, FP): Fossil Weekly = 6.92, Last 4 Avg = 9 →
              Effective = 9 → Core override forces 12 weeks of cover →
              Required = 9 × 12 = 108 → Total Inventory = 88 → PO need = 20 →
              Fossil SOH = 97 → <b>PO Qty = 20</b>.
            </p>
          </section>

        </div>
      </div>
    </div>
  );
}