import { useState } from "react";

export default function ReplenishmentV2() {
  const [showFilters, setShowFilters] = useState(false);

  return (
    <div className="p-6">
      {/* HEADER */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">
          Amazon Replenishment Dashboard
        </h1>

        <button
          onClick={() => setShowFilters(!showFilters)}
          className="px-4 py-2 bg-black text-white rounded-lg"
        >
          Filters
        </button>
      </div>

      {/* GLOBAL SEARCH */}
      <div className="mb-6">
        <input
          type="text"
          placeholder="Search Model / SKU / ASIN"
          className="w-full p-3 border rounded-lg"
        />
      </div>

      {/* KPI SECTION */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="p-4 border rounded-lg">
          <p className="text-sm text-gray-500">Units to Replenish</p>
          <h2 className="text-2xl font-bold">13169</h2>
        </div>

        <div className="p-4 border rounded-lg">
          <p className="text-sm text-gray-500">Avg Weeks of Cover</p>
          <h2 className="text-2xl font-bold">0.78</h2>
        </div>
      </div>

      {/* QUICK FILTERS */}
      <div className="flex gap-3 mb-6">
        <button className="px-3 py-1 border rounded-lg">Risky</button>
        <button className="px-3 py-1 border rounded-lg">Low Cover</button>
        <button className="px-3 py-1 border rounded-lg">Overstock</button>
      </div>

      {/* TABLE PLACEHOLDER */}
      <div className="border rounded-lg p-4">
        <p className="text-gray-500">Replenishment Table Here</p>
      </div>

      {/* FILTER DRAWER */}
      {showFilters && (
        <div className="fixed right-0 top-0 h-full w-80 bg-white shadow-lg p-6">
          <h2 className="text-lg font-bold mb-4">Filters</h2>

          <div className="space-y-4">
            <select className="w-full p-2 border rounded">
              <option>1 Week</option>
              <option>4 Weeks</option>
            </select>

            <select className="w-full p-2 border rounded">
              <option>8 Weeks</option>
              <option>12 Weeks</option>
            </select>
          </div>
        </div>
      )}
    </div>
  );
}