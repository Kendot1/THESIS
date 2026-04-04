"use client";
import { useState, useMemo } from "react";
import Link from "next/link";
import { Search, ArrowUpDown, Filter, Download, Eye } from "lucide-react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import SparklineChart from "../components/SparklineChart";
import ScrollReveal from "../components/ScrollReveal";
import { products, categories } from "../lib/data";

type SortKey = "name" | "currentPrice" | "predictedPrice" | "change" | "volume";
type SortDir = "asc" | "desc";

export default function TablePage() {
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedProducts = useMemo(() => {
    let results = products.filter((p) => {
      const matchCategory =
        selectedCategory === "All" || p.category === selectedCategory;
      const matchQuery =
        !query ||
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.category.toLowerCase().includes(query.toLowerCase());
      return matchCategory && matchQuery;
    });

    results.sort((a, b) => {
      let comp = 0;
      switch (sortKey) {
        case "name":
          comp = a.name.localeCompare(b.name);
          break;
        case "currentPrice":
          comp = a.currentPrice - b.currentPrice;
          break;
        case "predictedPrice":
          comp = a.predictedPrice - b.predictedPrice;
          break;
        case "change":
          comp =
            (a.predictedPrice - a.currentPrice) / a.currentPrice -
            (b.predictedPrice - b.currentPrice) / b.currentPrice;
          break;
        case "volume":
          comp =
            parseInt(a.volume.replace(/,/g, "")) -
            parseInt(b.volume.replace(/,/g, ""));
          break;
      }
      return sortDir === "asc" ? comp : -comp;
    });

    return results;
  }, [query, selectedCategory, sortKey, sortDir]);

  const SortHeader = ({
    label,
    sortKeyName,
  }: {
    label: string;
    sortKeyName: SortKey;
  }) => (
    <button
      onClick={() => toggleSort(sortKeyName)}
      className="flex items-center gap-1 text-xs font-semibold text-gray-500 uppercase tracking-wider hover:text-primary-800 transition-colors group"
      aria-label={`Sort by ${label}`}
    >
      {label}
      <ArrowUpDown
        className={`w-3 h-3 transition-colors ${
          sortKey === sortKeyName ? "text-primary-800" : "text-gray-300 group-hover:text-gray-400"
        }`}
      />
    </button>
  );

  return (
    <>
      <Header />
      <main id="main-content" className="pt-20 min-h-screen bg-surface">
        {/* ─── Header ──────────────────────────────────── */}
        <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-14 sm:py-16 overflow-hidden">
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            <div className="absolute top-0 left-1/3 w-[400px] h-[400px] bg-accent/6 rounded-full blur-[100px]" />
          </div>
          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <h1
              className="text-3xl sm:text-4xl font-bold text-white mb-2"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Market{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                Table View
              </span>
            </h1>
            <p className="text-white/50 max-w-xl">
              Comprehensive data view of all tracked agri-fishery products
            </p>
          </div>
        </section>

        <div className="max-w-7xl mx-auto px-5 lg:px-10 py-8 sm:py-10">
          {/* ─── Filters ─────────────────────────────────── */}
          <ScrollReveal>
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-6">
              {/* Search */}
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Filter products..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-800 placeholder-gray-400
                    focus:outline-none focus:border-accent/50 focus:shadow-[0_0_0_3px_rgba(126,217,87,0.1)] transition-all"
                  id="table-search"
                  aria-label="Filter products"
                />
              </div>

              {/* Category pills */}
              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                <Filter className="w-4 h-4 text-gray-400 shrink-0" />
                {categories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all duration-200 ${
                      selectedCategory === cat
                        ? "bg-primary-800 text-white"
                        : "bg-white border border-gray-200 text-gray-600 hover:border-primary-200 hover:text-primary-800"
                    }`}
                    aria-pressed={selectedCategory === cat}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>
          </ScrollReveal>

          {/* ─── Data Table ───────────────────────────────── */}
          <ScrollReveal>
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full" role="grid" aria-label="Product prices table">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left px-5 py-4">
                        <SortHeader label="Product" sortKeyName="name" />
                      </th>
                      <th className="text-left px-5 py-4">
                        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                          Category
                        </span>
                      </th>
                      <th className="text-right px-5 py-4">
                        <SortHeader label="Current Price" sortKeyName="currentPrice" />
                      </th>
                      <th className="text-right px-5 py-4">
                        <SortHeader label="Predicted" sortKeyName="predictedPrice" />
                      </th>
                      <th className="text-right px-5 py-4">
                        <SortHeader label="Change" sortKeyName="change" />
                      </th>
                      <th className="text-right px-5 py-4">
                        <SortHeader label="Volume" sortKeyName="volume" />
                      </th>
                      <th className="text-center px-5 py-4">
                        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                          Trend
                        </span>
                      </th>
                      <th className="text-center px-5 py-4">
                        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                          Sentiment
                        </span>
                      </th>
                      <th className="text-center px-5 py-4">
                        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                          Action
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedProducts.map((p, i) => {
                      const change =
                        ((p.predictedPrice - p.currentPrice) /
                          p.currentPrice) *
                        100;
                      const isUp = change >= 0;

                      return (
                        <tr
                          key={p.id}
                          className="border-b border-gray-50 hover:bg-primary-50/40 transition-colors group"
                        >
                          {/* Product */}
                          <td className="px-5 py-4">
                            <div className="flex items-center gap-3">
                              <span className="text-xl">{p.emoji}</span>
                              <span className="font-medium text-sm text-gray-900 group-hover:text-primary-800 transition-colors">
                                {p.name}
                              </span>
                            </div>
                          </td>

                          {/* Category */}
                          <td className="px-5 py-4">
                            <span className="text-xs font-medium text-primary-600 bg-primary-50 px-2 py-0.5 rounded-full">
                              {p.category}
                            </span>
                          </td>

                          {/* Current Price */}
                          <td className="px-5 py-4 text-right">
                            <span className="text-sm font-semibold text-gray-900">
                              ₱{p.currentPrice.toFixed(2)}
                            </span>
                          </td>

                          {/* Predicted Price */}
                          <td className="px-5 py-4 text-right">
                            <span
                              className={`text-sm font-semibold ${
                                isUp ? "text-positive" : "text-negative"
                              }`}
                            >
                              ₱{p.predictedPrice.toFixed(2)}
                            </span>
                          </td>

                          {/* Change */}
                          <td className="px-5 py-4 text-right">
                            <span
                              className={`inline-flex items-center gap-0.5 text-xs font-semibold px-2 py-0.5 rounded-full ${
                                isUp
                                  ? "text-positive bg-positive/10"
                                  : "text-negative bg-negative/10"
                              }`}
                            >
                              {isUp ? "▲" : "▼"}{" "}
                              {Math.abs(change).toFixed(1)}%
                            </span>
                          </td>

                          {/* Volume */}
                          <td className="px-5 py-4 text-right text-sm text-gray-600">
                            {p.volume}
                          </td>

                          {/* Sparkline */}
                          <td className="px-5 py-4">
                            <div className="w-[80px] mx-auto">
                              <SparklineChart
                                data={p.sparklineData}
                                color={isUp ? "#2E7D32" : "#C62828"}
                                height={30}
                              />
                            </div>
                          </td>

                          {/* Sentiment */}
                          <td className="px-5 py-4 text-center">
                            <span
                              className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                                p.sentiment === "Bullish"
                                  ? "text-positive bg-positive/10"
                                  : p.sentiment === "Bearish"
                                  ? "text-negative bg-negative/10"
                                  : "text-gray-600 bg-gray-100"
                              }`}
                            >
                              {p.sentiment}
                            </span>
                          </td>

                          {/* Action */}
                          <td className="px-5 py-4 text-center">
                            <Link
                              href={`/Product/${p.id}`}
                              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-primary-800 bg-primary-50 rounded-lg
                                hover:bg-primary-100 transition-colors"
                              aria-label={`View details for ${p.name}`}
                            >
                              <Eye className="w-3.5 h-3.5" />
                              View
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {sortedProducts.length === 0 && (
                <div className="text-center py-16">
                  <div className="text-4xl mb-3">📊</div>
                  <h3 className="text-base font-semibold text-gray-700 mb-1">
                    No results found
                  </h3>
                  <p className="text-gray-500 text-sm">
                    Try different filters or search terms
                  </p>
                </div>
              )}

              {/* Summary row */}
              <div className="px-5 py-3 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between">
                <span className="text-xs text-gray-500">
                  Showing {sortedProducts.length} of {products.length} products
                </span>
                <span className="text-xs text-gray-400">
                  Data refreshed hourly
                </span>
              </div>
            </div>
          </ScrollReveal>
        </div>
      </main>
      <Footer />
    </>
  );
}
